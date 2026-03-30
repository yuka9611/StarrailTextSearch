from __future__ import annotations

from collections import OrderedDict
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from data_paths import DATA_ROOT, DB_PATH
from dbBuild.builder import (
    StarrailDatabaseBuilder,
    extract_talk_sentence_refs,
    hash_text,
    normalize_hash,
    parse_version,
)


TEXTMAP_NORMAL_PREFIX = "TextMap"
TEXTMAP_MAIN_PREFIX = "TextMapMain"
TRACKED_TABLES = [
    "text_map",
    "mission",
    "book",
    "message_thread",
    "voice_entry",
    "story_entry",
    "source_record",
    "entity_search",
]
ENTITY_KIND_TO_TABLE = {
    "mission": ("mission", "mission_id"),
    "book": ("book", "book_id"),
    "message": ("message_thread", "thread_id"),
    "voice": ("voice_entry", "entry_key"),
    "story": ("story_entry", "entry_key"),
}
UPDATE_BATCH_SIZE = 5000
BACKFILL_STATUS_KEY = "history_backfill.status"
BACKFILL_VERSION_KEY = "history_backfill.version_tag"
BACKFILL_TEXT_GROUPS_KEY = "history_backfill.completed_text_groups"
BACKFILL_ENTITIES_DONE_KEY = "history_backfill.entities_done"
BACKFILL_STATUS_IN_PROGRESS = "in_progress"
BACKFILL_STATUS_COMPLETE = "complete"
SNAPSHOT_TEXT_GROUP_CACHE_LIMIT = 2

_snapshot_textmap_file_groups_cache: dict[tuple[str, str], dict[tuple[str, str], list[str]]] = {}
_snapshot_textmap_group_cache: OrderedDict[tuple[str, str, str, str], dict[str, str] | None] = OrderedDict()


def _log(verbose: bool, message: str) -> None:
    if verbose:
        print(message)


