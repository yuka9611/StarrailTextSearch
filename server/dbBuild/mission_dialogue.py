from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable


PLAYER_SPEAKER_NAME = "开拓者"


@dataclass(slots=True)
class TalkSentenceRef:
    talk_sentence_id: int
    speaker_hash: str | None
    text_hash: str | None
    voice_id: int | None = None


@dataclass(slots=True)
class SequenceBlock:
    block_id: str
    wait_key: str | None
    events: list[tuple[str, Any]]


@dataclass(slots=True)
class GraphCandidate:
    path: str
    source: str
    performance_id: int | None = None
    performance_type: str = ""


@dataclass(slots=True)
class MissionDialogueLine:
    source_path: str
    line_type: str
    talk_sentence_id: int | None
    speaker_hash: str | None
    speaker_text: str | None
    text_hash: str | None
    text_content: str | None
    option_group_id: str | None = None
    option_index: int | None = None
    branch_index: int | None = None


@dataclass(slots=True)
class MissionDialogueSection:
    section_id: int
    order: int
    title_hash: str | None
    fallback_title: str
    description_hash: str | None
    location: str
    resource_note: str
    lines: list[MissionDialogueLine]


@dataclass(slots=True)
class MissionDialogueContext:
    mission_id: int
    story_paths: list[str]
    sections: list[MissionDialogueSection]


