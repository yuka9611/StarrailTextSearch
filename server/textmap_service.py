from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_LANGUAGE = "chs"
DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100
DEFAULT_PLAYER_NAME = "开拓者"
DEFAULT_PLAYER_GENDER = "both"
VALID_PLAYER_GENDERS = {"male", "female", "both"}

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

TEXTMAP_FILE_PATTERN = re.compile(r"^TextMap(?!Main)([A-Z]+(?:_\d+)?)\.json$")
TEXTJOIN_PLACEHOLDER_PATTERN = re.compile(r"\{TEXTJOIN#(\d+)}")
MALE_FEMALE_PATTERN = re.compile(r"\{M#(.*?)}\{F#(.*?)}")
FEMALE_MALE_PATTERN = re.compile(r"\{F#(.*?)}\{M#(.*?)}")
MAX_NORMALIZE_DEPTH = 5


class TextMapServiceError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DataUnavailableError(TextMapServiceError):
    status_code = 503


class InvalidQueryError(TextMapServiceError):
    status_code = 400


class InvalidLanguageError(TextMapServiceError):
    status_code = 400


class InvalidPlayerGenderError(TextMapServiceError):
    status_code = 400


class TextMapService:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.textmap_dir = data_root / "TextMap"
        self.excel_output_dir = data_root / "ExcelOutput"
        self._lock = threading.RLock()
        self._file_index: Dict[str, List[Path]] | None = None
        self._raw_language_map_cache: Dict[str, Dict[str, str]] = {}
        self._search_entries_cache: Dict[Tuple[str, str, str], List[Tuple[str, str]]] = {}
        self._normalized_text_cache: Dict[Tuple[str, str, str, str], str] = {}
        self._text_join_items: Dict[int, str] | None = None
        self._text_join_configs: Dict[int, List[int]] | None = None

    def get_meta(self) -> Dict[str, object]:
        file_index = self._discover_files()
        return {
            "languages": [
                {
                    "code": code,
                    "label": LANGUAGE_LABELS.get(code, code.upper()),
                }
                for code in LANGUAGE_ORDER
                if code in file_index
            ],
            "defaultLanguage": DEFAULT_LANGUAGE,
            "dataAvailable": self.textmap_dir.is_dir(),
            "dataDir": str(self.textmap_dir),
        }

    def search(
        self,
        keyword: str,
        lang_code: str,
        page: int,
        size: int,
        result_langs: List[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> Dict[str, object]:
        normalized_keyword = self._normalize_keyword(keyword)
        if not normalized_keyword:
            raise InvalidQueryError("请输入要搜索的关键词。")

        normalized_language = lang_code.strip().lower()
        if not normalized_language:
            raise InvalidLanguageError("请选择有效的搜索语言。")

        if page < 1:
            raise InvalidQueryError("页码必须大于等于 1。")

        if size < 1:
            raise InvalidQueryError("每页数量必须大于等于 1。")

        size = min(size, MAX_PAGE_SIZE)
        normalized_player_gender = self._normalize_player_gender(player_gender)
        normalized_player_name = self._normalize_player_name(player_name)
        display_languages = self._resolve_result_languages(result_langs or [], normalized_language)
        entries = self._load_search_entries(
            normalized_language,
            normalized_player_name,
            normalized_player_gender,
        )

        lowered_keyword = normalized_keyword.casefold()
        matches = []
        for text_hash, content in entries:
            if lowered_keyword not in content.casefold():
                continue
            translates = {}
            for display_lang in display_languages:
                translated = self._get_normalized_text_by_hash(
                    text_hash,
                    display_lang,
                    normalized_player_name,
                    normalized_player_gender,
                )
                if translated:
                    translates[display_lang] = translated
            if normalized_language not in translates:
                translates[normalized_language] = content
            matches.append(
                {
                    "hash": text_hash,
                    "translates": translates,
                }
            )

        start = (page - 1) * size
        end = start + size

        return {
            "keyword": keyword,
            "lang": normalized_language,
            "resultLangs": display_languages,
            "playerName": normalized_player_name,
            "playerGender": normalized_player_gender,
            "page": page,
            "size": size,
            "total": len(matches),
            "results": matches[start:end],
        }

    def _discover_files(self) -> Dict[str, List[Path]]:
        with self._lock:
            if self._file_index is not None:
                return self._file_index

            if not self.textmap_dir.is_dir():
                self._file_index = {}
                return self._file_index

            file_index: Dict[str, List[Path]] = {}
            for path in sorted(self.textmap_dir.iterdir()):
                match = TEXTMAP_FILE_PATTERN.match(path.name)
                if not match or not path.is_file():
                    continue
                base_code = re.sub(r"_\d+$", "", match.group(1)).lower()
                file_index.setdefault(base_code, []).append(path)

            self._file_index = file_index
            return self._file_index

    def _load_raw_language_map(self, lang_code: str) -> Dict[str, str]:
        with self._lock:
            if lang_code in self._raw_language_map_cache:
                return self._raw_language_map_cache[lang_code]

        file_index = self._discover_files()
        if not self.textmap_dir.is_dir():
            raise DataUnavailableError(
                f"未找到 TextMap 数据目录：{self.textmap_dir}"
            )

        files = file_index.get(lang_code)
        if not files:
            raise InvalidLanguageError(f"不支持的语言代码：{lang_code}")

        combined: Dict[str, str] = {}
        for file_path in files:
            with file_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            for text_hash, content in payload.items():
                if isinstance(content, str) and content.strip():
                    combined[str(text_hash)] = content

        with self._lock:
            self._raw_language_map_cache[lang_code] = combined

        return combined

    def _load_search_entries(
        self,
        lang_code: str,
        player_name: str,
        player_gender: str,
    ) -> List[Tuple[str, str]]:
        cache_key = (lang_code, player_name, player_gender)
        with self._lock:
            cached = self._search_entries_cache.get(cache_key)
            if cached is not None:
                return cached

        raw_map = self._load_raw_language_map(lang_code)
        entries: List[Tuple[str, str]] = []
        for text_hash, _ in sorted(raw_map.items(), key=_hash_sort_key):
            normalized = self._get_normalized_text_by_hash(
                text_hash,
                lang_code,
                player_name,
                player_gender,
            )
            if normalized and normalized.strip():
                entries.append((text_hash, normalized))

        with self._lock:
            self._search_entries_cache[cache_key] = entries
        return entries

    def _get_normalized_text_by_hash(
        self,
        text_hash: str,
        lang_code: str,
        player_name: str,
        player_gender: str,
    ) -> str | None:
        cache_key = (lang_code, player_name, player_gender, text_hash)
        with self._lock:
            if cache_key in self._normalized_text_cache:
                return self._normalized_text_cache[cache_key]

        raw_map = self._load_raw_language_map(lang_code)
        raw_text = raw_map.get(text_hash)
        if raw_text is None:
            return None

        normalized = self._normalize_text(
            raw_text,
            lang_code,
            player_name,
            player_gender,
            depth=0,
        )
        if not normalized or not normalized.strip():
            normalized = None

        with self._lock:
            self._normalized_text_cache[cache_key] = normalized or ""

        return normalized

    def _normalize_text(
        self,
        text: str,
        lang_code: str,
        player_name: str,
        player_gender: str,
        *,
        depth: int,
    ) -> str:
        if depth > MAX_NORMALIZE_DEPTH:
            return text

        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\\n", "\n")
        normalized = TEXTJOIN_PLACEHOLDER_PATTERN.sub(
            lambda match: self._resolve_text_join(
                int(match.group(1)),
                lang_code,
                player_name,
                player_gender,
                depth=depth + 1,
            )
            or match.group(0),
            normalized,
        )
        normalized = MALE_FEMALE_PATTERN.sub(
            lambda match: _resolve_gender_pair(match.group(1), match.group(2), player_gender),
            normalized,
        )
        normalized = FEMALE_MALE_PATTERN.sub(
            lambda match: _resolve_gender_pair(match.group(2), match.group(1), player_gender),
            normalized,
        )
        normalized = normalized.replace("{NICKNAME}", player_name)

        if normalized.startswith("#"):
            normalized = normalized[1:]
        return normalized

    def _resolve_text_join(
        self,
        text_join_id: int,
        lang_code: str,
        player_name: str,
        player_gender: str,
        *,
        depth: int,
    ) -> str | None:
        item_hash_by_id, config_by_id = self._load_text_join_indexes()
        item_ids = config_by_id.get(text_join_id)
        if not item_ids:
            return None

        raw_map = self._load_raw_language_map(lang_code)
        parts: List[str] = []
        seen_parts: set[str] = set()

        for item_id in item_ids:
            text_hash = item_hash_by_id.get(item_id)
            if not text_hash:
                continue
            raw_text = raw_map.get(text_hash)
            if raw_text is None:
                continue
            normalized = self._normalize_text(
                raw_text,
                lang_code,
                player_name,
                player_gender,
                depth=depth,
            ).strip()
            if not normalized or normalized in seen_parts:
                continue
            seen_parts.add(normalized)
            parts.append(normalized)

        if not parts:
            return None
        return "/".join(parts)

    def _load_text_join_indexes(self) -> Tuple[Dict[int, str], Dict[int, List[int]]]:
        with self._lock:
            if self._text_join_items is not None and self._text_join_configs is not None:
                return self._text_join_items, self._text_join_configs

        item_hash_by_id: Dict[int, str] = {}
        config_by_id: Dict[int, List[int]] = {}

        item_file = self.excel_output_dir / "TextJoinItem.json"
        config_file = self.excel_output_dir / "TextJoinConfig.json"

        if item_file.is_file():
            with item_file.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            for row in payload:
                item_id = row.get("TextJoinItemID")
                hash_value = row.get("TextJoinText", {}).get("Hash")
                if item_id is None or hash_value is None:
                    continue
                item_hash_by_id[int(item_id)] = str(hash_value)

        if config_file.is_file():
            with config_file.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            for row in payload:
                join_id = row.get("TextJoinID")
                item_ids = [int(item_id) for item_id in row.get("TextJoinItemList", []) if item_id is not None]
                default_item = row.get("DefaultItem")
                if not item_ids and default_item is not None:
                    item_ids = [int(default_item)]
                if join_id is None or not item_ids:
                    continue
                config_by_id[int(join_id)] = item_ids

        with self._lock:
            self._text_join_items = item_hash_by_id
            self._text_join_configs = config_by_id

        return item_hash_by_id, config_by_id

    def _resolve_result_languages(self, result_langs: List[str], search_lang: str) -> List[str]:
        supported = self._discover_files()
        normalized_codes: List[str] = []
        seen_codes: set[str] = set()

        ordered_input = [search_lang, *result_langs]
        for code in ordered_input:
            normalized = str(code).strip().lower()
            if not normalized:
                continue
            if normalized not in supported:
                raise InvalidLanguageError(f"不支持的语言代码：{normalized}")
            if normalized in seen_codes:
                continue
            seen_codes.add(normalized)
            normalized_codes.append(normalized)

        if not normalized_codes:
            return [search_lang]

        return normalized_codes

    @staticmethod
    def _normalize_player_name(player_name: str | None) -> str:
        normalized = (player_name or "").strip()
        return normalized or DEFAULT_PLAYER_NAME

    @staticmethod
    def _normalize_player_gender(player_gender: str) -> str:
        normalized = str(player_gender or "").strip().lower()
        if normalized not in VALID_PLAYER_GENDERS:
            raise InvalidPlayerGenderError("玩家性别必须是 male、female 或 both。")
        return normalized

    @staticmethod
    def _normalize_keyword(keyword: str) -> str:
        return " ".join(keyword.strip().split())


def _hash_sort_key(item: Tuple[str, str]) -> Tuple[int, str]:
    text_hash = item[0]
    try:
        return (0, int(text_hash))
    except ValueError:
        return (1, text_hash)


def _resolve_gender_pair(male_text: str, female_text: str, player_gender: str) -> str:
    if player_gender == "male":
        return male_text
    if player_gender == "female":
        return female_text
    return f"{{{male_text}/{female_text}}}"