def _set_app_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO app_meta(k, v) VALUES (?, ?)
        ON CONFLICT(k) DO UPDATE SET v=excluded.v
        """,
        (key, value),
    )


def _get_app_meta(connection: sqlite3.Connection, key: str) -> str:
    row = connection.execute("SELECT v FROM app_meta WHERE k=?", (key,)).fetchone()
    return str(row[0]) if row else ""


def _persist_backfill_progress(
    connection: sqlite3.Connection,
    *,
    current_version_tag: str,
    completed_groups: set[str],
    entities_done: bool,
    status: str,
) -> None:
    _set_app_meta(connection, BACKFILL_STATUS_KEY, status)
    _set_app_meta(connection, BACKFILL_VERSION_KEY, current_version_tag)
    _set_app_meta(connection, BACKFILL_TEXT_GROUPS_KEY, json.dumps(sorted(completed_groups), ensure_ascii=False))
    _set_app_meta(connection, BACKFILL_ENTITIES_DONE_KEY, "1" if entities_done else "0")


def _load_backfill_progress(
    connection: sqlite3.Connection,
    current_version_tag: str,
) -> tuple[bool, bool, set[str]]:
    status = _get_app_meta(connection, BACKFILL_STATUS_KEY)
    version_tag = _get_app_meta(connection, BACKFILL_VERSION_KEY)
    if status != BACKFILL_STATUS_IN_PROGRESS or version_tag != current_version_tag:
        return False, False, set()

    completed_groups: set[str]
    try:
        completed_groups = {
            str(item)
            for item in json.loads(_get_app_meta(connection, BACKFILL_TEXT_GROUPS_KEY) or "[]")
            if str(item)
        }
    except json.JSONDecodeError:
        completed_groups = set()
    entities_done = _get_app_meta(connection, BACKFILL_ENTITIES_DONE_KEY) == "1"
    return True, entities_done, completed_groups


def _serialize_text_group(scope: str, lang: str) -> str:
    return f"{scope}/{lang}"


def _parse_textmap_group(filename: str) -> tuple[str, str] | None:
    if filename.startswith(TEXTMAP_MAIN_PREFIX) and filename.endswith(".json"):
        language = filename[len(TEXTMAP_MAIN_PREFIX) : -5]
        return ("main", language.split("_", 1)[0].lower())
    if filename.startswith(TEXTMAP_NORMAL_PREFIX) and filename.endswith(".json"):
        suffix = filename[len(TEXTMAP_NORMAL_PREFIX) : -5]
        if suffix.startswith("Main"):
            return None
        return ("normal", suffix.split("_", 1)[0].lower())
    return None


def _run_git(repo_path: Path, args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout or ""


def _git_show_text(repo_path: Path, commit: str, rel_path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", f"{commit}:{rel_path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _git_show_json(repo_path: Path, commit: str, rel_path: str) -> dict[str, Any] | list[Any] | None:
    raw = _git_show_text(repo_path, commit, rel_path)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _remember_snapshot_textmap_group(
    key: tuple[str, str, str, str],
    value: dict[str, str] | None,
) -> None:
    _snapshot_textmap_group_cache[key] = value
    _snapshot_textmap_group_cache.move_to_end(key)
    while len(_snapshot_textmap_group_cache) > SNAPSHOT_TEXT_GROUP_CACHE_LIMIT:
        _snapshot_textmap_group_cache.popitem(last=False)


def _filter_snapshot_textmap_group(
    snapshot: dict[str, str] | None,
    target_hashes: set[int | str] | None,
) -> dict[str, str]:
    if snapshot is None:
        return {}
    if target_hashes is None:
        return snapshot
    pending = {str(value) for value in target_hashes}
    if not pending:
        return {}
    return {text_hash: content for text_hash, content in snapshot.items() if text_hash in pending}


def _list_snapshot_textmap_groups(
    repo_path: Path,
    commit: str,
) -> dict[tuple[str, str], list[str]]:
    cache_key = (str(repo_path), commit)
    cached = _snapshot_textmap_file_groups_cache.get(cache_key)
    if cached is not None:
        return cached

    groups: dict[tuple[str, str], list[str]] = {}
    for rel_path in _run_git(repo_path, ["ls-tree", "-r", "--name-only", commit, "--", "TextMap"], check=False).splitlines():
        rel_path = rel_path.strip()
        if not rel_path:
            continue
        parsed = _parse_textmap_group(Path(rel_path).name)
        if not parsed:
            continue
        groups.setdefault(parsed, []).append(rel_path)

    for group_paths in groups.values():
        group_paths.sort()
    _snapshot_textmap_file_groups_cache[cache_key] = groups
    return groups


def _load_snapshot_textmap_group(
    repo_path: Path,
    commit: str,
    scope: str,
    lang: str,
    *,
    target_hashes: set[int | str] | None = None,
) -> dict[str, str]:
    cache_key = (str(repo_path), commit, scope, lang)
    cached = _snapshot_textmap_group_cache.get(cache_key)
    if cached is not None or cache_key in _snapshot_textmap_group_cache:
        return _filter_snapshot_textmap_group(cached, target_hashes)

    merged: dict[str, str] = {}
    matched = False
    for rel_path in _list_snapshot_textmap_groups(repo_path, commit).get((scope, lang), []):
        payload = _git_show_json(repo_path, commit, rel_path)
        if not isinstance(payload, dict):
            continue
        for text_hash, content in payload.items():
            if isinstance(content, str):
                merged[str(text_hash)] = content
                matched = True

    result = merged if matched else None
    _remember_snapshot_textmap_group(cache_key, result)
    return _filter_snapshot_textmap_group(result, target_hashes)


@dataclass(slots=True)
class VersionCheckpoint:
    version_tag: str
    raw_version: str
    sort_key: int
    commit: str


@dataclass(frozen=True, slots=True)
class VersionSnapshot:
    version_tag: str
    raw_version: str
    sort_key: int
    commit: str
    version_id: int


@dataclass(frozen=True, slots=True)
class SnapshotReplayRange:
    snapshots: tuple[VersionSnapshot, ...]
    target_snapshot: VersionSnapshot | None
    commit_to_version_tag: dict[str, str | None]


@dataclass(slots=True)
class TalkSentenceLite:
    speaker_hash: str | None
    text_hash: str | None


@dataclass(slots=True)
class TrackingSet:
    mission_ids: list[int]
    book_ids: list[int]
    thread_ids: list[int]
    voice_keys: list[str]
    story_keys: list[str]
    text_groups: list[tuple[str, str]]


class VersionTracker:
    def __init__(self, final_values: dict[int | str, str]):
        self.final_values = dict(final_values)
        self.keys = list(final_values.keys())
        self.created: dict[int | str, str] = {}
        self.updated: dict[int | str, str] = {}
        self.pending_created: set[int | str] = set(final_values.keys())
        self.pending_updated: set[int | str] = set(final_values.keys())

    def observe(self, values: dict[int | str, str], version_tag: str) -> None:
        for key, value in values.items():
            final_value = self.final_values.get(key)
            if final_value is None:
                continue
            if key in self.pending_created:
                self.created[key] = version_tag
                self.pending_created.discard(key)
            if key in self.pending_updated and value == final_value:
                self.updated[key] = version_tag
                self.pending_updated.discard(key)

    def pending_keys(self) -> set[int | str]:
        return self.pending_created | self.pending_updated

    def missing_created_keys(self) -> set[int | str]:
        return set(self.pending_created)

    def finalize(self, current_version_tag: str) -> dict[str, int]:
        stats = {
            "created_fallback_to_current": 0,
            "updated_fallback_to_created": 0,
        }
        for key in self.keys:
            if key not in self.created:
                self.created[key] = current_version_tag
                stats["created_fallback_to_current"] += 1
            if key not in self.updated:
                self.updated[key] = self.created[key]
                stats["updated_fallback_to_created"] += 1
        self.pending_created.clear()
        self.pending_updated.clear()
        return stats

    def version_pair(self, key: int | str) -> tuple[str, str]:
        return self.created[key], self.updated[key]


class SnapshotLoader:
    def __init__(self, root: Path, tracking: TrackingSet):
        self.root = root
        self.excel_root = root / "ExcelOutput"
        self.story_root = root / "Story"
        self.textmap_root = root / "TextMap"
        self.tracking = tracking
        self._textmap_files: dict[tuple[str, str], list[Path]] | None = None

    def load_entity_snapshot(self) -> dict[str, dict[int | str, str]]:
        talk_sentence_map = self._load_talk_sentence_map()
        return {
            "mission": self._load_missions(talk_sentence_map),
            "book": self._load_books(),
            "message": self._load_messages(),
            "voice": self._load_voices(),
            "story": self._load_stories(),
        }

    def load_text_map_group(
        self,
        scope: str,
        lang: str,
        *,
        target_hashes: set[int | str] | None = None,
    ) -> dict[str, str]:
        if target_hashes is not None and not target_hashes:
            return {}

        file_paths = self._get_textmap_files(scope, lang)
        if not file_paths:
            return {}

        pending = {str(value) for value in target_hashes} if target_hashes is not None else None
        snapshot: dict[str, str] = {}
        for file_path in file_paths:
            payload = self._load_json(file_path, {})
            if not isinstance(payload, dict):
                continue
            matched_hashes: list[str] = []
            for text_hash, content in payload.items():
                key = str(text_hash)
                if pending is not None and key not in pending:
                    continue
                if not isinstance(content, str):
                    continue
                snapshot[key] = hash_text(content)
                matched_hashes.append(key)
            if pending is not None:
                for key in matched_hashes:
                    pending.discard(key)
                if not pending:
                    break
        return snapshot

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _load_talk_sentence_map(self) -> dict[int, TalkSentenceLite]:
        rows = self._load_json(self.excel_root / "TalkSentenceConfig.json", [])
        result: dict[int, TalkSentenceLite] = {}
        for row in rows:
            talk_sentence_id = row.get("TalkSentenceID")
            if talk_sentence_id is None:
                continue
            result[int(talk_sentence_id)] = TalkSentenceLite(
                speaker_hash=normalize_hash(row.get("TextmapTalkSentenceName")),
                text_hash=normalize_hash(row.get("TalkSentenceText")),
            )
        return result

    def _load_missions(self, talk_sentence_map: dict[int, TalkSentenceLite]) -> dict[int, str]:
        mission_root = self.story_root / "Mission"
        if not mission_root.is_dir():
            return {}

        mission_name_hash: dict[int, str | None] = {}
        for row in self._load_json(self.excel_root / "MainMission.json", []):
            mission_id = row.get("MainMissionID")
            if mission_id is None:
                continue
            mission_name_hash[int(mission_id)] = normalize_hash(row.get("Name"))

        tracked_ids = set(self.tracking.mission_ids)
        snapshot: dict[int, str] = {}
        for mission_dir in sorted(mission_root.iterdir()):
            if not mission_dir.is_dir():
                continue
            try:
                mission_id = int(mission_dir.name)
            except ValueError:
                continue
            if mission_id not in tracked_ids:
                continue

            story_paths: list[str] = []
            lines: list[tuple[str, str, int, str | None, str | None]] = []
            for story_path in sorted(mission_dir.glob("*.json")):
                relative_path = str(story_path.relative_to(self.root))
                story_paths.append(relative_path)
                payload = self._load_json(story_path, {})
                for talk_sentence_id, line_type in extract_talk_sentence_refs(payload):
                    talk_sentence = talk_sentence_map.get(int(talk_sentence_id))
                    lines.append(
                        (
                            relative_path,
                            str(line_type),
                            int(talk_sentence_id),
                            talk_sentence.speaker_hash if talk_sentence else None,
                            talk_sentence.text_hash if talk_sentence else None,
                        )
                    )

            if not story_paths and not lines and mission_id not in mission_name_hash:
                continue
            snapshot[mission_id] = hash_text(
                {
                    "mission_id": mission_id,
                    "mission_type": "main",
                    "name_hash": mission_name_hash.get(mission_id),
                    "story_paths": story_paths,
                    "lines": lines,
                }
            )
        return snapshot

    def _load_books(self) -> dict[int, str]:
        tracked_ids = set(self.tracking.book_ids)
        series_map: dict[int, dict[str, Any]] = {}
        for row in self._load_json(self.excel_root / "BookSeriesConfig.json", []):
            series_id = row.get("BookSeriesID")
            if series_id is None:
                continue
            series_map[int(series_id)] = row

        snapshot: dict[int, str] = {}
        for row in self._load_json(self.excel_root / "LocalbookConfig.json", []):
            book_id = row.get("BookID")
            if book_id is None:
                continue
            book_id = int(book_id)
            if book_id not in tracked_ids:
                continue
            series = series_map.get(int(row.get("BookSeriesID") or 0), {})
            snapshot[book_id] = hash_text(
                {
                    "book_id": book_id,
                    "series_id": int(row.get("BookSeriesID") or 0),
                    "inside_id": int(row.get("BookSeriesInsideID") or 0),
                    "world_id": int(series.get("BookSeriesWorld") or 0),
                    "series_name_hash": normalize_hash(series.get("BookSeries")),
                    "series_comment_hash": normalize_hash(series.get("BookSeriesComments")),
                    "title_hash": normalize_hash(row.get("BookInsideName")),
                    "content_hash": normalize_hash(row.get("BookContent")),
                    "display_type": int(row.get("BookDisplayType") or 0),
                }
            )
        return snapshot

    def _load_messages(self) -> dict[int, str]:
        tracked_ids = set(self.tracking.thread_ids)
        contacts_by_id = {
            int(row.get("ID")): row
            for row in self._load_json(self.excel_root / "MessageContactsConfig.json", [])
            if row.get("ID") is not None
        }
        sections_by_id = {
            int(row.get("ID")): row
            for row in self._load_json(self.excel_root / "MessageSectionConfig.json", [])
            if row.get("ID") is not None
        }
        items_by_section: dict[int, list[dict[str, Any]]] = {}
        for row in self._load_json(self.excel_root / "MessageItemConfig.json", []):
            section_id = row.get("SectionID")
            item_id = row.get("ID")
            if section_id is None or item_id is None:
                continue
            items_by_section.setdefault(int(section_id), []).append(row)

        snapshot: dict[int, str] = {}
        for row in self._load_json(self.excel_root / "MessageGroupConfig.json", []):
            thread_id = row.get("ID")
            if thread_id is None:
                continue
            thread_id = int(thread_id)
            if thread_id not in tracked_ids:
                continue

            contact_id = int(row.get("MessageContactsID") or 0)
            contact = contacts_by_id.get(contact_id, {})
            section_ids = [int(value) for value in row.get("MessageSectionIDList", []) or [] if value is not None]
            contacts_type = int(contact.get("ContactsType") or 0)
            thread_type = "group" if contacts_type == 3 else "system" if contacts_type == 2 else "contact"

            latest_preview_hash = None
            linked_main_mission_id = None
            message_count = 0
            item_order = 0
            section_payloads: list[dict[str, Any]] = []

            for section_id in section_ids:
                section = sections_by_id.get(section_id, {})
                start_item_ids = [int(value) for value in section.get("StartMessageItemIDList", []) or [] if value is not None]
                section_main_mission = int(section.get("MainMissionLink") or 0) or None
                if linked_main_mission_id is None:
                    linked_main_mission_id = section_main_mission
                ordered_items = sorted(
                    items_by_section.get(section_id, []),
                    key=lambda item: int(item.get("ID") or 0),
                )
                item_payloads: list[dict[str, Any]] = []
                for item in ordered_items:
                    main_hash = normalize_hash(item.get("MainText"))
                    option_hash = normalize_hash(item.get("OptionText"))
                    if main_hash:
                        latest_preview_hash = main_hash
                    if main_hash or option_hash:
                        message_count += 1
                    item_payloads.append(
                        {
                            "item_id": int(item.get("ID")),
                            "sender": str(item.get("Sender") or ""),
                            "item_type": str(item.get("ItemType") or ""),
                            "main_text_hash": main_hash,
                            "option_text_hash": option_hash,
                            "next_item_ids": [int(value) for value in item.get("NextItemIDList", []) or [] if value is not None],
                            "item_content_id": int(item["ItemContentID"]) if item.get("ItemContentID") is not None else None,
                            "item_order": item_order,
                        }
                    )
                    item_order += 1
                section_payloads.append(
                    {
                        "section_id": section_id,
                        "linked_main_mission_id": section_main_mission,
                        "start_item_ids": start_item_ids,
                        "items": item_payloads,
                    }
                )

            snapshot[thread_id] = hash_text(
                {
                    "thread_id": thread_id,
                    "contact_id": contact_id or None,
                    "display_name_hash": normalize_hash(contact.get("Name")),
                    "signature_hash": normalize_hash(contact.get("SignatureText")),
                    "icon_path": str(contact.get("IconPath") or ""),
                    "thread_type": thread_type,
                    "camp": int(contact.get("ContactsCamp") or 0) or None,
                    "linked_main_mission_id": linked_main_mission_id,
                    "message_count": message_count,
                    "latest_preview_hash": latest_preview_hash,
                    "sections": section_payloads,
                }
            )
        return snapshot

    def _load_voices(self) -> dict[str, str]:
        tracked_keys = set(self.tracking.voice_keys)
        voice_path_by_id = {
            int(row.get("VoiceID")): str(row.get("VoicePath") or "")
            for row in self._load_json(self.excel_root / "VoiceConfig.json", [])
            if row.get("VoiceID") is not None
        }

        snapshot: dict[str, str] = {}
        for row in self._load_json(self.excel_root / "VoiceAtlas.json", []):
            avatar_id = row.get("AvatarID")
            voice_id = row.get("VoiceID")
            if avatar_id is None or voice_id is None:
                continue
            entry_key = f"{int(avatar_id)}:{int(voice_id)}"
            if entry_key not in tracked_keys:
                continue
            audio_id = int(row["AudioID"]) if row.get("AudioID") is not None else None
            snapshot[entry_key] = hash_text(
                {
                    "entry_key": entry_key,
                    "avatar_id": int(avatar_id),
                    "voice_id": int(voice_id),
                    "title_hash": normalize_hash(row.get("VoiceTitle")),
                    "text_hash_m": normalize_hash(row.get("Voice_M")),
                    "text_hash_f": normalize_hash(row.get("Voice_F")),
                    "audio_id": audio_id,
                    "voice_path": voice_path_by_id.get(audio_id or 0) or voice_path_by_id.get(int(voice_id)) or "",
                    "sort_id": int(row.get("SortID") or 0),
                }
            )
        return snapshot

    def _load_stories(self) -> dict[str, str]:
        tracked_keys = set(self.tracking.story_keys)
        title_hash_by_story_id = {
            int(row.get("StoryID")): normalize_hash(row.get("StoryName"))
            for row in self._load_json(self.excel_root / "StoryAtlasTextmap.json", [])
            if row.get("StoryID") is not None
        }

        snapshot: dict[str, str] = {}
        for row in self._load_json(self.excel_root / "StoryAtlas.json", []):
            avatar_id = row.get("AvatarID")
            story_id = row.get("StoryID")
            if avatar_id is None or story_id is None:
                continue
            entry_key = f"{int(avatar_id)}:{int(story_id)}"
            if entry_key not in tracked_keys:
                continue
            snapshot[entry_key] = hash_text(
                {
                    "entry_key": entry_key,
                    "avatar_id": int(avatar_id),
                    "story_id": int(story_id),
                    "title_hash": title_hash_by_story_id.get(int(story_id)),
                    "content_hash": normalize_hash(row.get("Story")),
                    "unlock_id": int(row["Unlock"]) if row.get("Unlock") is not None else None,
                    "sort_id": int(row.get("SortID") or 0),
                }
            )
        return snapshot

    def _get_textmap_files(self, scope: str, lang: str) -> list[Path]:
        if self._textmap_files is None:
            grouped: dict[tuple[str, str], list[Path]] = {}
            if self.textmap_root.is_dir():
                for path in sorted(self.textmap_root.iterdir()):
                    if not path.is_file():
                        continue
                    parsed = self._parse_textmap_group(path.name)
                    if not parsed:
                        continue
                    grouped.setdefault(parsed, []).append(path)
            self._textmap_files = grouped
        return self._textmap_files.get((scope, lang), [])

    def _parse_textmap_group(self, filename: str) -> tuple[str, str] | None:
        return _parse_textmap_group(filename)


def ensure_history_available() -> None:
    try:
        shallow = subprocess.run(
            ["git", "-C", str(DATA_ROOT), "rev-parse", "--is-shallow-repository"],
            check=True,
            capture_output=True,
            text=True,
        )
        count = subprocess.run(
            ["git", "-C", str(DATA_ROOT), "rev-list", "--count", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as error:
        raise RuntimeError(f"无法检查数据仓库历史：{error}") from error

    is_shallow = (shallow.stdout or "").strip().lower() == "true"
    commit_count = int((count.stdout or "0").strip() or "0")
    if is_shallow or commit_count <= 1:
        raise RuntimeError(
            "当前 turnbasedgamedata 是浅克隆或历史不足，无法执行历史回填。"
            "请先补全 git 历史后再运行本脚本。"
        )


def _collect_version_history_rows() -> list[tuple[str, str]]:
    result = _run_git(DATA_ROOT, ["log", "--format=%H\t%s", "--reverse"])
    rows: list[tuple[str, str]] = []
    for line in result.splitlines():
        if not line.strip():
            continue
        commit, raw_version = line.split("\t", 1)
        rows.append((commit, raw_version))
    return rows


def collect_version_checkpoints(history_rows: list[tuple[str, str]] | None = None) -> list[VersionCheckpoint]:
    if history_rows is None:
        history_rows = _collect_version_history_rows()
    checkpoints_by_tag: dict[str, VersionCheckpoint] = {}
    ordered_tags: list[str] = []
    for commit, raw_version in history_rows:
        version_tag, sort_key = parse_version(raw_version)
        if sort_key <= 0:
            continue
        checkpoint = VersionCheckpoint(
            version_tag=version_tag,
            raw_version=raw_version,
            sort_key=sort_key,
            commit=commit,
        )
        if version_tag not in checkpoints_by_tag:
            ordered_tags.append(version_tag)
        checkpoints_by_tag[version_tag] = checkpoint
    checkpoints = [checkpoints_by_tag[tag] for tag in ordered_tags]
    if not checkpoints:
        raise RuntimeError("未能从 git 历史中解析出任何有效版本。")
    return checkpoints


def build_snapshot_replay_range(
    history_rows: list[tuple[str, str]],
    version_id_by_tag: dict[str, int],
) -> SnapshotReplayRange:
    commit_to_version_tag: dict[str, str | None] = {}
    snapshots_by_tag: dict[str, VersionSnapshot] = {}
    ordered_tags: list[str] = []
    current_tag: str | None = None

    for commit, raw_version in history_rows:
        version_tag, sort_key = parse_version(raw_version)
        if sort_key > 0:
            current_tag = version_tag
            if version_tag not in ordered_tags:
                ordered_tags.append(version_tag)
            version_id = version_id_by_tag.get(version_tag)
            if version_id is None:
                continue
            snapshots_by_tag[version_tag] = VersionSnapshot(
                version_tag=version_tag,
                raw_version=raw_version,
                sort_key=sort_key,
                commit=commit,
                version_id=version_id,
            )
        commit_to_version_tag[commit] = current_tag

    snapshots = tuple(
        snapshots_by_tag[version_tag]
        for version_tag in ordered_tags
        if version_tag in snapshots_by_tag
    )
    return SnapshotReplayRange(
        snapshots=snapshots,
        target_snapshot=snapshots[-1] if snapshots else None,
        commit_to_version_tag=commit_to_version_tag,
    )


def load_tracking_set(connection: sqlite3.Connection) -> TrackingSet:
    mission_ids = [int(row[0]) for row in connection.execute("SELECT mission_id FROM mission ORDER BY mission_id")]
    book_ids = [int(row[0]) for row in connection.execute("SELECT book_id FROM book ORDER BY book_id")]
    thread_ids = [int(row[0]) for row in connection.execute("SELECT thread_id FROM message_thread ORDER BY thread_id")]
    voice_keys = [str(row[0]) for row in connection.execute("SELECT entry_key FROM voice_entry ORDER BY entry_key")]
    story_keys = [str(row[0]) for row in connection.execute("SELECT entry_key FROM story_entry ORDER BY entry_key")]
    text_groups = [
        (str(row[0]), str(row[1]))
        for row in connection.execute("SELECT DISTINCT scope, lang FROM text_map ORDER BY scope, lang")
    ]
    return TrackingSet(
        mission_ids=mission_ids,
        book_ids=book_ids,
        thread_ids=thread_ids,
        voice_keys=voice_keys,
        story_keys=story_keys,
        text_groups=text_groups,
    )


def clone_history_repo() -> Path:
    clone_root = Path(tempfile.mkdtemp(prefix="sts-history-backfill-"))
    repo_path = clone_root / "turnbasedgamedata"
    try:
        subprocess.run(
            ["git", "clone", "--shared", "--no-checkout", str(DATA_ROOT), str(repo_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        shutil.rmtree(clone_root, ignore_errors=True)
        raise
    return repo_path


def checkout_commit(repo_path: Path, commit: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo_path), "checkout", "--force", "--quiet", commit],
        check=True,
        capture_output=True,
        text=True,
    )


def rebuild_version_dim(
    connection: sqlite3.Connection,
    checkpoints: list[VersionCheckpoint],
) -> tuple[dict[str, int], int]:
    connection.execute("DELETE FROM version_dim")
    connection.execute("DELETE FROM sqlite_sequence WHERE name='version_dim'")
    connection.executemany(
        """
        INSERT INTO version_dim(id, raw_version, version_tag, version_sort_key, is_current)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                index + 1,
                checkpoint.raw_version,
                checkpoint.version_tag,
                checkpoint.sort_key,
                1 if index == len(checkpoints) - 1 else 0,
            )
            for index, checkpoint in enumerate(checkpoints)
        ],
    )
    version_rows = connection.execute(
        "SELECT id, version_tag FROM version_dim ORDER BY version_sort_key ASC, id ASC"
    ).fetchall()
    version_id_by_tag = {str(row[1]): int(row[0]) for row in version_rows}
    current_checkpoint = checkpoints[-1]
    for key, value in [
        ("current_raw_version", current_checkpoint.raw_version),
        ("current_version_tag", current_checkpoint.version_tag),
    ]:
        connection.execute(
            """
            INSERT INTO app_meta(k, v) VALUES (?, ?)
            ON CONFLICT(k) DO UPDATE SET v=excluded.v
            """,
            (key, value),
        )
    return version_id_by_tag, version_id_by_tag[current_checkpoint.version_tag]