def normalize_hash(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "Hash" in value:
            return normalize_hash(value.get("Hash"))
        if "Value" in value:
            return normalize_hash(value.get("Value"))
        return None
    text = str(value).strip()
    return text or None


def json_load(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def extract_talk_sentence_refs(payload: object) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []

    def append_result(raw_value: object | None, line_type: str) -> None:
        normalized_value = normalize_hash(raw_value)
        if normalized_value is None:
            return
        results.append((int(normalized_value), line_type))

    def walk(node: object, *, context: str = "dialogue") -> None:
        if isinstance(node, dict):
            task_type = str(node.get("$type", ""))
            if task_type.endswith("PlayOptionTalk"):
                for item in node.get("OptionList", []) or []:
                    append_result(item.get("TalkSentenceID"), "option")
                return
            if task_type.endswith("PlaySimpleTalk") or task_type.endswith("PlayMissionTalk"):
                talk_list = node.get("SimpleTalkList")
                if not isinstance(talk_list, list):
                    talk_list = node.get("MissionTalkList")
                for item in talk_list or []:
                    append_result(item.get("TalkSentenceID"), "dialogue")
                return
            if task_type in {"RPG.GameCore.PlayScreenTransfer", "RPG.GameCore.PerformanceTransition"}:
                if node.get("TextEnabled") is not False:
                    append_result(node.get("TalkSentenceID"), "dialogue")
                return
            if task_type in {"RPG.GameCore.PerformanceEndBlackText", "RPG.GameCore.PlayMultiVoiceTalk"}:
                append_result(node.get("TalkSentenceID"), "dialogue")
                return
            if task_type == "RPG.GameCore.PlayFullScreenTransfer":
                text_info = node.get("TextInfo")
                if isinstance(text_info, dict):
                    for item in text_info.get("TextList") or []:
                        append_result(item.get("TalkSentenceID"), context)
                return
            if task_type == "RPG.GameCore.SelectMissionItem":
                simple_talk = node.get("SimpleTalk")
                if isinstance(simple_talk, dict):
                    append_result(simple_talk.get("TalkSentenceID"), "dialogue")
                return
            for key, value in node.items():
                walk(value, context="option" if key == "OptionList" else context)
            return

        if isinstance(node, list):
            for item in node:
                walk(item, context=context)

    walk(payload)
    return results


def iter_mission_story_dirs(story_root: Path) -> Iterable[tuple[int, list[Path]]]:
    grouped: dict[int, list[Path]] = {}
    for mission_root in [story_root / "Discussion" / "Mission", story_root / "Mission"]:
        if not mission_root.is_dir():
            continue
        for mission_dir in sorted(mission_root.glob("*")):
            if not mission_dir.is_dir():
                continue
            try:
                mission_id = int(mission_dir.name)
            except ValueError:
                continue
            bucket = grouped.setdefault(mission_id, [])
            if mission_dir not in bucket:
                bucket.append(mission_dir)
    for mission_id in sorted(grouped):
        yield mission_id, sorted(grouped[mission_id], key=lambda path: str(path))


class MissionDialogueExtractor:
    _XXH64_MASK = (1 << 64) - 1
    _XXH64_PRIME1 = 11400714785074694791
    _XXH64_PRIME2 = 14029467366897019727
    _XXH64_PRIME3 = 1609587929392839161
    _XXH64_PRIME4 = 9650029242287828579
    _XXH64_PRIME5 = 2870177450012600261

    def __init__(self, data_root: Path, talk_sentence_map: dict[int, TalkSentenceRef]):
        self.data_root = data_root.resolve()
        self.excel_root = self.data_root / "ExcelOutput"
        self.story_root = self.data_root / "Story"
        self.config_level_root = self.data_root / "Config" / "Level"
        self.talk_sentence_map = talk_sentence_map
        self.main_missions_by_id: dict[int, dict[str, Any]] = {}
        self.sub_missions_by_id: dict[int, dict[str, Any]] = {}
        self.performance_paths_by_id: dict[int, str] = {}
        self.performance_type_by_id: dict[int, str] = {}
        self.linked_performance_ids_by_sub_id: dict[int, list[int]] = {}
        self.tutorial_guide_groups_by_sub_id: dict[int, list[dict[str, Any]]] = {}
        self.tutorial_guide_data_by_id: dict[int, dict[str, Any]] = {}
        self.tutorial_guide_talk_by_id: dict[int, dict[str, Any]] = {}
        self.tutorial_data_by_sub_id: dict[int, list[dict[str, Any]]] = {}
        self._json_cache: dict[str, Any] = {}
        self.mission_graph_paths_by_main_id: dict[int, list[str]] = {}
        self.graph_paths_by_talk_sentence_key: dict[tuple[int, int], list[str]] = {}
        self._load_indexes()

    @classmethod
    def _xxh64_rotl(cls, value: int, bits: int) -> int:
        return ((value << bits) | (value >> (64 - bits))) & cls._XXH64_MASK

    @classmethod
    def _xxh64_round(cls, acc: int, lane: int) -> int:
        acc = (acc + lane * cls._XXH64_PRIME2) & cls._XXH64_MASK
        acc = cls._xxh64_rotl(acc, 31)
        return (acc * cls._XXH64_PRIME1) & cls._XXH64_MASK

    @classmethod
    def _xxh64_merge_round(cls, acc: int, lane: int) -> int:
        acc ^= cls._xxh64_round(0, lane)
        return (acc * cls._XXH64_PRIME1 + cls._XXH64_PRIME4) & cls._XXH64_MASK

    @classmethod
    def hash_text_key(cls, text_key: str) -> int:
        data = text_key.encode("utf-8")
        length = len(data)
        index = 0
        if length >= 32:
            v1 = (cls._XXH64_PRIME1 + cls._XXH64_PRIME2) & cls._XXH64_MASK
            v2 = cls._XXH64_PRIME2
            v3 = 0
            v4 = (-cls._XXH64_PRIME1) & cls._XXH64_MASK
            limit = length - 32
            while index <= limit:
                v1 = cls._xxh64_round(v1, int.from_bytes(data[index:index + 8], "little"))
                index += 8
                v2 = cls._xxh64_round(v2, int.from_bytes(data[index:index + 8], "little"))
                index += 8
                v3 = cls._xxh64_round(v3, int.from_bytes(data[index:index + 8], "little"))
                index += 8
                v4 = cls._xxh64_round(v4, int.from_bytes(data[index:index + 8], "little"))
                index += 8
            acc = (
                cls._xxh64_rotl(v1, 1)
                + cls._xxh64_rotl(v2, 7)
                + cls._xxh64_rotl(v3, 12)
                + cls._xxh64_rotl(v4, 18)
            ) & cls._XXH64_MASK
            acc = cls._xxh64_merge_round(acc, v1)
            acc = cls._xxh64_merge_round(acc, v2)
            acc = cls._xxh64_merge_round(acc, v3)
            acc = cls._xxh64_merge_round(acc, v4)
        else:
            acc = cls._XXH64_PRIME5
        acc = (acc + length) & cls._XXH64_MASK
        while index + 8 <= length:
            lane = int.from_bytes(data[index:index + 8], "little")
            acc ^= cls._xxh64_round(0, lane)
            acc = (cls._xxh64_rotl(acc, 27) * cls._XXH64_PRIME1 + cls._XXH64_PRIME4) & cls._XXH64_MASK
            index += 8
        if index + 4 <= length:
            lane = int.from_bytes(data[index:index + 4], "little")
            acc ^= (lane * cls._XXH64_PRIME1) & cls._XXH64_MASK
            acc = (cls._xxh64_rotl(acc, 23) * cls._XXH64_PRIME2 + cls._XXH64_PRIME3) & cls._XXH64_MASK
            index += 4
        while index < length:
            acc ^= (data[index] * cls._XXH64_PRIME5) & cls._XXH64_MASK
            acc = (cls._xxh64_rotl(acc, 11) * cls._XXH64_PRIME1) & cls._XXH64_MASK
            index += 1
        acc ^= acc >> 33
        acc = (acc * cls._XXH64_PRIME2) & cls._XXH64_MASK
        acc ^= acc >> 29
        acc = (acc * cls._XXH64_PRIME3) & cls._XXH64_MASK
        acc ^= acc >> 32
        return acc & cls._XXH64_MASK

    def _load_indexes(self) -> None:
        for row in json_load(self.excel_root / "MainMission.json", []) or []:
            mission_id = row.get("MainMissionID")
            if isinstance(mission_id, int):
                self.main_missions_by_id[mission_id] = row

        for row in json_load(self.excel_root / "SubMission.json", []) or []:
            sub_id = row.get("SubMissionID")
            if isinstance(sub_id, int):
                self.sub_missions_by_id[sub_id] = row

        for path, kind in [
            (self.excel_root / "PerformanceDS.json", "D"),
            (self.excel_root / "PerformanceCG.json", "C"),
        ]:
            for row in json_load(path, []) or []:
                performance_id = row.get("PerformanceID")
                performance_path = row.get("PerformancePath")
                if isinstance(performance_id, int) and isinstance(performance_path, str):
                    self.performance_paths_by_id[performance_id] = performance_path
                    self.performance_type_by_id[performance_id] = kind

        for row in json_load(self.excel_root / "PerformanceSubMissionLink.json", []) or []:
            sub_id = row.get("SubMissionID")
            performance_id = row.get("PerformanceID")
            if not isinstance(sub_id, int) or not isinstance(performance_id, int):
                continue
            self.linked_performance_ids_by_sub_id.setdefault(sub_id, []).append(performance_id)
            performance_type = row.get("PerformanceType")
            if isinstance(performance_type, str) and performance_type:
                self.performance_type_by_id.setdefault(performance_id, performance_type)

        for row in json_load(self.excel_root / "TutorialGuideData.json", []) or []:
            row_id = row.get("ID")
            if isinstance(row_id, int):
                self.tutorial_guide_data_by_id[row_id] = row
        for row in json_load(self.excel_root / "TutorialGuideTalkData.json", []) or []:
            row_id = row.get("ID")
            if isinstance(row_id, int):
                self.tutorial_guide_talk_by_id[row_id] = row
        for row in json_load(self.excel_root / "TutorialGuideGroup.json", []) or []:
            if isinstance(row, dict):
                for sub_id in self._extract_row_sub_mission_ids(row):
                    self.tutorial_guide_groups_by_sub_id.setdefault(sub_id, []).append(row)
        for row in json_load(self.excel_root / "TutorialData.json", []) or []:
            if isinstance(row, dict):
                for sub_id in self._extract_row_sub_mission_ids(row):
                    self.tutorial_data_by_sub_id.setdefault(sub_id, []).append(row)

    def _read_json(self, relative_path: str) -> Any:
        relative_path = self._relative_path(relative_path)
        if relative_path in self._json_cache:
            return self._json_cache[relative_path]
        path = self.data_root / relative_path
        payload = json_load(path, None)
        if payload is not None:
            self._json_cache[relative_path] = payload
        return payload

    def _relative_path(self, path: str | Path) -> str:
        normalized = str(path or "").replace("\\", "/")
        if not normalized:
            return ""
        if Path(normalized).is_absolute():
            normalized = str(Path(normalized).resolve().relative_to(self.data_root)).replace("\\", "/")
        return normalized.lstrip("./")

    def _coerce_int(self, value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    def _hash_ref(self, value: Any) -> str | None:
        text_hash = normalize_hash(value)
        if not text_hash:
            return None
        if text_hash.lstrip("-").isdigit():
            return text_hash
        return str(self.hash_text_key(text_hash))

    @staticmethod
    def _is_player_role_text(value: str) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return False
        if normalized in {"player", "role_player", "talk_role_player"}:
            return True
        compact = normalized.replace("_", "").replace("-", "")
        if compact in {"hero", "trailblazer", "avatar", "mainavatar", "playeravatar", "playercharacter"}:
            return True
        return any(
            marker in normalized
            for marker in (
                "avatar_player",
                "npc_avatar_lad_player",
                "npc_avatar_miss_player",
                "playerboy",
                "playergirl",
            )
        )

    @classmethod
    def _value_has_player_role(cls, value: Any) -> bool:
        if isinstance(value, str):
            return cls._is_player_role_text(value)
        if isinstance(value, dict):
            return any(cls._value_has_player_role(item) for item in value.values())
        if isinstance(value, list):
            return any(cls._value_has_player_role(item) for item in value)
        return False

    @classmethod
    def _has_player_role(cls, obj: Any) -> bool:
        if not isinstance(obj, dict):
            return False
        player_role_keys = {
            "role",
            "talkrole",
            "speakerrole",
            "speakertype",
            "talkertype",
            "roletype",
            "avatarid",
            "characteruniquename",
        }
        for key, value in obj.items():
            normalized_key = str(key).replace("_", "").lower()
            if normalized_key in player_role_keys and cls._value_has_player_role(value):
                return True
        return False

    def _extract_trigger_sub_mission_ids(self, *trigger_lists: Any) -> list[int]:
        sub_mission_ids: list[int] = []
        seen: set[int] = set()
        for trigger_list in trigger_lists:
            if not isinstance(trigger_list, list):
                continue
            for trigger in trigger_list:
                if not isinstance(trigger, dict):
                    continue
                sub_id = self._coerce_int(trigger.get("TriggerParam"))
                if sub_id is None or sub_id in seen:
                    continue
                seen.add(sub_id)
                sub_mission_ids.append(sub_id)
        return sub_mission_ids

    def _extract_row_sub_mission_ids(self, row: dict[str, Any]) -> list[int]:
        sub_mission_ids: list[int] = []
        direct_sub_id = self._coerce_int(row.get("FinishSubMission"))
        if direct_sub_id is not None:
            sub_mission_ids.append(direct_sub_id)
        for sub_id in self._extract_trigger_sub_mission_ids(row.get("TriggerParams"), row.get("FinishTriggerList")):
            if sub_id not in sub_mission_ids:
                sub_mission_ids.append(sub_id)
        return sub_mission_ids

    def _get_mission_info(self, mission_id: int) -> dict[str, Any] | None:
        payload = self._read_json(f"Config/Level/Mission/{mission_id}/MissionInfo_{mission_id}.json")
        return payload if isinstance(payload, dict) else None

    def _get_mission_info_partial_layout(self, mission_id: int) -> dict[str, Any] | None:
        payload = self._read_json(f"Config/Level/Mission/{mission_id}/MissionInfo_{mission_id}.partial.layout.json")
        return payload if isinstance(payload, dict) else None

    def _get_graph_paths(self, mission_id: int, graph_id: int, *, include_mission: bool = True) -> list[str]:
        base_dir = f"Config/Level/Mission/{mission_id}"
        candidates: list[str] = []
        if include_mission:
            candidates.append(f"{base_dir}/Mission_{graph_id}.json")
        candidates.extend(
            [
                f"{base_dir}/Act/Act{graph_id}.json",
                f"{base_dir}/Act{graph_id}.json",
                f"{base_dir}/CS{graph_id}.json",
                f"{base_dir}/Talk/Talk_{graph_id}.json",
            ]
        )
        result: list[str] = []
        seen: set[str] = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            result.append(path)
        return result

    def _get_partial_layout_sub_mission_ids(self, mission_id: int) -> list[int]:
        partial_layout = self._get_mission_info_partial_layout(mission_id)
        if not isinstance(partial_layout, dict):
            return []
        raw_layouts = partial_layout.get("BakeInfoLayouts")
        if not isinstance(raw_layouts, list):
            return []
        layouts = [row for row in raw_layouts if isinstance(row, dict)]
        layouts.sort(
            key=lambda row: (
                row.get("Offset") if isinstance(row.get("Offset"), int) else 10**9,
                row.get("UniqueName") if isinstance(row.get("UniqueName"), str) else "",
            )
        )
        sub_ids: list[int] = []
        seen: set[int] = set()
        for row in layouts:
            unique_name = row.get("UniqueName")
            if not isinstance(unique_name, str):
                continue
            match = re.fullmatch(r"SubMission_(\d+)", unique_name)
            if not match:
                continue
            sub_id = int(match.group(1))
            if sub_id in seen:
                continue
            seen.add(sub_id)
            sub_ids.append(sub_id)
        return sub_ids

    def _build_sub_rows(self, mission_id: int, mission_info: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(mission_info, dict):
            return []

        raw_sub_rows = mission_info.get("SubMissionList") or []
        if isinstance(raw_sub_rows, list):
            sub_rows = [row for row in raw_sub_rows if isinstance(row, dict)]
            if sub_rows:
                sub_rows.sort(key=lambda row: (row.get("Progress", 0), row.get("ID", 0)))
                return sub_rows

        ordered_ids: list[int] = []
        seen: set[int] = set()

        def append_sub_id(raw_value: Any) -> None:
            sub_id = self._coerce_int(raw_value)
            if sub_id is None or sub_id in seen:
                return
            seen.add(sub_id)
            ordered_ids.append(sub_id)

        for raw_value in mission_info.get("StartSubMissionList") or []:
            append_sub_id(raw_value)
        for raw_value in mission_info.get("FinishSubMissionList") or []:
            append_sub_id(raw_value)
        for sub_id in self._get_partial_layout_sub_mission_ids(mission_id):
            append_sub_id(sub_id)

        return [{"ID": sub_id, "_synthetic": True} for sub_id in ordered_ids]

    def _line_from_sentence(self, source_path: str, sentence_id: int, *, speaker_fallback: str = "") -> MissionDialogueLine | None:
        sentence = self.talk_sentence_map.get(sentence_id)
        if sentence is None or not sentence.text_hash:
            return None
        return MissionDialogueLine(
            source_path=source_path,
            line_type="dialogue",
            talk_sentence_id=sentence_id,
            speaker_hash=sentence.speaker_hash,
            speaker_text=speaker_fallback if speaker_fallback and not sentence.speaker_hash else None,
            text_hash=sentence.text_hash,
            text_content=None,
        )

    def _task_sentence_lines(self, source_path: str, task: dict[str, Any], key: str = "TalkSentenceID") -> list[MissionDialogueLine]:
        sentence_id = task.get(key)
        if not isinstance(sentence_id, int):
            return []
        speaker_fallback = PLAYER_SPEAKER_NAME if self._has_player_role(task) else ""
        line = self._line_from_sentence(source_path, sentence_id, speaker_fallback=speaker_fallback)
        return [line] if line else []

    def _text_value_to_line(self, source_path: str, value: Any) -> MissionDialogueLine | None:
        text_hash = self._hash_ref(value)
        if not text_hash:
            return None
        return MissionDialogueLine(
            source_path=source_path,
            line_type="narration",
            talk_sentence_id=None,
            speaker_hash=None,
            speaker_text=None,
            text_hash=text_hash,
            text_content=None,
        )

    def _text_info_lines(self, source_path: str, text_info: Any) -> list[MissionDialogueLine]:
        if not isinstance(text_info, dict):
            return []
        lines: list[MissionDialogueLine] = []
        for item in text_info.get("TextList") or []:
            if not isinstance(item, dict):
                continue
            sentence_id = item.get("TalkSentenceID")
            line = self._line_from_sentence(source_path, sentence_id) if isinstance(sentence_id, int) else None
            if line is None:
                line = self._text_value_to_line(source_path, item.get("Text"))
            if line is None:
                line = self._text_value_to_line(source_path, item.get("TextMapID"))
            if line is None:
                line = self._text_value_to_line(source_path, item.get("TextmapID"))
            if line:
                lines.append(line)
        return lines

    def _extract_task_lines(self, source_path: str, task: dict[str, Any]) -> list[MissionDialogueLine]:
        task_type = task.get("$type")
        if task_type in {
            "RPG.GameCore.PlayAndWaitSimpleTalk",
            "RPG.GameCore.PlaySimpleTalk",
            "RPG.GameCore.PlayAndWaitMissionTalk",
            "RPG.GameCore.PlayMissionTalk",
        }:
            talk_list = task.get("SimpleTalkList")
            if not isinstance(talk_list, list):
                talk_list = task.get("MissionTalkList")
            if not isinstance(talk_list, list):
                return []
            lines: list[MissionDialogueLine] = []
            for item in talk_list:
                if isinstance(item, dict):
                    lines.extend(self._task_sentence_lines(source_path, item))
            return lines

        if task_type == "RPG.GameCore.PlayOptionTalk":
            return []
        if task_type in {"RPG.GameCore.PlayScreenTransfer", "RPG.GameCore.PerformanceTransition"}:
            return [] if task.get("TextEnabled") is False else self._task_sentence_lines(source_path, task)
        if task_type in {"RPG.GameCore.PerformanceEndBlackText", "RPG.GameCore.PlayMultiVoiceTalk"}:
            return self._task_sentence_lines(source_path, task)
        if task_type == "RPG.GameCore.PlayFullScreenTransfer":
            return self._text_info_lines(source_path, task.get("TextInfo"))
        if task_type == "RPG.GameCore.ShowGuideText":
            line = self._text_value_to_line(source_path, task.get("Text"))
            return [line] if line else []
        if task_type == "RPG.GameCore.ShowGuideHintWithText":
            line = self._text_value_to_line(source_path, task.get("GuideText"))
            return [line] if line else []
        if task_type == "RPG.GameCore.SelectMissionItem":
            lines: list[MissionDialogueLine] = []
            simple_talk = task.get("SimpleTalk")
            if isinstance(simple_talk, dict):
                lines.extend(self._task_sentence_lines(source_path, simple_talk))
            info_line = self._text_value_to_line(source_path, task.get("InfoText"))
            if info_line:
                lines.append(info_line)
            return lines
        return []

    def _option_line(self, source_path: str, raw_option: dict[str, Any]) -> MissionDialogueLine | None:
        sentence_id = raw_option.get("TalkSentenceID")
        sentence = self.talk_sentence_map.get(sentence_id) if isinstance(sentence_id, int) else None
        if sentence and sentence.text_hash:
            return MissionDialogueLine(
                source_path=source_path,
                line_type="option",
                talk_sentence_id=sentence_id,
                speaker_hash=None,
                speaker_text=None,
                text_hash=sentence.text_hash,
                text_content=None,
            )
        option_hash = self._hash_ref(raw_option.get("OptionTextmapID"))
        if not option_hash:
            return None
        return MissionDialogueLine(
            source_path=source_path,
            line_type="option",
            talk_sentence_id=None,
            speaker_hash=None,
            speaker_text=None,
            text_hash=option_hash,
            text_content=None,
        )

    def _parse_sequence_blocks(self, obj: dict[str, Any], source_path: str) -> list[SequenceBlock]:
        raw_blocks = obj.get("OnStartSequece")
        if not isinstance(raw_blocks, list):
            raw_blocks = obj.get("OnStartSequence")
        if not isinstance(raw_blocks, list):
            return []

        blocks: list[SequenceBlock] = []
        for index, raw_block in enumerate(raw_blocks):
            if not isinstance(raw_block, dict):
                continue
            tasks = raw_block.get("TaskList")
            if not isinstance(tasks, list):
                continue
            wait_key: str | None = None
            events: list[tuple[str, Any]] = []
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                task_type = task.get("$type")
                if task_type == "RPG.GameCore.WaitCustomString" and wait_key is None and not events:
                    wait_key = self._normalize_key(((task.get("CustomString") or {}).get("Value")))
                    continue
                lines = self._extract_task_lines(source_path, task)
                if lines:
                    events.append(("lines", lines))
                    continue
                if task_type == "RPG.GameCore.PlayOptionTalk":
                    raw_options = task.get("OptionList")
                    if not isinstance(raw_options, list):
                        continue
                    options = []
                    for raw_option in raw_options:
                        if not isinstance(raw_option, dict):
                            continue
                        line = self._option_line(source_path, raw_option)
                        if not line:
                            continue
                        options.append(
                            {
                                "line": line,
                                "trigger": self._normalize_key(raw_option.get("TriggerCustomString")),
                            }
                        )
                    if options:
                        events.append(("options", options))
                    continue
                if task_type == "RPG.GameCore.TriggerCustomString":
                    trigger_key = self._normalize_key(((task.get("CustomString") or {}).get("Value")))
                    if trigger_key:
                        events.append(("trigger", trigger_key))
            blocks.append(SequenceBlock(block_id=f"{source_path}:{index}", wait_key=wait_key, events=events))
        return blocks

    def _render_blocks(self, blocks: list[SequenceBlock]) -> list[MissionDialogueLine]:
        blocks_by_wait: dict[str | None, list[SequenceBlock]] = {}
        for block in blocks:
            blocks_by_wait.setdefault(block.wait_key, []).append(block)
        consumed: set[str] = set()

        def unique_keys(keys: Iterable[str]) -> list[str]:
            seen: set[str] = set()
            result: list[str] = []
            for key in keys:
                if not key or key in seen:
                    continue
                seen.add(key)
                result.append(key)
            return result

        def render_trigger_chain(trigger_key: str, allow_common_follow: bool) -> tuple[list[MissionDialogueLine], list[str]]:
            output: list[MissionDialogueLine] = []
            next_keys: list[str] = []
            queue = [trigger_key]
            while queue:
                current_key = queue.pop(0)
                for candidate in blocks_by_wait.get(current_key, []):
                    if candidate.block_id in consumed:
                        continue
                    consumed.add(candidate.block_id)
                    block_output, block_next_keys = render_single_block(candidate)
                    output.extend(block_output)
                    next_keys.extend(block_next_keys)
                deduped_next = unique_keys(next_keys)
                if allow_common_follow and len(deduped_next) == 1:
                    next_keys = []
                    queue = deduped_next
                else:
                    break
            return output, unique_keys(next_keys)

        def render_options(block: SequenceBlock, options: list[dict[str, Any]]) -> list[MissionDialogueLine]:
            option_group_id = block.block_id
            output: list[MissionDialogueLine] = []
            branch_next_keys: list[list[str]] = []
            for option_index, option in enumerate(options, start=1):
                output.append(
                    replace(
                        option["line"],
                        option_group_id=option_group_id,
                        option_index=option_index,
                    )
                )
                branch_lines: list[MissionDialogueLine] = []
                next_keys: list[str] = []
                if option.get("trigger"):
                    branch_lines, next_keys = render_trigger_chain(option["trigger"], allow_common_follow=False)
                output.extend(
                    replace(line, option_group_id=option_group_id, option_index=option_index, branch_index=option_index)
                    for line in branch_lines
                )
                branch_next_keys.append(next_keys)
            common_keys = [keys[0] for keys in branch_next_keys if len(keys) == 1]
            if branch_next_keys and len(common_keys) == len(branch_next_keys) and len(set(common_keys)) == 1:
                common_output, _ = render_trigger_chain(common_keys[0], allow_common_follow=True)
                output.extend(common_output)
            return output

        def render_single_block(block: SequenceBlock) -> tuple[list[MissionDialogueLine], list[str]]:
            output: list[MissionDialogueLine] = []
            next_keys: list[str] = []
            for event_type, payload in block.events:
                if event_type == "lines":
                    output.extend(payload)
                elif event_type == "options":
                    output.extend(render_options(block, payload))
                elif event_type == "trigger":
                    next_keys.append(payload)
            return output, unique_keys(next_keys)

        rendered: list[MissionDialogueLine] = []
        for block in blocks_by_wait.get(None, []):
            if block.block_id in consumed:
                continue
            consumed.add(block.block_id)
            block_output, next_keys = render_single_block(block)
            rendered.extend(block_output)
            for next_key in next_keys:
                chain_output, _ = render_trigger_chain(next_key, allow_common_follow=True)
                rendered.extend(chain_output)
        return rendered

    def _render_file_dialogues(self, source_path: str) -> list[MissionDialogueLine]:
        obj = self._read_json(source_path)
        if not isinstance(obj, dict):
            return []
        return self._render_blocks(self._parse_sequence_blocks(obj, self._relative_path(source_path)))

    def _normalize_key(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        return text.replace("\\", "/")

    def _extract_graph_reference_ids(self, obj: dict[str, Any]) -> tuple[list[int], list[int]]:
        talk_ids: list[int] = []
        talk_sentence_ids: list[int] = []
        seen_talk_ids: set[int] = set()
        seen_talk_sentence_ids: set[int] = set()

        def record_reference(raw_value: Any) -> None:
            key = self._normalize_key(raw_value)
            if not key:
                return
            talk_match = re.fullmatch(r"Talk_(\d+)", key)
            if talk_match:
                talk_id = int(talk_match.group(1))
                if talk_id not in seen_talk_ids:
                    seen_talk_ids.add(talk_id)
                    talk_ids.append(talk_id)
                return
            sentence_match = re.fullmatch(r"TalkSentence_(\d+)", key)
            if sentence_match:
                sentence_id = int(sentence_match.group(1))
                if sentence_id not in seen_talk_sentence_ids:
                    seen_talk_sentence_ids.add(sentence_id)
                    talk_sentence_ids.append(sentence_id)

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                custom_string = node.get("CustomString")
                if isinstance(custom_string, dict):
                    record_reference(custom_string.get("Value"))
                record_reference(node.get("TriggerCustomString"))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(obj)
        return talk_ids, talk_sentence_ids

    def _get_all_mission_graph_paths(self, mission_id: int) -> list[str]:
        cached_paths = self.mission_graph_paths_by_main_id.get(mission_id)
        if cached_paths is not None:
            return list(cached_paths)

        base_dir = f"Config/Level/Mission/{mission_id}"
        patterns = [
            f"{base_dir}/Mission_*.json",
            f"{base_dir}/Act/Act*.json",
            f"{base_dir}/Act*.json",
            f"{base_dir}/CS*.json",
            f"{base_dir}/Talk/Talk_*.json",
        ]
        paths: list[str] = []
        seen: set[str] = set()
        for pattern in patterns:
            for path in sorted(self.data_root.glob(pattern), key=lambda item: str(item)):
                relative_path = self._relative_path(path)
                if not relative_path or relative_path in seen:
                    continue
                seen.add(relative_path)
                paths.append(relative_path)

        self.mission_graph_paths_by_main_id[mission_id] = list(paths)
        return list(paths)

    def _contains_talk_sentence_id(self, obj: Any, sentence_id: int) -> bool:
        if isinstance(obj, dict):
            raw_sentence_id = obj.get("TalkSentenceID")
            if self._coerce_int(raw_sentence_id) == sentence_id:
                return True
            return any(self._contains_talk_sentence_id(value, sentence_id) for value in obj.values())
        if isinstance(obj, list):
            return any(self._contains_talk_sentence_id(item, sentence_id) for item in obj)
        return False

    def _find_graph_paths_by_talk_sentence_id(self, mission_id: int, sentence_id: int) -> list[str]:
        cache_key = (mission_id, sentence_id)
        cached_paths = self.graph_paths_by_talk_sentence_key.get(cache_key)
        if cached_paths is not None:
            return list(cached_paths)

        paths: list[str] = []
        for path in self._get_all_mission_graph_paths(mission_id):
            obj = self._read_json(path)
            if not isinstance(obj, dict):
                continue
            if self._contains_talk_sentence_id(obj, sentence_id):
                paths.append(path)

        self.graph_paths_by_talk_sentence_key[cache_key] = list(paths)
        return list(paths)

    def _get_followup_paths_for_talk_id(self, mission_id: int, talk_id: int) -> list[str]:
        matched_paths = self._find_graph_paths_by_talk_sentence_id(mission_id, talk_id)
        if matched_paths:
            return matched_paths
        return [
            path
            for path in self._get_graph_paths(mission_id, talk_id, include_mission=False)
            if isinstance(self._read_json(path), dict)
        ]

    def _collect_section_content(self, mission_id: int, sub_row: dict[str, Any]) -> tuple[list[MissionDialogueLine], str, list[str]]:
        sub_id = sub_row.get("ID")
        if not isinstance(sub_id, int):
            return [], "", []

        reasons: list[str] = []
        dialogue_lines: list[MissionDialogueLine] = []
        source_paths: list[str] = []
        rendered_signatures: set[tuple[str, str]] = set()
        queued_paths: set[str] = set()
        processed_paths: set[str] = set()
        queued_talk_ids: set[int] = set()
        local_queue: deque[GraphCandidate] = deque()
        performance_queue: deque[GraphCandidate] = deque()

        def queue_paths(
            queue: deque[GraphCandidate],
            paths: Iterable[str],
            source: str,
            performance_id: int | None = None,
            performance_type: str = "",
        ) -> None:
            for path in paths:
                relative_path = self._relative_path(path)
                if not relative_path or relative_path in queued_paths:
                    continue
                queued_paths.add(relative_path)
                source_paths.append(relative_path)
                queue.append(GraphCandidate(relative_path, source, performance_id, performance_type))

        def append_rendered(path: str, rendered: list[MissionDialogueLine]) -> None:
            if not rendered:
                return
            signature = (path, "|".join(f"{line.line_type}:{line.talk_sentence_id}:{line.text_hash}" for line in rendered))
            if signature in rendered_signatures:
                return
            rendered_signatures.add(signature)
            dialogue_lines.extend(rendered)

        def process_queue(queue: deque[GraphCandidate], *, allow_followup: bool) -> None:
            while queue:
                candidate = queue.popleft()
                if candidate.path in processed_paths:
                    continue
                processed_paths.add(candidate.path)
                obj = self._read_json(candidate.path)
                if not isinstance(obj, dict):
                    if candidate.source == "performance":
                        reasons.append(f"PerformanceID={candidate.performance_id} 资源缺失：{candidate.path}")
                    continue
                rendered = self._render_file_dialogues(candidate.path)
                append_rendered(candidate.path, rendered)
                if not rendered and candidate.source == "performance":
                    reasons.append(f"PerformanceID={candidate.performance_id} 未包含可稳定提取台词：{candidate.path}")
                if not allow_followup:
                    continue
                talk_ids, _ = self._extract_graph_reference_ids(obj)
                for talk_id in talk_ids:
                    if talk_id in queued_talk_ids:
                        continue
                    queued_talk_ids.add(talk_id)
                    existing_paths = self._get_followup_paths_for_talk_id(mission_id, talk_id)
                    if existing_paths:
                        queue_paths(local_queue, existing_paths, "sibling")
                    else:
                        reasons.append(f"引用了 Talk_{talk_id}，但同任务目录内未找到对应图文件")

        direct_paths: list[str] = []
        mission_json_path = sub_row.get("MissionJsonPath")
        if isinstance(mission_json_path, str):
            direct_paths.append(self._relative_path(mission_json_path))
        direct_paths.extend(self._get_graph_paths(mission_id, sub_id))
        queue_paths(local_queue, direct_paths, "local")
        process_queue(local_queue, allow_followup=True)

        for performance_id in self.linked_performance_ids_by_sub_id.get(sub_id, []):
            performance_path = self.performance_paths_by_id.get(performance_id)
            if not performance_path:
                reasons.append(f"PerformanceID={performance_id} 缺少对应路径")
                continue
            queue_paths(
                performance_queue,
                [performance_path],
                "performance",
                performance_id,
                self.performance_type_by_id.get(performance_id, ""),
            )
        process_queue(performance_queue, allow_followup=False)

        for line in self._get_tutorial_section_lines(sub_id):
            key = f"{line.line_type}:{line.text_hash}:{line.text_content}"
            if key not in {f"{item.line_type}:{item.text_hash}:{item.text_content}" for item in dialogue_lines}:
                dialogue_lines.append(line)

        resource_note = "；".join(dict.fromkeys(reasons))
        return dialogue_lines, resource_note, source_paths

    def _get_tutorial_section_lines(self, sub_id: int) -> list[MissionDialogueLine]:
        lines: list[MissionDialogueLine] = []
        seen: set[str] = set()

        def append_line(line: MissionDialogueLine | None) -> None:
            if not line:
                return
            key = line.text_hash or line.text_content or ""
            if not key or key in seen:
                return
            seen.add(key)
            lines.append(line)

        for group_row in self.tutorial_guide_groups_by_sub_id.get(sub_id, []):
            append_line(self._text_value_to_line("ExcelOutput/TutorialGuideGroup.json", group_row.get("MessageText")))
            raw_ids = group_row.get("TutorialGuideIDList") or []
            if not isinstance(raw_ids, list):
                continue
            for raw_id in raw_ids:
                guide_id = self._coerce_int(raw_id)
                guide_row = self.tutorial_guide_data_by_id.get(guide_id or -1) or {}
                append_line(self._text_value_to_line("ExcelOutput/TutorialGuideData.json", guide_row.get("DescText")))

        for tutorial_row in self.tutorial_data_by_sub_id.get(sub_id, []):
            tutorial_path = tutorial_row.get("TutorialJsonPath")
            if not isinstance(tutorial_path, str):
                continue
            obj = self._read_json(tutorial_path)
            if not isinstance(obj, dict):
                continue
            def walk(node: Any) -> None:
                if isinstance(node, dict):
                    if node.get("$type") == "RPG.GameCore.ShowGuideHintWithText":
                        guide_talk_id = self._coerce_int(node.get("GuideTalkID"))
                        guide_talk_row = self.tutorial_guide_talk_by_id.get(guide_talk_id or -1) or {}
                        append_line(self._text_value_to_line(self._relative_path(tutorial_path), guide_talk_row.get("TalkDataText")))
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for item in node:
                        walk(item)
            walk(obj)
        return lines

    def extract_mission(self, mission_id: int) -> MissionDialogueContext:
        mission_info = self._get_mission_info(mission_id)
        sub_rows = self._build_sub_rows(mission_id, mission_info)
        sections: list[MissionDialogueSection] = []
        story_paths: list[str] = []
        seen_paths: set[str] = set()
        for index, sub_row in enumerate(sub_rows, start=1):
            sub_id = sub_row.get("ID")
            if not isinstance(sub_id, int):
                continue
            sub_config = self.sub_missions_by_id.get(sub_id) or {}
            lines, resource_note, source_paths = self._collect_section_content(mission_id, sub_row)
            for path in source_paths:
                if path not in seen_paths:
                    seen_paths.add(path)
                    story_paths.append(path)
            sections.append(
                MissionDialogueSection(
                    section_id=sub_id,
                    order=index,
                    title_hash=self._hash_ref((sub_config.get("TargetText") or {}).get("Hash")),
                    fallback_title=f"子任务 {sub_id}",
                    description_hash=self._hash_ref((sub_config.get("DescrptionText") or {}).get("Hash")),
                    location="",
                    resource_note=resource_note,
                    lines=lines,
                )
            )
        return MissionDialogueContext(mission_id=mission_id, story_paths=story_paths, sections=sections)
