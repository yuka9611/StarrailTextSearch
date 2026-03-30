from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from data_paths import CONFIG_LEVEL_ROOT, DATA_ROOT, DB_PATH, DB_TMP_PATH, EXCEL_OUTPUT_ROOT, STORY_ROOT, TEXTMAP_ROOT


DEFAULT_SOURCE_LANGUAGE = "chs"
DEFAULT_PLAYER_NAME = "开拓者"
DEFAULT_PLAYER_GENDER = "both"
MAX_NORMALIZE_DEPTH = 5

TEXTMAP_NORMAL_PATTERN = re.compile(r"^TextMap(?!Main)([A-Z]+(?:_\d+)?)\.json$")
TEXTMAP_MAIN_PATTERN = re.compile(r"^TextMapMain([A-Z]+(?:_\d+)?)\.json$")
TEXTJOIN_PLACEHOLDER_PATTERN = re.compile(r"\{TEXTJOIN#(\d+)}")
MALE_FEMALE_PATTERN = re.compile(r"\{M#(.*?)}\{F#(.*?)}")
FEMALE_MALE_PATTERN = re.compile(r"\{F#(.*?)}\{M#(.*?)}")
VERSION_TAG_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")
TEXT_LINE_BREAKS = re.compile(r"\r\n|\r|\\n")

LANGUAGE_LABELS = {
    "chs": "简体中文",
    "cht": "繁體中文",
    "en": "English",
    "jp": "日本語",
    "kr": "한국어",
    "es": "Español",
    "ru": "Русский",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
}