def reset_version_columns(connection: sqlite3.Connection, current_version_id: int) -> None:
    for table in TRACKED_TABLES:
        connection.execute(
            f"UPDATE {table} SET created_version_id=?, updated_version_id=?",
            (current_version_id, current_version_id),
        )


def load_current_text_map_group(
    connection: sqlite3.Connection,
    scope: str,
    lang: str,
) -> tuple[dict[str, int], dict[str, str]]:
    row_id_by_hash: dict[str, int] = {}
    final_values: dict[str, str] = {}
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT id, hash, content FROM text_map WHERE scope=? AND lang=? ORDER BY id",
            (scope, lang),
        )
        while True:
            rows = cursor.fetchmany(UPDATE_BATCH_SIZE)
            if not rows:
                break
            for row_id, text_hash, content in rows:
                key = str(text_hash)
                row_id_by_hash[key] = int(row_id)
                final_values[key] = str(content)
    finally:
        cursor.close()
    return row_id_by_hash, final_values


def update_version_pairs(
    connection: sqlite3.Connection,
    table: str,
    key_column: str,
    tracker: VersionTracker,
    version_id_by_tag: dict[str, int],
) -> None:
    rows = [
        (
            version_id_by_tag[tracker.version_pair(key)[0]],
            version_id_by_tag[tracker.version_pair(key)[1]],
            key,
        )
        for key in tracker.keys
    ]
    connection.executemany(
        f"UPDATE {table} SET created_version_id=?, updated_version_id=? WHERE {key_column}=?",
        rows,
    )