LANGUAGE_ORDER = [
    "chs",
    "cht",
    "en",
    "jp",
    "kr",
    "es",
    "ru",
    "th",
    "vi",
    "id",
    "fr",
    "de",
    "pt",
]


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_dim (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_version TEXT NOT NULL UNIQUE,
    version_tag TEXT NOT NULL,
    version_sort_key INTEGER NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS language_dim (
    code TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS text_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    lang TEXT NOT NULL,
    hash TEXT NOT NULL,
    content TEXT NOT NULL,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL,
    UNIQUE(scope, lang, hash)
);

CREATE INDEX IF NOT EXISTS text_map_lang_hash_index ON text_map(lang, hash);
CREATE INDEX IF NOT EXISTS text_map_scope_lang_hash_index ON text_map(scope, lang, hash);
CREATE INDEX IF NOT EXISTS text_map_created_version_index ON text_map(created_version_id);
CREATE INDEX IF NOT EXISTS text_map_updated_version_index ON text_map(updated_version_id);

CREATE VIRTUAL TABLE IF NOT EXISTS text_map_fts USING fts5(
    search_content,
    lang_scope,
    tokenize = 'unicode61',
    content = ''
);

CREATE TABLE IF NOT EXISTS text_join_item (
    item_id INTEGER PRIMARY KEY,
    text_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS text_join_config (
    join_id INTEGER PRIMARY KEY,
    item_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS avatar (
    avatar_id INTEGER PRIMARY KEY,
    name_hash TEXT,
    full_name_hash TEXT,
    icon_path TEXT,
    round_icon_path TEXT,
    json_path TEXT
);

CREATE TABLE IF NOT EXISTS message_camp (
    camp_id INTEGER PRIMARY KEY,
    name_hash TEXT,
    sort_id INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS message_contact_type (
    type_id INTEGER PRIMARY KEY,
    name_hash TEXT,
    sort_id INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mission (
    mission_id INTEGER PRIMARY KEY,
    mission_type TEXT,
    name_hash TEXT,
    search_key TEXT NOT NULL,
    story_paths_json TEXT NOT NULL,
    line_count INTEGER NOT NULL DEFAULT 0,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mission_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL REFERENCES mission(mission_id) ON DELETE CASCADE,
    story_path TEXT NOT NULL,
    line_order INTEGER NOT NULL,
    line_type TEXT NOT NULL,
    talk_sentence_id INTEGER NOT NULL,
    speaker_hash TEXT,
    text_hash TEXT
);

CREATE INDEX IF NOT EXISTS mission_line_mission_order_index ON mission_line(mission_id, line_order);

CREATE TABLE IF NOT EXISTS book (
    book_id INTEGER PRIMARY KEY,
    series_id INTEGER,
    inside_id INTEGER,
    world_id INTEGER,
    series_name_hash TEXT,
    series_comment_hash TEXT,
    title_hash TEXT,
    content_hash TEXT,
    display_type INTEGER,
    line_count INTEGER NOT NULL DEFAULT 0,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS message_thread (
    thread_id INTEGER PRIMARY KEY,
    contact_id INTEGER,
    display_name_hash TEXT,
    signature_hash TEXT,
    icon_path TEXT,
    thread_type TEXT NOT NULL,
    camp INTEGER,
    linked_main_mission_id INTEGER,
    message_count INTEGER NOT NULL DEFAULT 0,
    latest_preview_hash TEXT,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS message_section (
    section_id INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES message_thread(thread_id) ON DELETE CASCADE,
    linked_main_mission_id INTEGER,
    start_item_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_item (
    item_id INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES message_thread(thread_id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES message_section(section_id) ON DELETE CASCADE,
    sender TEXT,
    item_type TEXT,
    main_text_hash TEXT,
    option_text_hash TEXT,
    next_item_ids_json TEXT NOT NULL,
    item_content_id INTEGER,
    item_order INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS message_item_thread_order_index ON message_item(thread_id, item_order);

CREATE TABLE IF NOT EXISTS voice_entry (
    entry_key TEXT PRIMARY KEY,
    avatar_id INTEGER NOT NULL,
    voice_id INTEGER NOT NULL,
    title_hash TEXT,
    text_hash_m TEXT,
    text_hash_f TEXT,
    audio_id INTEGER,
    voice_path TEXT,
    sort_id INTEGER NOT NULL DEFAULT 0,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS voice_entry_avatar_sort_index ON voice_entry(avatar_id, sort_id, voice_id);

CREATE TABLE IF NOT EXISTS story_entry (
    entry_key TEXT PRIMARY KEY,
    avatar_id INTEGER NOT NULL,
    story_id INTEGER NOT NULL,
    title_hash TEXT,
    content_hash TEXT,
    unlock_id INTEGER,
    sort_id INTEGER NOT NULL DEFAULT 0,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS story_entry_avatar_sort_index ON story_entry(avatar_id, sort_id, story_id);

CREATE TABLE IF NOT EXISTS source_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_key TEXT NOT NULL,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL,
    UNIQUE(source_type, source_key)
);

CREATE TABLE IF NOT EXISTS text_source_link (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_record_id INTEGER NOT NULL REFERENCES source_record(id) ON DELETE CASCADE,
    text_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS text_source_link_hash_index ON text_source_link(text_hash);
CREATE INDEX IF NOT EXISTS text_source_link_source_index ON text_source_link(source_record_id);

CREATE TABLE IF NOT EXISTS entity_search (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    lang TEXT NOT NULL,
    title_text TEXT NOT NULL,
    preview_text TEXT NOT NULL,
    search_text TEXT NOT NULL,
    camp INTEGER,
    thread_type TEXT,
    created_version_id INTEGER NOT NULL,
    updated_version_id INTEGER NOT NULL,
    UNIQUE(entity_type, entity_key, lang)
);

CREATE INDEX IF NOT EXISTS entity_search_type_lang_index ON entity_search(entity_type, lang);
CREATE INDEX IF NOT EXISTS entity_search_camp_index ON entity_search(camp);
CREATE INDEX IF NOT EXISTS entity_search_created_index ON entity_search(created_version_id);
CREATE INDEX IF NOT EXISTS entity_search_updated_index ON entity_search(updated_version_id);

CREATE VIRTUAL TABLE IF NOT EXISTS entity_search_fts USING fts5(
    search_text,
    entity_type UNINDEXED,
    entity_key UNINDEXED,
    lang UNINDEXED,
    camp UNINDEXED,
    thread_type UNINDEXED,
    tokenize = 'unicode61'
);
"""


@dataclass(slots=True)
class TalkSentence:
    talk_sentence_id: int
    speaker_hash: str | None
    text_hash: str | None
    voice_id: int | None


class TextMapCache:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self._cache: dict[tuple[str, str, str], str] = {}
        self._raw_map_cache: dict[tuple[str, str], dict[str, str]] = {}
        self._text_join_items: dict[int, str] | None = None
        self._text_join_configs: dict[int, list[int]] | None = None

    def clear(self) -> None:
        self._cache.clear()
        self._raw_map_cache.clear()
        self._text_join_items = None
        self._text_join_configs = None

    def get_text(self, text_hash: str | None, lang: str, *, prefer_main: bool = False) -> str:
        normalized_hash = normalize_hash(text_hash)
        if not normalized_hash:
            return ""

        scopes = ("main", "normal") if prefer_main else ("normal", "main")
        for scope in scopes:
            key = (scope, lang, normalized_hash)
            if key in self._cache:
                cached = self._cache[key]
                if cached:
                    return cached
                continue

            row = self.connection.execute(
                "SELECT content FROM text_map WHERE scope=? AND lang=? AND hash=? LIMIT 1",
                (scope, lang, normalized_hash),
            ).fetchone()
            content = str(row["content"]) if row and row["content"] else ""
            self._cache[key] = content
            if content:
                return content
        return ""

    def get_raw_map(self, lang: str, scope: str = "normal") -> dict[str, str]:
        key = (scope, lang)
        if key in self._raw_map_cache:
            return self._raw_map_cache[key]
        rows = self.connection.execute(
            "SELECT hash, content FROM text_map WHERE scope=? AND lang=?",
            (scope, lang),
        ).fetchall()
        mapping = {str(row[0]): str(row[1]) for row in rows}
        self._raw_map_cache[key] = mapping
        return mapping

    def get_normalized_text(
        self,
        text_hash: str | None,
        lang: str,
        *,
        player_name: str = DEFAULT_PLAYER_NAME,
        player_gender: str = DEFAULT_PLAYER_GENDER,
        prefer_main: bool = False,
        depth: int = 0,
    ) -> str:
        raw = self.get_text(text_hash, lang, prefer_main=prefer_main)
        if not raw:
            return ""
        return self._normalize_text(
            raw,
            lang,
            player_name=player_name,
            player_gender=player_gender,
            depth=depth,
        )

    def _normalize_text(
        self,
        text: str,
        lang: str,
        *,
        player_name: str,
        player_gender: str,
        depth: int,
    ) -> str:
        if depth > MAX_NORMALIZE_DEPTH:
            return text

        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\\n", "\n")
        normalized = TEXTJOIN_PLACEHOLDER_PATTERN.sub(
            lambda match: self._resolve_text_join(
                int(match.group(1)),
                lang,
                player_name=player_name,
                player_gender=player_gender,
                depth=depth + 1,
            )
            or match.group(0),
            normalized,
        )
        normalized = MALE_FEMALE_PATTERN.sub(
            lambda match: resolve_gender_pair(match.group(1), match.group(2), player_gender),
            normalized,
        )
        normalized = FEMALE_MALE_PATTERN.sub(
            lambda match: resolve_gender_pair(match.group(2), match.group(1), player_gender),
            normalized,
        )
        normalized = normalized.replace("{NICKNAME}", player_name)
        if normalized.startswith("#"):
            normalized = normalized[1:]
        return normalized

    def _resolve_text_join(
        self,
        text_join_id: int,
        lang: str,
        *,
        player_name: str,
        player_gender: str,
        depth: int,
    ) -> str | None:
        item_hash_by_id, config_by_id = self._load_text_join_indexes()
        item_ids = config_by_id.get(text_join_id)
        if not item_ids:
            return None

        parts: list[str] = []
        seen: set[str] = set()
        for item_id in item_ids:
            text_hash = item_hash_by_id.get(item_id)
            if not text_hash:
                continue
            normalized = self.get_normalized_text(
                text_hash,
                lang,
                player_name=player_name,
                player_gender=player_gender,
                depth=depth,
            ).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            parts.append(normalized)
        if not parts:
            return None
        return "/".join(parts)

    def _load_text_join_indexes(self) -> tuple[dict[int, str], dict[int, list[int]]]:
        if self._text_join_items is not None and self._text_join_configs is not None:
            return self._text_join_items, self._text_join_configs

        cursor = self.connection.cursor()
        try:
            item_rows = cursor.execute("SELECT item_id, text_hash FROM text_join_item").fetchall()
            config_rows = cursor.execute("SELECT join_id, item_ids_json FROM text_join_config").fetchall()
        finally:
            cursor.close()

        self._text_join_items = {int(row[0]): str(row[1]) for row in item_rows}
        self._text_join_configs = {
            int(row[0]): [int(item_id) for item_id in json.loads(row[1] or "[]")]
            for row in config_rows
        }
        return self._text_join_items, self._text_join_configs


def normalize_hash(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "Hash" in value:
            return normalize_hash(value.get("Hash"))
        return None
    text = str(value).strip()
    return text or None


def json_load(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_text_for_search(value: str) -> str:
    text = TEXT_LINE_BREAKS.sub("\n", str(value or ""))
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def hash_text(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def parse_version(raw_version: str) -> tuple[str, int]:
    match = VERSION_TAG_PATTERN.search(raw_version or "")
    if not match:
        return (raw_version or "current", 0)
    major, minor, patch = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return (f"{major}.{minor}.{patch}", major * 1_000_000 + minor * 1_000 + patch)


def current_version_from_git() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(DATA_ROOT), "log", "--format=%s", "-n", "1"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "current"
    return (result.stdout or "").strip() or "current"


def resolve_gender_pair(male_text: str, female_text: str, player_gender: str) -> str:
    if player_gender == "male":
        return male_text
    if player_gender == "female":
        return female_text
    return f"{{{male_text}/{female_text}}}"


def extract_talk_sentence_refs(payload: object) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []

    def walk(node: object, *, context: str = "dialogue") -> None:
        if isinstance(node, dict):
            task_type = str(node.get("$type", ""))
            if task_type.endswith("PlayOptionTalk"):
                for item in node.get("OptionList", []) or []:
                    talk_sentence_id = item.get("TalkSentenceID")
                    if talk_sentence_id is not None:
                        results.append((int(talk_sentence_id), "option"))
                return
            if task_type.endswith("PlaySimpleTalk"):
                for item in node.get("SimpleTalkList", []) or []:
                    talk_sentence_id = item.get("TalkSentenceID")
                    if talk_sentence_id is not None:
                        results.append((int(talk_sentence_id), "dialogue"))
                return
            for key, value in node.items():
                next_context = context
                if key == "OptionList":
                    next_context = "option"
                walk(value, context=next_context)
            return

        if isinstance(node, list):
            for item in node:
                walk(item, context=context)

    walk(payload)
    return results


class StarrailDatabaseBuilder:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.current_raw_version = current_version_from_git()
        self.current_version_tag, self.current_version_sort_key = parse_version(self.current_raw_version)

    def initialize_empty_database(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        connection = sqlite3.connect(self.db_path)
        try:
            connection.executescript(SCHEMA_SQL)
            connection.commit()
        finally:
            connection.close()

    def build_database(self, *, verbose: bool = True, include_history: bool = True) -> Path:
        if not TEXTMAP_ROOT.is_dir():
            raise FileNotFoundError(f"TextMap directory not found: {TEXTMAP_ROOT}")
        if not EXCEL_OUTPUT_ROOT.is_dir():
            raise FileNotFoundError(f"ExcelOutput directory not found: {EXCEL_OUTPUT_ROOT}")

        if DB_TMP_PATH.exists():
            DB_TMP_PATH.unlink()

        connection = sqlite3.connect(DB_TMP_PATH)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript(SCHEMA_SQL)
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute("PRAGMA journal_mode = MEMORY")
            version_id = self._seed_meta(connection)

            if verbose:
                print("Importing TextMap...")
            self._import_languages(connection)
            self._import_text_map(connection, version_id)
            self._import_text_join(connection)
            self._import_avatar_and_message_meta(connection)

            if verbose:
                print("Importing structured entities...")
            talk_sentence_map = self._load_talk_sentence_map()
            self._import_missions(connection, talk_sentence_map, version_id)
            self._import_books(connection, version_id)
            self._import_messages(connection, version_id)
            self._import_voices(connection, version_id)
            self._import_stories(connection, version_id)

            if verbose:
                print("Rebuilding sources and search indexes...")
            self._rebuild_sources(connection, version_id)
            self._rebuild_text_map_fts(connection)
            self._rebuild_entity_search(connection, version_id)
            connection.commit()
        finally:
            connection.close()

        if include_history:
            if verbose:
                print("Backfilling version history...")
            from dbBuild.history_backfill import run_backfill

            run_backfill(DB_TMP_PATH, verbose=verbose)

        os.replace(DB_TMP_PATH, self.db_path)
        return self.db_path

    def _seed_meta(self, connection: sqlite3.Connection) -> int:
        connection.execute("DELETE FROM app_meta")
        connection.execute("DELETE FROM version_dim")
        connection.execute("INSERT INTO version_dim(raw_version, version_tag, version_sort_key, is_current) VALUES (?, ?, ?, 1)",
                           (self.current_raw_version, self.current_version_tag, self.current_version_sort_key))
        version_id = int(connection.execute("SELECT id FROM version_dim LIMIT 1").fetchone()[0])
        connection.executemany(
            "INSERT INTO app_meta(k, v) VALUES (?, ?)",
            [
                ("default_language", "chs"),
                ("default_source_language", DEFAULT_SOURCE_LANGUAGE),
                ("current_raw_version", self.current_raw_version),
                ("current_version_tag", self.current_version_tag),
            ],
        )
        return version_id

    def _import_languages(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM language_dim")
        rows = [
            (code, LANGUAGE_LABELS.get(code, code.upper()), index)
            for index, code in enumerate(LANGUAGE_ORDER, start=1)
        ]
        connection.executemany(
            "INSERT INTO language_dim(code, label, sort_order) VALUES (?, ?, ?)",
            rows,
        )

    def _iter_textmap_groups(self) -> Iterable[tuple[str, str, list[Path]]]:
        grouped: dict[tuple[str, str], list[Path]] = defaultdict(list)
        for path in sorted(TEXTMAP_ROOT.iterdir()):
            if not path.is_file():
                continue
            normal_match = TEXTMAP_NORMAL_PATTERN.match(path.name)
            if normal_match:
                lang = re.sub(r"_\d+$", "", normal_match.group(1)).lower()
                grouped[("normal", lang)].append(path)
        for (scope, lang), files in sorted(grouped.items()):
            yield scope, lang, sorted(files, key=lambda item: item.name)

    def _import_text_map(self, connection: sqlite3.Connection, version_id: int) -> None:
        connection.execute("DELETE FROM text_map")
        rows: list[tuple] = []
        for scope, lang, files in self._iter_textmap_groups():
            for file_path in files:
                payload = json_load(file_path)
                for text_hash, content in payload.items():
                    if not isinstance(content, str):
                        continue
                    rows.append((
                        scope,
                        lang,
                        str(text_hash),
                        content,
                        version_id,
                        version_id,
                    ))
                    if len(rows) >= 5000:
                        connection.executemany(
                            """
                            INSERT INTO text_map(scope, lang, hash, content, created_version_id, updated_version_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            rows,
                        )
                        rows.clear()
        if rows:
            connection.executemany(
                """
                INSERT INTO text_map(scope, lang, hash, content, created_version_id, updated_version_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _normalize_text_for_index(self, text: str) -> str:
        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\\n", "\n")
        normalized = MALE_FEMALE_PATTERN.sub(lambda match: f"{match.group(1)}/{match.group(2)}", normalized)
        normalized = FEMALE_MALE_PATTERN.sub(lambda match: f"{match.group(2)}/{match.group(1)}", normalized)
        normalized = normalized.replace("{NICKNAME}", DEFAULT_PLAYER_NAME)
        if normalized.startswith("#"):
            normalized = normalized[1:]
        return normalized

    def _import_text_join(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM text_join_item")
        connection.execute("DELETE FROM text_join_config")

        item_path = EXCEL_OUTPUT_ROOT / "TextJoinItem.json"
        if item_path.is_file():
            item_rows = []
            for row in json_load(item_path):
                item_id = row.get("TextJoinItemID")
                text_hash = normalize_hash(row.get("TextJoinText"))
                if item_id is None or not text_hash:
                    continue
                item_rows.append((int(item_id), text_hash))
            connection.executemany(
                "INSERT INTO text_join_item(item_id, text_hash) VALUES (?, ?)",
                item_rows,
            )

        config_path = EXCEL_OUTPUT_ROOT / "TextJoinConfig.json"
        if config_path.is_file():
            config_rows = []
            for row in json_load(config_path):
                join_id = row.get("TextJoinID")
                item_ids = [int(value) for value in row.get("TextJoinItemList", []) or [] if value is not None]
                default_item = row.get("DefaultItem")
                if not item_ids and default_item is not None:
                    item_ids = [int(default_item)]
                if join_id is None or not item_ids:
                    continue
                config_rows.append((int(join_id), json.dumps(item_ids, ensure_ascii=False)))
            connection.executemany(
                "INSERT INTO text_join_config(join_id, item_ids_json) VALUES (?, ?)",
                config_rows,
            )

    def _import_avatar_and_message_meta(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM avatar")
        connection.execute("DELETE FROM message_camp")
        connection.execute("DELETE FROM message_contact_type")

        avatar_rows = []
        for row in json_load(EXCEL_OUTPUT_ROOT / "AvatarConfig.json"):
            avatar_id = row.get("AvatarID")
            if avatar_id is None:
                continue
            avatar_rows.append((
                int(avatar_id),
                normalize_hash(row.get("AvatarName")),
                normalize_hash(row.get("AvatarFullName")),
                str(row.get("DefaultAvatarHeadIconPath") or ""),
                str(row.get("AvatarSideIconPath") or row.get("AvatarRoundIconPath") or ""),
                str(row.get("JsonPath") or ""),
            ))
        connection.executemany(
            """
            INSERT INTO avatar(avatar_id, name_hash, full_name_hash, icon_path, round_icon_path, json_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            avatar_rows,
        )

        if (EXCEL_OUTPUT_ROOT / "MessageContactsCamp.json").is_file():
            connection.executemany(
                "INSERT INTO message_camp(camp_id, name_hash, sort_id) VALUES (?, ?, ?)",
                [
                    (
                        int(row.get("ContactsCamp")),
                        normalize_hash(row.get("Name")),
                        int(row.get("SortID") or 0),
                    )
                    for row in json_load(EXCEL_OUTPUT_ROOT / "MessageContactsCamp.json")
                    if row.get("ContactsCamp") is not None
                ],
            )

        if (EXCEL_OUTPUT_ROOT / "MessageContactsType.json").is_file():
            connection.executemany(
                "INSERT INTO message_contact_type(type_id, name_hash, sort_id) VALUES (?, ?, ?)",
                [
                    (
                        int(row.get("ContactsType")),
                        normalize_hash(row.get("Name")),
                        int(row.get("SortID") or 0),
                    )
                    for row in json_load(EXCEL_OUTPUT_ROOT / "MessageContactsType.json")
                    if row.get("ContactsType") is not None
                ],
            )

    def _load_talk_sentence_map(self) -> dict[int, TalkSentence]:
        talk_sentence_map: dict[int, TalkSentence] = {}
        payload = json_load(EXCEL_OUTPUT_ROOT / "TalkSentenceConfig.json")
        for row in payload:
            talk_sentence_id = row.get("TalkSentenceID")
            if talk_sentence_id is None:
                continue
            talk_sentence_map[int(talk_sentence_id)] = TalkSentence(
                talk_sentence_id=int(talk_sentence_id),
                speaker_hash=normalize_hash(row.get("TextmapTalkSentenceName")),
                text_hash=normalize_hash(row.get("TalkSentenceText")),
                voice_id=int(row["VoiceID"]) if row.get("VoiceID") is not None else None,
            )
        return talk_sentence_map

    def _import_missions(
        self,
        connection: sqlite3.Connection,
        talk_sentence_map: dict[int, TalkSentence],
        version_id: int,
    ) -> None:
        connection.execute("DELETE FROM mission_line")
        connection.execute("DELETE FROM mission")

        mission_name_hash: dict[int, str | None] = {}
        for row in json_load(EXCEL_OUTPUT_ROOT / "MainMission.json"):
            mission_id = row.get("MainMissionID")
            if mission_id is None:
                continue
            mission_name_hash[int(mission_id)] = normalize_hash(row.get("Name"))

        mission_rows = []
        line_rows = []
        for mission_dir in sorted((STORY_ROOT / "Mission").glob("*")):
            if not mission_dir.is_dir():
                continue
            try:
                mission_id = int(mission_dir.name)
            except ValueError:
                continue
            story_paths: list[str] = []
            line_count = 0
            for story_path in sorted(mission_dir.glob("*.json")):
                story_paths.append(str(story_path.relative_to(DATA_ROOT)))
                payload = json_load(story_path)
                talk_refs = extract_talk_sentence_refs(payload)
                for offset, (talk_sentence_id, line_type) in enumerate(talk_refs):
                    talk_sentence = talk_sentence_map.get(talk_sentence_id)
                    line_rows.append((
                        mission_id,
                        str(story_path.relative_to(DATA_ROOT)),
                        line_count + offset,
                        line_type,
                        talk_sentence_id,
                        talk_sentence.speaker_hash if talk_sentence else None,
                        talk_sentence.text_hash if talk_sentence else None,
                    ))
                line_count += len(talk_refs)
            mission_rows.append((
                mission_id,
                "main",
                mission_name_hash.get(mission_id),
                str(mission_id),
                json.dumps(story_paths, ensure_ascii=False),
                line_count,
                version_id,
                version_id,
            ))

        connection.executemany(
            """
            INSERT INTO mission(mission_id, mission_type, name_hash, search_key, story_paths_json, line_count, created_version_id, updated_version_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            mission_rows,
        )
        connection.executemany(
            """
            INSERT INTO mission_line(mission_id, story_path, line_order, line_type, talk_sentence_id, speaker_hash, text_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            line_rows,
        )

    def _import_books(self, connection: sqlite3.Connection, version_id: int) -> None:
        connection.execute("DELETE FROM book")
        resolver = TextMapCache(connection)

        series_map: dict[int, dict] = {}
        for row in json_load(EXCEL_OUTPUT_ROOT / "BookSeriesConfig.json"):
            series_id = row.get("BookSeriesID")
            if series_id is None:
                continue
            series_map[int(series_id)] = row

        rows = []
        for row in json_load(EXCEL_OUTPUT_ROOT / "LocalbookConfig.json"):
            book_id = row.get("BookID")
            if book_id is None:
                continue
            series = series_map.get(int(row.get("BookSeriesID") or 0), {})
            content_hash = normalize_hash(row.get("BookContent"))
            content_text = resolver.get_normalized_text(content_hash, DEFAULT_SOURCE_LANGUAGE)
            normalized_content = normalize_text_for_search(content_text)
            line_count = normalized_content.count("\n") + 1 if normalized_content else 0
            rows.append((
                int(book_id),
                int(row.get("BookSeriesID") or 0),
                int(row.get("BookSeriesInsideID") or 0),
                int(series.get("BookSeriesWorld") or 0),
                normalize_hash(series.get("BookSeries")),
                normalize_hash(series.get("BookSeriesComments")),
                normalize_hash(row.get("BookInsideName")),
                content_hash,
                int(row.get("BookDisplayType") or 0),
                line_count,
                version_id,
                version_id,
            ))
        connection.executemany(
            """
            INSERT INTO book(
                book_id, series_id, inside_id, world_id, series_name_hash, series_comment_hash,
                title_hash, content_hash, display_type, line_count, created_version_id, updated_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def _import_messages(self, connection: sqlite3.Connection, version_id: int) -> None:
        connection.execute("DELETE FROM message_item")
        connection.execute("DELETE FROM message_section")
        connection.execute("DELETE FROM message_thread")

        contacts_by_id = {
            int(row.get("ID")): row
            for row in json_load(EXCEL_OUTPUT_ROOT / "MessageContactsConfig.json")
            if row.get("ID") is not None
        }
        sections_by_id = {
            int(row.get("ID")): row
            for row in json_load(EXCEL_OUTPUT_ROOT / "MessageSectionConfig.json")
            if row.get("ID") is not None
        }
        message_items_by_section: dict[int, list[dict]] = defaultdict(list)
        for row in json_load(EXCEL_OUTPUT_ROOT / "MessageItemConfig.json"):
            section_id = row.get("SectionID")
            item_id = row.get("ID")
            if section_id is None or item_id is None:
                continue
            message_items_by_section[int(section_id)].append(row)

        thread_rows = []
        section_rows = []
        item_rows = []

        for group_row in json_load(EXCEL_OUTPUT_ROOT / "MessageGroupConfig.json"):
            thread_id = group_row.get("ID")
            if thread_id is None:
                continue
            contact_id = int(group_row.get("MessageContactsID") or 0)
            contact = contacts_by_id.get(contact_id, {})
            section_ids = [int(section_id) for section_id in group_row.get("MessageSectionIDList", []) or [] if section_id is not None]

            message_count = 0
            latest_preview_hash = None
            primary_mission = None
            item_order = 0

            for section_id in section_ids:
                section = sections_by_id.get(section_id, {})
                start_item_ids = [int(item_id) for item_id in section.get("StartMessageItemIDList", []) or [] if item_id is not None]
                linked_main_mission_id = int(section.get("MainMissionLink") or 0) or None
                if primary_mission is None:
                    primary_mission = linked_main_mission_id
                section_rows.append((
                    section_id,
                    int(thread_id),
                    linked_main_mission_id,
                    json.dumps(start_item_ids, ensure_ascii=False),
                ))
                ordered_section_items = sorted(
                    message_items_by_section.get(section_id, []),
                    key=lambda item: int(item.get("ID") or 0),
                )
                for item in ordered_section_items:
                    main_hash = normalize_hash(item.get("MainText"))
                    if main_hash:
                        latest_preview_hash = main_hash
                    if main_hash or normalize_hash(item.get("OptionText")):
                        message_count += 1
                    item_rows.append((
                        int(item.get("ID")),
                        int(thread_id),
                        int(section_id),
                        str(item.get("Sender") or ""),
                        str(item.get("ItemType") or ""),
                        main_hash,
                        normalize_hash(item.get("OptionText")),
                        json.dumps([int(value) for value in item.get("NextItemIDList", []) or [] if value is not None], ensure_ascii=False),
                        int(item["ItemContentID"]) if item.get("ItemContentID") is not None else None,
                        item_order,
                    ))
                    item_order += 1

            contacts_type = int(contact.get("ContactsType") or 0)
            thread_type = "group" if contacts_type == 3 else "system" if contacts_type == 2 else "contact"
            thread_rows.append((
                int(thread_id),
                contact_id or None,
                normalize_hash(contact.get("Name")),
                normalize_hash(contact.get("SignatureText")),
                str(contact.get("IconPath") or ""),
                thread_type,
                int(contact.get("ContactsCamp") or 0) or None,
                primary_mission,
                message_count,
                latest_preview_hash,
                version_id,
                version_id,
            ))

        connection.executemany(
            """
            INSERT INTO message_thread(
                thread_id, contact_id, display_name_hash, signature_hash, icon_path, thread_type, camp,
                linked_main_mission_id, message_count, latest_preview_hash, created_version_id, updated_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            thread_rows,
        )
        connection.executemany(
            """
            INSERT INTO message_section(section_id, thread_id, linked_main_mission_id, start_item_ids_json)
            VALUES (?, ?, ?, ?)
            """,
            section_rows,
        )
        connection.executemany(
            """
            INSERT INTO message_item(
                item_id, thread_id, section_id, sender, item_type, main_text_hash, option_text_hash,
                next_item_ids_json, item_content_id, item_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            item_rows,
        )

    def _import_voices(self, connection: sqlite3.Connection, version_id: int) -> None:
        connection.execute("DELETE FROM voice_entry")

        voice_path_by_id = {
            int(row.get("VoiceID")): str(row.get("VoicePath") or "")
            for row in json_load(EXCEL_OUTPUT_ROOT / "VoiceConfig.json")
            if row.get("VoiceID") is not None
        }

        rows = []
        for row in json_load(EXCEL_OUTPUT_ROOT / "VoiceAtlas.json"):
            avatar_id = row.get("AvatarID")
            voice_id = row.get("VoiceID")
            if avatar_id is None or voice_id is None:
                continue
            entry_key = f"{int(avatar_id)}:{int(voice_id)}"
            rows.append((
                entry_key,
                int(avatar_id),
                int(voice_id),
                normalize_hash(row.get("VoiceTitle")),
                normalize_hash(row.get("Voice_M")),
                normalize_hash(row.get("Voice_F")),
                int(row["AudioID"]) if row.get("AudioID") is not None else None,
                voice_path_by_id.get(int(row.get("AudioID") or 0)) or voice_path_by_id.get(int(voice_id)) or "",
                int(row.get("SortID") or 0),
                version_id,
                version_id,
            ))
        connection.executemany(
            """
            INSERT INTO voice_entry(
                entry_key, avatar_id, voice_id, title_hash, text_hash_m, text_hash_f,
                audio_id, voice_path, sort_id, created_version_id, updated_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def _import_stories(self, connection: sqlite3.Connection, version_id: int) -> None:
        connection.execute("DELETE FROM story_entry")

        story_name_by_id = {
            int(row.get("StoryID")): normalize_hash(row.get("StoryName"))
            for row in json_load(EXCEL_OUTPUT_ROOT / "StoryAtlasTextmap.json")
            if row.get("StoryID") is not None
        }

        rows = []
        for row in json_load(EXCEL_OUTPUT_ROOT / "StoryAtlas.json"):
            avatar_id = row.get("AvatarID")
            story_id = row.get("StoryID")
            if avatar_id is None or story_id is None:
                continue
            entry_key = f"{int(avatar_id)}:{int(story_id)}"
            rows.append((
                entry_key,
                int(avatar_id),
                int(story_id),
                story_name_by_id.get(int(story_id)),
                normalize_hash(row.get("Story")),
                int(row["Unlock"]) if row.get("Unlock") is not None else None,
                int(row.get("SortID") or 0),
                version_id,
                version_id,
            ))
        connection.executemany(
            """
            INSERT INTO story_entry(
                entry_key, avatar_id, story_id, title_hash, content_hash, unlock_id,
                sort_id, created_version_id, updated_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def _rebuild_sources(self, connection: sqlite3.Connection, version_id: int) -> None:
        connection.execute("DELETE FROM text_source_link")
        connection.execute("DELETE FROM source_record")

        def add_source(
            source_type: str,
            source_key: str,
            created_version_id: int,
            updated_version_id: int,
            text_hashes: list[tuple[str | None, str, int]],
        ) -> None:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "INSERT INTO source_record(source_type, source_key, created_version_id, updated_version_id) VALUES (?, ?, ?, ?)",
                    (source_type, source_key, created_version_id, updated_version_id),
                )
                source_record_id = int(cursor.lastrowid)
                rows = [
                    (source_record_id, text_hash, role, sort_order)
                    for text_hash, role, sort_order in text_hashes
                    if text_hash
                ]
                cursor.executemany(
                    "INSERT INTO text_source_link(source_record_id, text_hash, role, sort_order) VALUES (?, ?, ?, ?)",
                    rows,
                )
            finally:
                cursor.close()

        mission_rows = connection.execute(
            "SELECT mission_id, name_hash, created_version_id, updated_version_id FROM mission ORDER BY mission_id"
        ).fetchall()
        for mission in mission_rows:
            text_hashes = [(mission["name_hash"], "title", 0)]
            line_rows = connection.execute(
                "SELECT text_hash, speaker_hash, line_order FROM mission_line WHERE mission_id=? ORDER BY line_order",
                (mission["mission_id"],),
            ).fetchall()
            for row in line_rows:
                text_hashes.append((row["text_hash"], "content", int(row["line_order"])))
                text_hashes.append((row["speaker_hash"], "speaker", int(row["line_order"])))
            add_source(
                "mission",
                str(mission["mission_id"]),
                int(mission["created_version_id"] or version_id),
                int(mission["updated_version_id"] or version_id),
                text_hashes,
            )

        book_rows = connection.execute(
            """
            SELECT book_id, title_hash, content_hash, series_name_hash, series_comment_hash,
                   created_version_id, updated_version_id
            FROM book
            ORDER BY book_id
            """
        ).fetchall()
        for book in book_rows:
            add_source(
                "book",
                str(book["book_id"]),
                int(book["created_version_id"] or version_id),
                int(book["updated_version_id"] or version_id),
                [
                    (book["title_hash"], "title", 0),
                    (book["content_hash"], "content", 1),
                    (book["series_name_hash"], "series", 2),
                    (book["series_comment_hash"], "comment", 3),
                ],
            )

        message_rows = connection.execute(
            """
            SELECT thread_id, display_name_hash, signature_hash, latest_preview_hash,
                   created_version_id, updated_version_id
            FROM message_thread
            ORDER BY thread_id
            """
        ).fetchall()
        for thread in message_rows:
            text_hashes = [
                (thread["display_name_hash"], "title", 0),
                (thread["signature_hash"], "signature", 1),
                (thread["latest_preview_hash"], "preview", 2),
            ]
            item_rows = connection.execute(
                "SELECT main_text_hash, option_text_hash, item_order FROM message_item WHERE thread_id=? ORDER BY item_order",
                (thread["thread_id"],),
            ).fetchall()
            for row in item_rows:
                text_hashes.append((row["main_text_hash"], "content", int(row["item_order"])))
                text_hashes.append((row["option_text_hash"], "option", int(row["item_order"])))
            add_source(
                "message",
                str(thread["thread_id"]),
                int(thread["created_version_id"] or version_id),
                int(thread["updated_version_id"] or version_id),
                text_hashes,
            )

        voice_rows = connection.execute(
            """
            SELECT entry_key, title_hash, text_hash_m, text_hash_f, created_version_id, updated_version_id
            FROM voice_entry
            ORDER BY avatar_id, sort_id, voice_id
            """
        ).fetchall()
        for voice in voice_rows:
            add_source(
                "voice",
                str(voice["entry_key"]),
                int(voice["created_version_id"] or version_id),
                int(voice["updated_version_id"] or version_id),
                [
                    (voice["title_hash"], "title", 0),
                    (voice["text_hash_m"], "content", 1),
                    (voice["text_hash_f"], "content_alt", 2),
                ],
            )

        story_rows = connection.execute(
            """
            SELECT entry_key, title_hash, content_hash, created_version_id, updated_version_id
            FROM story_entry
            ORDER BY avatar_id, sort_id, story_id
            """
        ).fetchall()
        for story in story_rows:
            add_source(
                "story",
                str(story["entry_key"]),
                int(story["created_version_id"] or version_id),
                int(story["updated_version_id"] or version_id),
                [
                    (story["title_hash"], "title", 0),
                    (story["content_hash"], "content", 1),
                ],
            )

    def _rebuild_text_map_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM text_map_fts")
        cursor = connection.execute(
            "SELECT id, scope, lang, content FROM text_map WHERE scope='normal' ORDER BY id"
        )
        rows: list[tuple[int, str, str]] = []
        for row in cursor.fetchall():
            rows.append((
                int(row["id"]),
                normalize_text_for_search(self._normalize_text_for_index(row["content"])),
                f"{row['scope']}{row['lang']}",
            ))
            if len(rows) >= 5000:
                connection.executemany(
                    "INSERT INTO text_map_fts(rowid, search_content, lang_scope) VALUES (?, ?, ?)",
                    rows,
                )
                rows.clear()
        if rows:
            connection.executemany(
                "INSERT INTO text_map_fts(rowid, search_content, lang_scope) VALUES (?, ?, ?)",
                rows,
            )

    def _rebuild_entity_search(self, connection: sqlite3.Connection, version_id: int) -> None:
        connection.execute("DELETE FROM entity_search")
        connection.execute("DELETE FROM entity_search_fts")

        resolver = TextMapCache(connection)
        cursor = connection.cursor()
        try:
            entity_rows = []
            for lang in LANGUAGE_ORDER:
                entity_rows.extend(self._build_mission_search_rows(cursor, resolver, lang, version_id))
                entity_rows.extend(self._build_book_search_rows(cursor, resolver, lang, version_id))
                entity_rows.extend(self._build_message_search_rows(cursor, resolver, lang, version_id))
                resolver.clear()

            connection.executemany(
                """
                INSERT INTO entity_search(
                    entity_type, entity_key, lang, title_text, preview_text, search_text, camp, thread_type,
                    created_version_id, updated_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entity_rows,
            )
            connection.execute(
                """
                INSERT INTO entity_search_fts(rowid, search_text, entity_type, entity_key, lang, camp, thread_type)
                SELECT id, search_text, entity_type, entity_key, lang, camp, thread_type
                FROM entity_search
                """
            )
        finally:
            cursor.close()

    def _build_mission_search_rows(
        self,
        cursor: sqlite3.Cursor,
        resolver: TextMapCache,
        lang: str,
        version_id: int,
    ) -> list[tuple]:
        rows = []
        missions = cursor.execute("SELECT mission_id, name_hash, created_version_id, updated_version_id FROM mission ORDER BY mission_id").fetchall()
        for mission in missions:
            title = resolver.get_normalized_text(mission["name_hash"], lang, prefer_main=True) or f"任务 {mission['mission_id']}"
            line_rows = cursor.execute(
                "SELECT speaker_hash, text_hash FROM mission_line WHERE mission_id=? ORDER BY line_order LIMIT 12",
                (mission["mission_id"],),
            ).fetchall()
            line_texts = []
            for row in line_rows:
                speaker = resolver.get_normalized_text(row["speaker_hash"], lang, prefer_main=True)
                content = resolver.get_normalized_text(row["text_hash"], lang)
                if speaker and content:
                    line_texts.append(f"{speaker}: {content}")
                elif content:
                    line_texts.append(content)
            preview = " ".join(line_texts[:2])
            search_text = " ".join([title, *line_texts]).strip()
            rows.append(("mission", str(mission["mission_id"]), lang, title, preview, search_text, None, None,
                         int(mission["created_version_id"] or version_id), int(mission["updated_version_id"] or version_id)))
        return rows

    def _build_book_search_rows(self, cursor: sqlite3.Cursor, resolver: TextMapCache, lang: str, version_id: int) -> list[tuple]:
        rows = []
        books = cursor.execute(
            "SELECT book_id, title_hash, content_hash, series_name_hash, created_version_id, updated_version_id FROM book ORDER BY book_id"
        ).fetchall()
        for book in books:
            title = resolver.get_normalized_text(book["title_hash"], lang, prefer_main=True) or f"书籍 {book['book_id']}"
            series = resolver.get_normalized_text(book["series_name_hash"], lang, prefer_main=True)
            content = resolver.get_normalized_text(book["content_hash"], lang)
            preview = summarize_text(content)
            search_text = " ".join(part for part in [title, series, content] if part)
            rows.append(("book", str(book["book_id"]), lang, title, preview, search_text, None, None,
                         int(book["created_version_id"] or version_id), int(book["updated_version_id"] or version_id)))
        return rows

    def _build_message_search_rows(self, cursor: sqlite3.Cursor, resolver: TextMapCache, lang: str, version_id: int) -> list[tuple]:
        rows = []
        threads = cursor.execute(
            """
            SELECT thread_id, display_name_hash, latest_preview_hash, signature_hash, camp, thread_type, created_version_id, updated_version_id
            FROM message_thread
            ORDER BY thread_id
            """
        ).fetchall()
        for thread in threads:
            title = resolver.get_normalized_text(thread["display_name_hash"], lang, prefer_main=True) or f"短信 {thread['thread_id']}"
            preview = resolver.get_normalized_text(thread["latest_preview_hash"], lang)
            signature = resolver.get_normalized_text(thread["signature_hash"], lang)
            extra = []
            item_rows = cursor.execute(
                "SELECT main_text_hash, option_text_hash FROM message_item WHERE thread_id=? ORDER BY item_order LIMIT 24",
                (thread["thread_id"],),
            ).fetchall()
            for row in item_rows:
                main_text = resolver.get_normalized_text(row["main_text_hash"], lang)
                option_text = resolver.get_normalized_text(row["option_text_hash"], lang)
                if main_text:
                    extra.append(main_text)
                if option_text:
                    extra.append(option_text)
            search_text = " ".join(part for part in [title, signature, preview, *extra] if part)
            rows.append(("message", str(thread["thread_id"]), lang, title, preview or summarize_text(signature), search_text,
                         thread["camp"], thread["thread_type"],
                         int(thread["created_version_id"] or version_id), int(thread["updated_version_id"] or version_id)))
        return rows

def summarize_text(value: str, *, limit: int = 88) -> str:
    text = normalize_text_for_search(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def prettify_identifier(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()