def update_text_map_versions(
    connection: sqlite3.Connection,
    row_id_by_hash: dict[str, int],
    tracker: VersionTracker,
    version_id_by_tag: dict[str, int],
) -> None:
    rows: list[tuple[int, int, int]] = []
    for text_hash, row_id in row_id_by_hash.items():
        created_tag, updated_tag = tracker.version_pair(text_hash)
        rows.append((version_id_by_tag[created_tag], version_id_by_tag[updated_tag], row_id))
        if len(rows) >= UPDATE_BATCH_SIZE:
            connection.executemany(
                "UPDATE text_map SET created_version_id=?, updated_version_id=? WHERE id=?",
                rows,
            )
            rows.clear()
    if rows:
        connection.executemany(
            "UPDATE text_map SET created_version_id=?, updated_version_id=? WHERE id=?",
            rows,
        )


def rebuild_dependent_indexes(connection: sqlite3.Connection, current_version_id: int) -> None:
    builder = StarrailDatabaseBuilder(DB_PATH)
    builder._rebuild_sources(connection, current_version_id)
    builder._rebuild_entity_search(connection, current_version_id)


def verify_current_snapshot(connection: sqlite3.Connection, current_version_tag: str) -> None:
    version_rows = connection.execute(
        "SELECT version_tag, raw_version, is_current FROM version_dim ORDER BY version_sort_key ASC"
    ).fetchall()
    if not version_rows:
        raise RuntimeError("历史回填后 version_dim 为空。")
    if str(version_rows[-1][0]) != current_version_tag:
        raise RuntimeError("历史回填后的当前版本与 HEAD 不一致。")


def build_entity_trackers(
    repo_path: Path,
    checkpoints: list[VersionCheckpoint],
    tracking: TrackingSet,
) -> dict[str, VersionTracker]:
    checkout_commit(repo_path, checkpoints[-1].commit)
    final_snapshot = SnapshotLoader(repo_path, tracking).load_entity_snapshot()
    return {
        entity_kind: VersionTracker(final_snapshot[entity_kind])
        for entity_kind in ENTITY_KIND_TO_TABLE
    }


def observe_entity_versions(
    repo_path: Path,
    checkpoints: list[VersionCheckpoint],
    tracking: TrackingSet,
    trackers: dict[str, VersionTracker],
    *,
    verbose: bool = True,
) -> None:
    total = len(checkpoints)
    for index, checkpoint in enumerate(checkpoints, start=1):
        _log(verbose, f"[entities {index}/{total}] Loading {checkpoint.version_tag} from {checkpoint.raw_version}")
        checkout_commit(repo_path, checkpoint.commit)
        snapshot = SnapshotLoader(repo_path, tracking).load_entity_snapshot()
        for entity_kind, tracker in trackers.items():
            tracker.observe(snapshot[entity_kind], checkpoint.version_tag)


def finalize_entity_trackers(
    trackers: dict[str, VersionTracker],
    current_version_tag: str,
) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for entity_kind, tracker in trackers.items():
        summary[entity_kind] = tracker.finalize(current_version_tag)
    return summary


def print_entity_fallback_summary(summary: dict[str, dict[str, int]]) -> None:
    for entity_kind in ENTITY_KIND_TO_TABLE:
        stats = summary.get(entity_kind, {})
        print(
            f"Entity fallback {entity_kind}: "
            f"created->current={stats.get('created_fallback_to_current', 0)}, "
            f"updated->created={stats.get('updated_fallback_to_created', 0)}"
        )


def backfill_text_map_group(
    connection: sqlite3.Connection,
    repo_path: Path,
    snapshots: tuple[VersionSnapshot, ...],
    *,
    scope: str,
    lang: str,
    version_id_by_tag: dict[str, int],
    current_version_tag: str,
    verbose: bool = True,
) -> dict[str, int]:
    _snapshot_textmap_group_cache.clear()
    row_id_by_hash, final_values = load_current_text_map_group(connection, scope, lang)
    tracker = VersionTracker(final_values)
    group_label = f"{scope}/{lang}"
    total_rows = len(final_values)
    _log(verbose, f"TextMap group {group_label}: {total_rows} rows")

    for index, snapshot in enumerate(snapshots, start=1):
        pending = tracker.pending_keys()
        if not pending:
            break
        _log(verbose, f"  [{index}/{len(snapshots)}] {group_label} -> {snapshot.version_tag} ({len(pending)} pending)")
        snapshot_values = _load_snapshot_textmap_group(
            repo_path,
            snapshot.commit,
            scope,
            lang,
            target_hashes=pending,
        )
        tracker.observe(snapshot_values, snapshot.version_tag)

    pending_created = tracker.missing_created_keys()
    if pending_created:
        _log(verbose, f"  phase 1.5 {group_label}: retry earliest existence for {len(pending_created)} rows")
        for snapshot in snapshots:
            if not pending_created:
                break
            snapshot_values = _load_snapshot_textmap_group(
                repo_path,
                snapshot.commit,
                scope,
                lang,
                target_hashes=pending_created,
            )
            tracker.observe(snapshot_values, snapshot.version_tag)
            pending_created = tracker.missing_created_keys()

    stats = tracker.finalize(current_version_tag)
    with connection:
        update_text_map_versions(connection, row_id_by_hash, tracker, version_id_by_tag)
    _log(
        verbose,
        f"  completed {group_label}: "
        f"created->current={stats['created_fallback_to_current']}, "
        f"updated->created={stats['updated_fallback_to_created']}",
    )
    return stats


def run_backfill(db_path: Path = DB_PATH, *, verbose: bool = True) -> None:
    ensure_history_available()
    history_rows = _collect_version_history_rows()
    checkpoints = collect_version_checkpoints(history_rows)
    if not db_path.is_file():
        raise RuntimeError(f"数据库不存在：{db_path}")

    current_version_tag = checkpoints[-1].version_tag
    entity_repo_path: Path | None = None

    _log(verbose, f"Preparing history backfill from {len(checkpoints)} version checkpoints...")
    try:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA journal_mode = MEMORY")
        connection.execute("PRAGMA temp_store = MEMORY")
        try:
            tracking = load_tracking_set(connection)
            snapshot_range: SnapshotReplayRange | None = None
            with connection:
                version_id_by_tag, current_version_id = rebuild_version_dim(connection, checkpoints)
                snapshot_range = build_snapshot_replay_range(history_rows, version_id_by_tag)
                resume_mode, entities_done, completed_groups = _load_backfill_progress(connection, current_version_tag)
                if not resume_mode:
                    _persist_backfill_progress(
                        connection,
                        current_version_tag=current_version_tag,
                        completed_groups=set(),
                        entities_done=False,
                        status=BACKFILL_STATUS_IN_PROGRESS,
                    )
                    completed_groups = set()
                    entities_done = False
                else:
                    _persist_backfill_progress(
                        connection,
                        current_version_tag=current_version_tag,
                        completed_groups=completed_groups,
                        entities_done=entities_done,
                        status=BACKFILL_STATUS_IN_PROGRESS,
                    )

            if resume_mode:
                _log(
                    verbose,
                    f"Resuming history backfill: entities_done={entities_done}, completed_text_groups={len(completed_groups)}",
                )

            if not entities_done:
                _log(verbose, "Scanning structured entities...")
                entity_repo_path = clone_history_repo()
                try:
                    entity_trackers = build_entity_trackers(entity_repo_path, checkpoints, tracking)
                    observe_entity_versions(
                        entity_repo_path,
                        checkpoints,
                        tracking,
                        entity_trackers,
                        verbose=verbose,
                    )
                    entity_summary = finalize_entity_trackers(entity_trackers, current_version_tag)
                    if verbose:
                        print_entity_fallback_summary(entity_summary)

                    _log(verbose, "Writing structured entity version history into SQLite...")
                    with connection:
                        for entity_kind, (table_name, key_column) in ENTITY_KIND_TO_TABLE.items():
                            update_version_pairs(
                                connection,
                                table_name,
                                key_column,
                                entity_trackers[entity_kind],
                                version_id_by_tag,
                            )
                        _persist_backfill_progress(
                            connection,
                            current_version_tag=current_version_tag,
                            completed_groups=completed_groups,
                            entities_done=True,
                            status=BACKFILL_STATUS_IN_PROGRESS,
                        )
                    entities_done = True
                finally:
                    shutil.rmtree(entity_repo_path.parent, ignore_errors=True)
                    entity_repo_path = None
            else:
                _log(verbose, "Structured entity version history already written, skipping entity scan.")

            _log(verbose, "Backfilling TextMap version history...")
            text_map_summary = {
                "created_fallback_to_current": 0,
                "updated_fallback_to_created": 0,
            }
            total_groups = len(tracking.text_groups)
            for index, (scope, lang) in enumerate(tracking.text_groups, start=1):
                group_key = _serialize_text_group(scope, lang)
                if group_key in completed_groups:
                    _log(verbose, f"[text_map {index}/{total_groups}] {scope}/{lang} (resume skip)")
                    continue

                _log(verbose, f"[text_map {index}/{total_groups}] {scope}/{lang}")
                group_stats = backfill_text_map_group(
                    connection,
                    DATA_ROOT,
                    snapshot_range.snapshots if snapshot_range is not None else tuple(),
                    scope=scope,
                    lang=lang,
                    version_id_by_tag=version_id_by_tag,
                    current_version_tag=current_version_tag,
                    verbose=verbose,
                )
                for key in text_map_summary:
                    text_map_summary[key] += group_stats.get(key, 0)
                completed_groups.add(group_key)
                with connection:
                    _persist_backfill_progress(
                        connection,
                        current_version_tag=current_version_tag,
                        completed_groups=completed_groups,
                        entities_done=True,
                        status=BACKFILL_STATUS_IN_PROGRESS,
                    )

            _log(
                verbose,
                "TextMap fallback summary: "
                f"created->current={text_map_summary['created_fallback_to_current']}, "
                f"updated->created={text_map_summary['updated_fallback_to_created']}",
            )

            _log(verbose, "Rebuilding sources and search indexes...")
            with connection:
                rebuild_dependent_indexes(connection, current_version_id)
                verify_current_snapshot(connection, current_version_tag)
                _persist_backfill_progress(
                    connection,
                    current_version_tag=current_version_tag,
                    completed_groups=set(),
                    entities_done=True,
                    status=BACKFILL_STATUS_COMPLETE,
                )
        finally:
            connection.close()
    finally:
        if entity_repo_path is not None:
            shutil.rmtree(entity_repo_path.parent, ignore_errors=True)

    _log(verbose, f"History backfill complete. Current version: {current_version_tag}")


def main() -> None:
    run_backfill()


if __name__ == "__main__":
    main()
