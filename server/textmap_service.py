from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from data_paths import DATA_ROOT, DB_PATH, TEXTMAP_ROOT
from dbBuild.builder import (
    DEFAULT_PLAYER_GENDER,
    DEFAULT_PLAYER_NAME,
    DEFAULT_SOURCE_LANGUAGE,
    LANGUAGE_LABELS,
    LANGUAGE_ORDER,
    StarrailDatabaseBuilder,
    TextMapCache,
    normalize_hash,
    normalize_text_for_search,
    summarize_text,
)


DEFAULT_LANGUAGE = "chs"
DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100
VALID_PLAYER_GENDERS = {"male", "female", "both"}

SOURCE_TYPE_PRIORITY = {
    "mission": 1,
    "message": 2,
    "book": 3,
    "voice": 4,
    "story": 5,
}

ROLE_PRIORITY = {
    "content": 0,
    "content_alt": 1,
    "option": 2,
    "title": 3,
    "speaker": 4,
    "series": 5,
    "comment": 6,
    "signature": 7,
    "preview": 8,
}

PLACEHOLDER_STORY_TITLES = {
    "角色详情",
    "character details",
    "character detail",
}

SEARCH_CACHE_LIMIT = 96


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
    def __init__(self, data_root: Path | None = None, db_path: Path = DB_PATH):
        self.data_root = data_root or DATA_ROOT
        self.textmap_dir = TEXTMAP_ROOT
        self.db_path = db_path
        self._build_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._search_cache: dict[tuple[Any, ...], dict[str, object]] = {}

    def get_meta(self, source_lang: str = DEFAULT_SOURCE_LANGUAGE) -> dict[str, object]:
        self._ensure_database()
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        with self._connect() as connection:
            cursor = connection.cursor()
            language_rows = cursor.execute(
                "SELECT code, label FROM language_dim ORDER BY sort_order"
            ).fetchall()
            current_version_row = cursor.execute(
                "SELECT version_tag, raw_version FROM version_dim WHERE is_current=1 LIMIT 1"
            ).fetchone()
            message_camps = self._get_message_camp_options(connection, normalized_source_lang)
            cursor.close()
        return {
            "languages": [
                {"code": row["code"], "label": row["label"]}
                for row in language_rows
                if row["code"] in LANGUAGE_ORDER
            ],
            "defaultLanguage": DEFAULT_LANGUAGE,
            "defaultSourceLanguage": DEFAULT_SOURCE_LANGUAGE,
            "dataAvailable": self.textmap_dir.is_dir(),
            "databaseAvailable": self.db_path.is_file(),
            "dataDir": str(self.textmap_dir),
            "dbPath": str(self.db_path),
            "currentVersion": current_version_row["version_tag"] if current_version_row else "",
            "currentVersionRaw": current_version_row["raw_version"] if current_version_row else "",
            "messageCamps": message_camps,
            "availablePages": [
                "search",
                "mission-book",
                "message",
                "voice",
                "story",
                "settings",
                "detail",
            ],
        }

    def get_versions(self) -> dict[str, object]:
        self._ensure_database()
        with self._connect() as connection:
            cursor = connection.cursor()
            rows = cursor.execute(
                "SELECT version_tag, raw_version FROM version_dim ORDER BY version_sort_key DESC, id DESC"
            ).fetchall()
            current_row = cursor.execute(
                "SELECT version_tag, raw_version FROM version_dim WHERE is_current=1 LIMIT 1"
            ).fetchone()
            cursor.close()
        versions = [row["version_tag"] for row in rows]
        return {
            "versions": versions,
            "currentVersion": current_row["version_tag"] if current_row else "",
            "currentVersionRaw": current_row["raw_version"] if current_row else "",
        }

    def search(
        self,
        keyword: str,
        lang_code: str,
        page: int,
        size: int,
        *,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
        created_version: str | None = None,
        updated_version: str | None = None,
        source_types: list[str] | None = None,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_keyword = self._normalize_keyword(keyword)
        if not normalized_keyword:
            raise InvalidQueryError("请输入要搜索的关键词。")

        normalized_language = self._normalize_language_code(lang_code)
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_result_langs = self._resolve_result_languages(result_langs or [], normalized_language)
        normalized_player_name = self._normalize_player_name(player_name)
        normalized_player_gender = self._normalize_player_gender(player_gender)
        page, size = self._normalize_page(page, size)
        normalized_source_types = [self._normalize_source_type(item) for item in source_types or [] if item]
        cache_key = self._build_search_cache_key(
            keyword=normalized_keyword,
            lang_code=normalized_language,
            page=page,
            size=size,
            result_langs=normalized_result_langs,
            player_name=normalized_player_name,
            player_gender=normalized_player_gender,
            created_version=created_version,
            updated_version=updated_version,
            source_types=normalized_source_types,
            source_lang=normalized_source_lang,
        )
        cached_payload = self._get_cached_search_payload(cache_key)
        if cached_payload is not None:
            return cached_payload

        with self._connect() as connection:
            resolver = TextMapCache(connection)
            total = self._count_text_search(
                connection,
                normalized_keyword,
                normalized_language,
                created_version,
                updated_version,
                normalized_source_types,
            )
            rows = self._query_text_search(
                connection,
                normalized_keyword,
                normalized_language,
                created_version,
                updated_version,
                normalized_source_types,
                limit=size,
                offset=(page - 1) * size,
            )
            results = self._build_text_search_results(
                connection,
                resolver,
                rows,
                normalized_result_langs,
                source_lang=normalized_source_lang,
                player_name=normalized_player_name,
                player_gender=normalized_player_gender,
            )

        payload = {
            "keyword": keyword,
            "lang": normalized_language,
            "resultLangs": normalized_result_langs,
            "sourceLang": normalized_source_lang,
            "playerName": normalized_player_name,
            "playerGender": normalized_player_gender,
            "page": page,
            "size": size,
            "total": total,
            "results": results,
        }
        self._set_cached_search_payload(cache_key, payload)
        return payload

    def get_text_sources(
        self,
        text_hash: str,
        *,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_hash = normalize_hash(text_hash)
        if not normalized_hash:
            raise InvalidQueryError("缺少有效的文本哈希。")

        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_result_langs = self._resolve_result_languages(result_langs or [], DEFAULT_LANGUAGE)
        normalized_player_name = self._normalize_player_name(player_name)
        normalized_player_gender = self._normalize_player_gender(player_gender)

        with self._connect() as connection:
            resolver = TextMapCache(connection)
            translates = self._resolve_translations(
                resolver,
                normalized_hash,
                normalized_result_langs,
                player_name=normalized_player_name,
                player_gender=normalized_player_gender,
            )
            source_rows = self._query_sources_by_hash(connection, normalized_hash)
            sources = [
                self._build_source_object(
                    connection,
                    resolver,
                    row,
                    normalized_source_lang,
                    player_name=normalized_player_name,
                    player_gender=normalized_player_gender,
                )
                for row in source_rows
            ]

        return {
            "hash": normalized_hash,
            "translates": translates,
            "sources": sources,
            "sourceCount": len(sources),
        }

    def search_missions(
        self,
        keyword: str,
        *,
        lang_code: str,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        created_version: str | None = None,
        updated_version: str | None = None,
        page: int = 1,
        size: int = 30,
    ) -> dict[str, object]:
        return self._search_entities(
            entity_type="mission",
            keyword=keyword,
            lang_code=lang_code,
            source_lang=source_lang,
            created_version=created_version,
            updated_version=updated_version,
            page=page,
            size=size,
        )

    def search_books(
        self,
        keyword: str,
        *,
        lang_code: str,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        created_version: str | None = None,
        updated_version: str | None = None,
        page: int = 1,
        size: int = 30,
    ) -> dict[str, object]:
        return self._search_entities(
            entity_type="book",
            keyword=keyword,
            lang_code=lang_code,
            source_lang=source_lang,
            created_version=created_version,
            updated_version=updated_version,
            page=page,
            size=size,
        )

    def search_messages(
        self,
        keyword: str,
        *,
        lang_code: str,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        camp: str | None = None,
        created_version: str | None = None,
        updated_version: str | None = None,
        page: int = 1,
        size: int = 60,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_language = self._normalize_language_code(lang_code)
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        page, size = self._normalize_page(page, min(size, 120))
        normalized_camp = int(camp) if str(camp or "").strip().isdigit() else None
        keyword_text = self._normalize_keyword(keyword)

        with self._connect() as connection:
            resolver = TextMapCache(connection)
            rows = self._query_message_threads(
                connection,
                keyword=keyword_text,
                lang_code=normalized_language,
                created_version=created_version,
                updated_version=updated_version,
                camp=normalized_camp,
            )
            grouped_rows: list[dict[str, object]] = []
            grouped_map: dict[str, dict[str, object]] = {}
            for row in rows:
                display_name = self._resolve_message_thread_name(connection, resolver, row, normalized_source_lang)
                preview = resolver.get_normalized_text(
                    row["latest_preview_hash"],
                    normalized_language,
                    player_name=DEFAULT_PLAYER_NAME,
                    player_gender=DEFAULT_PLAYER_GENDER,
                )
                contact_key = (
                    f"contact:{int(row['contact_id'])}"
                    if row["contact_id"] is not None
                    else f"thread:{int(row['thread_id'])}"
                )
                grouped = grouped_map.get(contact_key)
                if grouped is None:
                    grouped = {
                        "threadId": int(row["thread_id"]),
                        "contactId": int(row["contact_id"]) if row["contact_id"] is not None else None,
                        "threadIds": [int(row["thread_id"])],
                        "displayName": display_name,
                        "avatarKey": str(row["icon_path"] or display_name[:2]),
                        "threadType": str(row["thread_type"] or "contact"),
                        "camp": self._resolve_message_camp(connection, resolver, row["camp"], normalized_source_lang),
                        "messageCount": int(row["message_count"] or 0),
                        "latestPreview": summarize_text(preview),
                        "linkedMainMissionId": int(row["linked_main_mission_id"]) if row["linked_main_mission_id"] else None,
                        "createdVersionId": int(row["created_version_id"] or 0),
                        "updatedVersionId": int(row["updated_version_id"] or 0),
                        "createdSortKey": int(row["created_sort_key"] or 0),
                        "updatedSortKey": int(row["updated_sort_key"] or 0),
                    }
                    grouped_map[contact_key] = grouped
                    grouped_rows.append(grouped)
                    continue

                grouped["threadIds"].append(int(row["thread_id"]))
                grouped["messageCount"] = int(grouped["messageCount"]) + int(row["message_count"] or 0)
                if preview:
                    grouped["latestPreview"] = summarize_text(preview)
                if not grouped["linkedMainMissionId"] and row["linked_main_mission_id"]:
                    grouped["linkedMainMissionId"] = int(row["linked_main_mission_id"])

                created_sort_key = int(row["created_sort_key"] or 0)
                if created_sort_key and (
                    int(grouped["createdSortKey"]) == 0 or created_sort_key < int(grouped["createdSortKey"])
                ):
                    grouped["createdSortKey"] = created_sort_key
                    grouped["createdVersionId"] = int(row["created_version_id"] or 0)

                updated_sort_key = int(row["updated_sort_key"] or 0)
                if updated_sort_key >= int(grouped["updatedSortKey"]):
                    grouped["updatedSortKey"] = updated_sort_key
                    grouped["updatedVersionId"] = int(row["updated_version_id"] or 0)

            contact_ids = [
                int(item["contactId"])
                for item in grouped_rows
                if item["contactId"] is not None
            ]
            if contact_ids:
                placeholders = ",".join("?" for _ in contact_ids)
                all_contact_threads = connection.execute(
                    """
                    SELECT mt.*, COALESCE(cv.version_sort_key, 0) AS created_sort_key,
                           COALESCE(uv.version_sort_key, 0) AS updated_sort_key
                    FROM message_thread mt
                    LEFT JOIN version_dim cv ON cv.id = mt.created_version_id
                    LEFT JOIN version_dim uv ON uv.id = mt.updated_version_id
                    WHERE mt.contact_id IN (""" + placeholders + """)
                    ORDER BY COALESCE(cv.version_sort_key, 0) ASC, COALESCE(mt.contact_id, mt.thread_id) ASC, mt.thread_id ASC
                    """,
                    contact_ids,
                ).fetchall()
                for row in all_contact_threads:
                    contact_key = f"contact:{int(row['contact_id'])}"
                    grouped = grouped_map.get(contact_key)
                    if grouped is None or int(row["thread_id"]) in grouped["threadIds"]:
                        continue

                    display_name = self._resolve_message_thread_name(connection, resolver, row, normalized_source_lang)
                    preview = resolver.get_normalized_text(
                        row["latest_preview_hash"],
                        normalized_language,
                        player_name=DEFAULT_PLAYER_NAME,
                        player_gender=DEFAULT_PLAYER_GENDER,
                    )
                    grouped["displayName"] = grouped["displayName"] or display_name
                    grouped["avatarKey"] = grouped["avatarKey"] or str(row["icon_path"] or display_name[:2])
                    grouped["threadIds"].append(int(row["thread_id"]))
                    grouped["messageCount"] = int(grouped["messageCount"]) + int(row["message_count"] or 0)
                    if preview:
                        grouped["latestPreview"] = summarize_text(preview)
                    if not grouped["linkedMainMissionId"] and row["linked_main_mission_id"]:
                        grouped["linkedMainMissionId"] = int(row["linked_main_mission_id"])

                    created_sort_key = int(row["created_sort_key"] or 0)
                    if created_sort_key and (
                        int(grouped["createdSortKey"]) == 0 or created_sort_key < int(grouped["createdSortKey"])
                    ):
                        grouped["createdSortKey"] = created_sort_key
                        grouped["createdVersionId"] = int(row["created_version_id"] or 0)

                    updated_sort_key = int(row["updated_sort_key"] or 0)
                    if updated_sort_key >= int(grouped["updatedSortKey"]):
                        grouped["updatedSortKey"] = updated_sort_key
                        grouped["updatedVersionId"] = int(row["updated_version_id"] or 0)

            total = len(grouped_rows)
            paged_rows = grouped_rows[(page - 1) * size:(page - 1) * size + size]
            result_rows = [
                {
                    "threadId": int(item["threadId"]),
                    "contactId": item["contactId"],
                    "threadIds": list(item["threadIds"]),
                    "displayName": str(item["displayName"]),
                    "avatarKey": str(item["avatarKey"]),
                    "threadType": str(item["threadType"]),
                    "camp": item["camp"],
                    "messageCount": int(item["messageCount"]),
                    "latestPreview": str(item["latestPreview"] or ""),
                    "linkedMainMissionId": item["linkedMainMissionId"],
                    "createdVersion": self._resolve_version_tag(connection, item["createdVersionId"]),
                    "updatedVersion": self._resolve_version_tag(connection, item["updatedVersionId"]),
                }
                for item in paged_rows
            ]

        return {
            "keyword": keyword,
            "lang": normalized_language,
            "sourceLang": normalized_source_lang,
            "page": page,
            "size": size,
            "total": total,
            "results": result_rows,
            "campOptions": self.get_meta(normalized_source_lang).get("messageCamps", []),
        }

    def search_voices(
        self,
        keyword: str,
        *,
        lang_code: str,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        created_version: str | None = None,
        updated_version: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
        page: int = 1,
        size: int = 30,
    ) -> dict[str, object]:
        return self._search_avatar_entries(
            kind="voice",
            keyword=keyword,
            lang_code=lang_code,
            source_lang=source_lang,
            created_version=created_version,
            updated_version=updated_version,
            player_gender=player_gender,
            page=page,
            size=size,
        )

    def search_stories(
        self,
        keyword: str,
        *,
        lang_code: str,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        created_version: str | None = None,
        updated_version: str | None = None,
        page: int = 1,
        size: int = 30,
    ) -> dict[str, object]:
        return self._search_avatar_entries(
            kind="story",
            keyword=keyword,
            lang_code=lang_code,
            source_lang=source_lang,
            created_version=created_version,
            updated_version=updated_version,
            page=page,
            size=size,
        )

    def search_avatars(
        self,
        kind: str,
        *,
        avatar_keyword: str,
        keyword: str,
        lang_code: str,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        created_version: str | None = None,
        updated_version: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_kind = self._normalize_avatar_kind(kind)
        normalized_language = self._normalize_language_code(lang_code)
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_avatar_keyword = self._normalize_keyword(avatar_keyword)
        normalized_keyword = self._normalize_keyword(keyword)
        normalized_player_gender = self._normalize_player_gender(player_gender)

        if not normalized_avatar_keyword and not normalized_keyword and not created_version and not updated_version:
            return {
                "kind": normalized_kind,
                "avatarKeyword": avatar_keyword,
                "keyword": keyword,
                "lang": normalized_language,
                "sourceLang": normalized_source_lang,
                "total": 0,
                "results": [],
            }

        with self._connect() as connection:
            resolver = TextMapCache(connection)
            entries = self._collect_avatar_entries(
                connection,
                resolver,
                kind=normalized_kind,
                lang_code=normalized_language,
                source_lang=normalized_source_lang,
                avatar_keyword=normalized_avatar_keyword,
                keyword=normalized_keyword,
                created_version=created_version,
                updated_version=updated_version,
                player_gender=normalized_player_gender,
                include_translations=False,
            )

        grouped: dict[int, dict[str, object]] = {}
        for entry in entries:
            avatar_id = int(entry["avatarId"])
            existing = grouped.get(avatar_id)
            if existing is None:
                grouped[avatar_id] = {
                    "avatarId": avatar_id,
                    "name": entry["avatarName"],
                    "entryCount": 1,
                    "createdSortKey": int(entry["createdSortKey"]),
                }
                continue
            existing["entryCount"] = int(existing["entryCount"]) + 1
            existing["createdSortKey"] = min(int(existing["createdSortKey"]), int(entry["createdSortKey"]))

        results = sorted(
            grouped.values(),
            key=lambda item: (int(item["createdSortKey"]), int(item["avatarId"])),
        )
        for item in results:
            item.pop("createdSortKey", None)

        return {
            "kind": normalized_kind,
            "avatarKeyword": avatar_keyword,
            "keyword": keyword,
            "lang": normalized_language,
            "sourceLang": normalized_source_lang,
            "total": len(results),
            "results": results,
        }

    def get_avatar_entries(
        self,
        kind: str,
        *,
        avatar_id: int,
        keyword: str,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        result_langs: list[str] | None = None,
        created_version: str | None = None,
        updated_version: str | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_kind = self._normalize_avatar_kind(kind)
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_result_langs = self._resolve_result_languages(result_langs or [], normalized_source_lang)
        normalized_player_name = self._normalize_player_name(player_name)
        normalized_player_gender = self._normalize_player_gender(player_gender)
        normalized_keyword = self._normalize_keyword(keyword)

        with self._connect() as connection:
            resolver = TextMapCache(connection)
            entries = self._collect_avatar_entries(
                connection,
                resolver,
                kind=normalized_kind,
                lang_code=normalized_source_lang,
                source_lang=normalized_source_lang,
                avatar_keyword="",
                keyword=normalized_keyword,
                created_version=created_version,
                updated_version=updated_version,
                player_name=normalized_player_name,
                player_gender=normalized_player_gender,
                include_translations=True,
                result_langs=normalized_result_langs,
                avatar_id=avatar_id,
            )

        avatar_name = entries[0]["avatarName"] if entries else ""
        return {
            "kind": normalized_kind,
            "avatarId": avatar_id,
            "avatarName": avatar_name,
            "keyword": keyword,
            "sourceLang": normalized_source_lang,
            "resultLangs": normalized_result_langs,
            "total": len(entries),
            "results": entries,
        }

    def get_mission_detail(
        self,
        mission_id: int,
        *,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        with self._connect() as connection:
            resolver = TextMapCache(connection)
            mission = connection.execute(
                "SELECT * FROM mission WHERE mission_id=?",
                (mission_id,),
            ).fetchone()
            if mission is None:
                raise DataUnavailableError(f"未找到任务：{mission_id}")
            normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
            normalized_result_langs = self._resolve_result_languages(result_langs or [], normalized_source_lang)
            normalized_player_name = self._normalize_player_name(player_name)
            normalized_player_gender = self._normalize_player_gender(player_gender)
            title = resolver.get_normalized_text(
                mission["name_hash"],
                normalized_source_lang,
                prefer_main=True,
                player_name=normalized_player_name,
                player_gender=normalized_player_gender,
            ) or f"任务 {mission_id}"
            line_rows = connection.execute(
                """
                SELECT story_path, line_order, line_type, talk_sentence_id, speaker_hash, text_hash
                FROM mission_line
                WHERE mission_id=?
                ORDER BY line_order
                """,
                (mission_id,),
            ).fetchall()
            lines = [
                self._build_dialogue_line(
                    resolver,
                    row,
                    source_lang=normalized_source_lang,
                    result_langs=normalized_result_langs,
                    player_name=normalized_player_name,
                    player_gender=normalized_player_gender,
                )
                for row in line_rows
            ]
            return {
                "kind": "mission",
                "missionId": mission_id,
                "title": title,
                "storyPaths": json.loads(mission["story_paths_json"] or "[]"),
                "createdVersion": self._resolve_version_tag(connection, mission["created_version_id"]),
                "updatedVersion": self._resolve_version_tag(connection, mission["updated_version_id"]),
                "lines": lines,
            }

    def get_book_detail(
        self,
        book_id: int,
        *,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        with self._connect() as connection:
            resolver = TextMapCache(connection)
            row = connection.execute("SELECT * FROM book WHERE book_id=?", (book_id,)).fetchone()
            if row is None:
                raise DataUnavailableError(f"未找到书籍：{book_id}")
            normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
            normalized_result_langs = self._resolve_result_languages(result_langs or [], normalized_source_lang)
            normalized_player_name = self._normalize_player_name(player_name)
            normalized_player_gender = self._normalize_player_gender(player_gender)
            return {
                "kind": "book",
                "bookId": book_id,
                "title": resolver.get_normalized_text(
                    row["title_hash"], normalized_source_lang, prefer_main=True,
                    player_name=normalized_player_name, player_gender=normalized_player_gender,
                ) or f"书籍 {book_id}",
                "series": resolver.get_normalized_text(
                    row["series_name_hash"], normalized_source_lang, prefer_main=True,
                    player_name=normalized_player_name, player_gender=normalized_player_gender,
                ),
                "comment": resolver.get_normalized_text(
                    row["series_comment_hash"], normalized_source_lang, prefer_main=True,
                    player_name=normalized_player_name, player_gender=normalized_player_gender,
                ),
                "createdVersion": self._resolve_version_tag(connection, row["created_version_id"]),
                "updatedVersion": self._resolve_version_tag(connection, row["updated_version_id"]),
                "translates": self._resolve_translations(
                    resolver,
                    row["content_hash"],
                    normalized_result_langs,
                    player_name=normalized_player_name,
                    player_gender=normalized_player_gender,
                ),
            }

    def get_message_detail(
        self,
        thread_id: int,
        *,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_result_langs = self._resolve_result_languages(result_langs or [], normalized_source_lang)
        normalized_player_name = self._normalize_player_name(player_name)
        normalized_player_gender = self._normalize_player_gender(player_gender)

        with self._connect() as connection:
            resolver = TextMapCache(connection)
            thread = connection.execute(
                "SELECT * FROM message_thread WHERE thread_id=?",
                (thread_id,),
            ).fetchone()
            if thread is None:
                raise DataUnavailableError(f"未找到短信线程：{thread_id}")
            if thread["contact_id"] is not None:
                thread_rows = connection.execute(
                    """
                    SELECT mt.*, COALESCE(cv.version_sort_key, 0) AS created_sort_key,
                           COALESCE(uv.version_sort_key, 0) AS updated_sort_key
                    FROM message_thread mt
                    LEFT JOIN version_dim cv ON cv.id = mt.created_version_id
                    LEFT JOIN version_dim uv ON uv.id = mt.updated_version_id
                    WHERE mt.contact_id=?
                    ORDER BY COALESCE(cv.version_sort_key, 0) ASC, mt.thread_id ASC
                    """,
                    (int(thread["contact_id"]),),
                ).fetchall()
            else:
                thread_rows = [thread]

            section_payloads = []
            flat_nodes = []
            total_message_count = 0
            linked_main_mission_id = None
            signature = ""
            created_version_id = int(thread_rows[0]["created_version_id"] or 0) if thread_rows else 0
            updated_version_id = int(thread_rows[0]["updated_version_id"] or 0) if thread_rows else 0
            created_sort_key = int(thread_rows[0]["created_sort_key"] or 0) if thread_rows else 0
            updated_sort_key = int(thread_rows[0]["updated_sort_key"] or 0) if thread_rows else 0

            for thread_index, thread_row in enumerate(thread_rows, start=1):
                if not signature:
                    signature = resolver.get_normalized_text(
                        thread_row["signature_hash"],
                        normalized_source_lang,
                        prefer_main=True,
                        player_name=normalized_player_name,
                        player_gender=normalized_player_gender,
                    )
                if linked_main_mission_id is None and thread_row["linked_main_mission_id"]:
                    linked_main_mission_id = int(thread_row["linked_main_mission_id"])
                total_message_count += int(thread_row["message_count"] or 0)

                row_created_sort_key = int(thread_row["created_sort_key"] or 0)
                if row_created_sort_key and (created_sort_key == 0 or row_created_sort_key < created_sort_key):
                    created_sort_key = row_created_sort_key
                    created_version_id = int(thread_row["created_version_id"] or 0)

                row_updated_sort_key = int(thread_row["updated_sort_key"] or 0)
                if row_updated_sort_key >= updated_sort_key:
                    updated_sort_key = row_updated_sort_key
                    updated_version_id = int(thread_row["updated_version_id"] or 0)

                sections = connection.execute(
                    "SELECT * FROM message_section WHERE thread_id=? ORDER BY section_id",
                    (int(thread_row["thread_id"]),),
                ).fetchall()
                items = connection.execute(
                    "SELECT * FROM message_item WHERE thread_id=? ORDER BY item_order, item_id",
                    (int(thread_row["thread_id"]),),
                ).fetchall()
                items_by_id = {int(item["item_id"]): item for item in items}

                for section in sections:
                    nodes = []
                    visited: set[int] = set()
                    start_ids = [int(value) for value in json.loads(section["start_item_ids_json"] or "[]")]
                    for start_id in start_ids:
                        self._append_message_nodes(
                            nodes,
                            items_by_id,
                            resolver,
                            visited,
                            start_id,
                            source_lang=normalized_source_lang,
                            result_langs=normalized_result_langs,
                            player_name=normalized_player_name,
                            player_gender=normalized_player_gender,
                        )
                    flat_nodes.extend(nodes)
                    section_linked_mission_id = int(section["linked_main_mission_id"]) if section["linked_main_mission_id"] else None
                    section_index = len(section_payloads) + 1
                    section_payloads.append(
                        {
                            "sectionId": int(section["section_id"]),
                            "threadId": int(thread_row["thread_id"]),
                            "index": section_index,
                            "title": (
                                f"主线 {section_linked_mission_id}"
                                if section_linked_mission_id
                                else f"短信段落 {section_index}"
                            ),
                            "linkedMainMissionId": section_linked_mission_id,
                            "messageCount": len(nodes),
                            "nodes": nodes,
                        }
                    )

            return {
                "kind": "message",
                "threadId": thread_id,
                "threadIds": [int(row["thread_id"]) for row in thread_rows],
                "contactId": int(thread["contact_id"]) if thread["contact_id"] is not None else None,
                "displayName": self._resolve_message_thread_name(connection, resolver, thread, normalized_source_lang),
                "threadType": str(thread["thread_type"] or "contact"),
                "camp": self._resolve_message_camp(connection, resolver, thread["camp"], normalized_source_lang),
                "signature": signature,
                "messageCount": total_message_count,
                "linkedMainMissionId": linked_main_mission_id,
                "createdVersion": self._resolve_version_tag(connection, created_version_id),
                "updatedVersion": self._resolve_version_tag(connection, updated_version_id),
                "nodes": flat_nodes,
                "sections": section_payloads,
            }

    def get_voice_detail(
        self,
        entry_key: str,
        *,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_result_langs = self._resolve_result_languages(result_langs or [], normalized_source_lang)
        normalized_player_name = self._normalize_player_name(player_name)
        normalized_player_gender = self._normalize_player_gender(player_gender)
        with self._connect() as connection:
            resolver = TextMapCache(connection)
            row = connection.execute(
                """
                SELECT ve.*, a.name_hash, a.full_name_hash
                FROM voice_entry ve
                LEFT JOIN avatar a ON a.avatar_id = ve.avatar_id
                WHERE ve.entry_key=?
                """,
                (entry_key,),
            ).fetchone()
            if row is None:
                raise DataUnavailableError(f"未找到角色语音：{entry_key}")
            avatar_name = resolver.get_normalized_text(
                row["name_hash"], normalized_source_lang, prefer_main=True,
                player_name=normalized_player_name, player_gender=normalized_player_gender,
            ) or resolver.get_normalized_text(
                row["full_name_hash"], normalized_source_lang, prefer_main=True,
                player_name=normalized_player_name, player_gender=normalized_player_gender,
            )
            title = resolver.get_normalized_text(
                row["title_hash"], normalized_source_lang, prefer_main=True,
                player_name=normalized_player_name, player_gender=normalized_player_gender,
            )
            content_hash = row["text_hash_f"] if normalized_player_gender == "female" and row["text_hash_f"] else row["text_hash_m"] or row["text_hash_f"]
            return {
                "kind": "voice",
                "entryKey": entry_key,
                "avatarName": avatar_name,
                "title": title or f"角色语音 {row['voice_id']}",
                "voiceId": int(row["voice_id"]),
                "voicePath": str(row["voice_path"] or ""),
                "createdVersion": self._resolve_version_tag(connection, row["created_version_id"]),
                "updatedVersion": self._resolve_version_tag(connection, row["updated_version_id"]),
                "translates": self._resolve_translations(
                    resolver,
                    content_hash,
                    normalized_result_langs,
                    player_name=normalized_player_name,
                    player_gender=normalized_player_gender,
                ),
            }

    def get_story_detail(
        self,
        entry_key: str,
        *,
        source_lang: str = DEFAULT_SOURCE_LANGUAGE,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_result_langs = self._resolve_result_languages(result_langs or [], normalized_source_lang)
        normalized_player_name = self._normalize_player_name(player_name)
        normalized_player_gender = self._normalize_player_gender(player_gender)
        with self._connect() as connection:
            resolver = TextMapCache(connection)
            row = connection.execute(
                """
                SELECT se.*, a.name_hash, a.full_name_hash
                FROM story_entry se
                LEFT JOIN avatar a ON a.avatar_id = se.avatar_id
                WHERE se.entry_key=?
                """,
                (entry_key,),
            ).fetchone()
            if row is None:
                raise DataUnavailableError(f"未找到角色故事：{entry_key}")
            avatar_name = resolver.get_normalized_text(
                row["name_hash"], normalized_source_lang, prefer_main=True,
                player_name=normalized_player_name, player_gender=normalized_player_gender,
            ) or resolver.get_normalized_text(
                row["full_name_hash"], normalized_source_lang, prefer_main=True,
                player_name=normalized_player_name, player_gender=normalized_player_gender,
            )
            title = resolver.get_normalized_text(
                row["title_hash"], normalized_source_lang, prefer_main=True,
                player_name=normalized_player_name, player_gender=normalized_player_gender,
            )
            content_text = resolver.get_normalized_text(
                row["content_hash"],
                normalized_source_lang,
                player_name=normalized_player_name,
                player_gender=normalized_player_gender,
            )
            return {
                "kind": "story",
                "entryKey": entry_key,
                "avatarName": avatar_name,
                "storyId": int(row["story_id"]),
                "title": self._resolve_story_display_title(title, avatar_name, content_text),
                "createdVersion": self._resolve_version_tag(connection, row["created_version_id"]),
                "updatedVersion": self._resolve_version_tag(connection, row["updated_version_id"]),
                "translates": self._resolve_translations(
                    resolver,
                    row["content_hash"],
                    normalized_result_langs,
                    player_name=normalized_player_name,
                    player_gender=normalized_player_gender,
                ),
            }

    def _search_entities(
        self,
        *,
        entity_type: str,
        keyword: str,
        lang_code: str,
        source_lang: str,
        created_version: str | None,
        updated_version: str | None,
        page: int,
        size: int,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_language = self._normalize_language_code(lang_code)
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        keyword_text = self._normalize_keyword(keyword)
        page, size = self._normalize_page(page, size)
        with self._connect() as connection:
            total, rows = self._query_entity_search(
                connection,
                entity_type=entity_type,
                keyword=keyword_text,
                lang_code=normalized_language,
                created_version=created_version,
                updated_version=updated_version,
                camp=None,
                page=page,
                size=size,
            )
            results = [
                {
                    "entityType": entity_type,
                    "entityKey": str(row["entity_key"]),
                    "title": row["title_text"],
                    "preview": row["preview_text"],
                    "createdVersion": self._resolve_version_tag(connection, row["created_version_id"]),
                    "updatedVersion": self._resolve_version_tag(connection, row["updated_version_id"]),
                    "detailQuery": self._build_detail_query(entity_type, str(row["entity_key"])),
                }
                for row in rows
            ]
        return {
            "keyword": keyword,
            "lang": normalized_language,
            "sourceLang": normalized_source_lang,
            "entityType": entity_type,
            "page": page,
            "size": size,
            "total": total,
            "results": results,
        }

    def _query_entity_search(
        self,
        connection: sqlite3.Connection,
        *,
        entity_type: str,
        keyword: str,
        lang_code: str,
        created_version: str | None,
        updated_version: str | None,
        camp: int | None,
        page: int,
        size: int,
    ) -> tuple[int, list[sqlite3.Row]]:
        params: list[Any] = [entity_type, lang_code]
        filters = ["es.entity_type=?", "es.lang=?"]
        if camp is not None:
            filters.append("es.camp=?")
            params.append(camp)
        created_version_id = self._resolve_version_filter_id(connection, created_version)
        updated_version_id = self._resolve_version_filter_id(connection, updated_version)
        if created_version_id is not None:
            filters.append("es.created_version_id=?")
            params.append(created_version_id)
        if updated_version_id is not None:
            filters.append("es.updated_version_id=?")
            params.append(updated_version_id)

        if keyword:
            fts_query = self._build_fts_query(keyword)
            where_sql = " AND ".join(filters)
            count_sql = (
                "SELECT COUNT(*) FROM entity_search es "
                "JOIN entity_search_fts ON entity_search_fts.rowid = es.id "
                f"WHERE {where_sql} AND entity_search_fts.search_text MATCH ?"
            )
            count_params = [*params, fts_query]
            total = int(connection.execute(count_sql, count_params).fetchone()[0])
            query_sql = (
                "SELECT es.* FROM entity_search es "
                "LEFT JOIN version_dim cv ON cv.id = es.created_version_id "
                "JOIN entity_search_fts ON entity_search_fts.rowid = es.id "
                f"WHERE {where_sql} AND entity_search_fts.search_text MATCH ? "
                "ORDER BY COALESCE(cv.version_sort_key, 0) ASC, CAST(es.entity_key AS INTEGER) ASC, es.entity_key ASC "
                "LIMIT ? OFFSET ?"
            )
            query_params = [*params, fts_query, size, (page - 1) * size]
            rows = connection.execute(query_sql, query_params).fetchall()
            return total, rows

        where_sql = " AND ".join(filters)
        count_sql = f"SELECT COUNT(*) FROM entity_search es WHERE {where_sql}"
        total = int(connection.execute(count_sql, params).fetchone()[0])
        query_sql = (
            "SELECT es.* FROM entity_search es "
            "LEFT JOIN version_dim cv ON cv.id = es.created_version_id "
            f"WHERE {where_sql} "
            "ORDER BY COALESCE(cv.version_sort_key, 0) ASC, CAST(es.entity_key AS INTEGER) ASC, es.entity_key ASC LIMIT ? OFFSET ?"
        )
        rows = connection.execute(query_sql, [*params, size, (page - 1) * size]).fetchall()
        return total, rows

    def _query_message_threads(
        self,
        connection: sqlite3.Connection,
        *,
        keyword: str,
        lang_code: str,
        created_version: str | None,
        updated_version: str | None,
        camp: int | None,
    ) -> list[sqlite3.Row]:
        filters = ["1=1"]
        params: list[Any] = []

        created_version_id = self._resolve_version_filter_id(connection, created_version)
        updated_version_id = self._resolve_version_filter_id(connection, updated_version)
        if created_version_id is not None:
            filters.append("mt.created_version_id=?")
            params.append(created_version_id)
        if updated_version_id is not None:
            filters.append("mt.updated_version_id=?")
            params.append(updated_version_id)
        if camp is not None:
            filters.append("mt.camp=?")
            params.append(int(camp))
        if keyword:
            filters.append(
                "EXISTS ("
                "SELECT 1 FROM entity_search es "
                "JOIN entity_search_fts ON entity_search_fts.rowid = es.id "
                "WHERE es.entity_type='message' "
                "AND es.entity_key = CAST(mt.thread_id AS TEXT) "
                "AND es.lang=? "
                "AND entity_search_fts.search_text MATCH ?"
                ")"
            )
            params.extend([lang_code, self._build_fts_query(keyword)])

        where_sql = " AND ".join(filters)
        sql = (
            "SELECT mt.*, "
            "COALESCE(cv.version_sort_key, 0) AS created_sort_key, "
            "COALESCE(uv.version_sort_key, 0) AS updated_sort_key "
            "FROM message_thread mt "
            "LEFT JOIN version_dim cv ON cv.id = mt.created_version_id "
            "LEFT JOIN version_dim uv ON uv.id = mt.updated_version_id "
            f"WHERE {where_sql} "
            "ORDER BY COALESCE(cv.version_sort_key, 0) ASC, COALESCE(mt.contact_id, mt.thread_id) ASC, mt.thread_id ASC"
        )
        return connection.execute(sql, params).fetchall()

    def _query_text_search(
        self,
        connection: sqlite3.Connection,
        keyword: str,
        lang_code: str,
        created_version: str | None,
        updated_version: str | None,
        source_types: list[str],
        *,
        limit: int,
        offset: int,
    ) -> list[sqlite3.Row]:
        filters = ["tm.scope='normal'", "tm.lang=?"]
        params: list[Any] = [lang_code]
        created_version_id = self._resolve_version_filter_id(connection, created_version)
        updated_version_id = self._resolve_version_filter_id(connection, updated_version)
        if created_version_id is not None:
            filters.append("tm.created_version_id=?")
            params.append(created_version_id)
        if updated_version_id is not None:
            filters.append("tm.updated_version_id=?")
            params.append(updated_version_id)
        if source_types:
            placeholders = ",".join("?" for _ in source_types)
            filters.append(
                "EXISTS ("
                "SELECT 1 FROM text_source_link tsl "
                "JOIN source_record sr ON sr.id = tsl.source_record_id "
                f"WHERE tsl.text_hash = tm.hash AND sr.source_type IN ({placeholders})"
                ")"
            )
            params.extend(source_types)

        fts_query = self._build_text_map_match_query(keyword, lang_code)
        where_sql = " AND ".join(filters)
        sql = (
            "WITH matched(rowid, rank) AS MATERIALIZED ("
            "SELECT rowid, bm25(text_map_fts) FROM text_map_fts WHERE text_map_fts MATCH ?"
            ") "
            "SELECT tm.* FROM matched "
            "JOIN text_map tm ON tm.id = matched.rowid "
            f"WHERE {where_sql} "
            "ORDER BY matched.rank, length(tm.content), tm.hash LIMIT ? OFFSET ?"
        )
        rows = connection.execute(sql, [fts_query, *params, limit, offset]).fetchall()
        return rows

    def _count_text_search(
        self,
        connection: sqlite3.Connection,
        keyword: str,
        lang_code: str,
        created_version: str | None,
        updated_version: str | None,
        source_types: list[str],
    ) -> int:
        filters = ["tm.scope='normal'", "tm.lang=?"]
        params: list[Any] = [lang_code]
        created_version_id = self._resolve_version_filter_id(connection, created_version)
        updated_version_id = self._resolve_version_filter_id(connection, updated_version)
        if created_version_id is not None:
            filters.append("tm.created_version_id=?")
            params.append(created_version_id)
        if updated_version_id is not None:
            filters.append("tm.updated_version_id=?")
            params.append(updated_version_id)
        if source_types:
            placeholders = ",".join("?" for _ in source_types)
            filters.append(
                "EXISTS ("
                "SELECT 1 FROM text_source_link tsl "
                "JOIN source_record sr ON sr.id = tsl.source_record_id "
                f"WHERE tsl.text_hash = tm.hash AND sr.source_type IN ({placeholders})"
                ")"
            )
            params.extend(source_types)
        fts_query = self._build_text_map_match_query(keyword, lang_code)
        where_sql = " AND ".join(filters)
        sql = (
            "WITH matched(rowid) AS MATERIALIZED ("
            "SELECT rowid FROM text_map_fts WHERE text_map_fts MATCH ?"
            ") "
            "SELECT COUNT(*) FROM text_map tm "
            "JOIN matched ON matched.rowid = tm.id "
            f"WHERE {where_sql}"
        )
        return int(connection.execute(sql, [fts_query, *params]).fetchone()[0])

    def _build_text_search_results(
        self,
        connection: sqlite3.Connection,
        resolver: TextMapCache,
        rows: list[sqlite3.Row],
        result_langs: list[str],
        *,
        source_lang: str,
        player_name: str,
        player_gender: str,
    ) -> list[dict[str, object]]:
        if not rows:
            return []

        hashes = [str(row["hash"]) for row in rows]
        version_tag_map = self._get_version_tag_map(connection)
        source_rows_by_hash = self._query_sources_by_hashes(connection, hashes)
        source_core_map = self._prefetch_source_core_map(
            connection,
            resolver,
            source_rows_by_hash,
            source_lang=source_lang,
            player_name=player_name,
            player_gender=player_gender,
        )

        results = []
        for row in rows:
            text_hash = str(row["hash"])
            translates = self._resolve_translations(
                resolver,
                text_hash,
                result_langs,
                player_name=player_name,
                player_gender=player_gender,
            )
            sources = [
                self._build_prefetched_source_object(source_row, source_core_map, version_tag_map)
                for source_row in source_rows_by_hash.get(text_hash, [])
            ]
            primary_source = sources[0] if sources else self._build_unknown_source(text_hash)
            display_created_version = (
                str(primary_source.get("createdVersion") or "")
                or version_tag_map.get(int(row["created_version_id"] or 0), "")
            )
            display_updated_version = (
                str(primary_source.get("updatedVersion") or "")
                or version_tag_map.get(int(row["updated_version_id"] or 0), "")
            )
            results.append(
                {
                    "hash": text_hash,
                    "translates": translates,
                    "createdVersion": display_created_version,
                    "updatedVersion": display_updated_version,
                    "primarySource": primary_source,
                    "sourceCount": len(sources),
                }
            )

        return results

    def _query_sources_by_hashes(
        self,
        connection: sqlite3.Connection,
        hashes: list[str],
    ) -> dict[str, list[sqlite3.Row]]:
        if not hashes:
            return {}
        placeholders = ",".join("?" for _ in hashes)
        sql = (
            "SELECT tsl.text_hash, sr.id AS source_record_id, sr.source_type, sr.source_key, "
            "sr.created_version_id, sr.updated_version_id, tsl.role, tsl.sort_order "
            "FROM text_source_link tsl "
            "JOIN source_record sr ON sr.id = tsl.source_record_id "
            f"WHERE tsl.text_hash IN ({placeholders}) "
            "ORDER BY tsl.text_hash, "
            "CASE tsl.role "
            "WHEN 'content' THEN 0 WHEN 'content_alt' THEN 1 WHEN 'option' THEN 2 "
            "WHEN 'title' THEN 3 WHEN 'speaker' THEN 4 ELSE 9 END, "
            "CASE sr.source_type "
            "WHEN 'mission' THEN 1 WHEN 'message' THEN 2 WHEN 'book' THEN 3 "
            "WHEN 'voice' THEN 4 WHEN 'story' THEN 5 ELSE 99 END, "
            "tsl.sort_order, sr.source_key"
        )
        grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in connection.execute(sql, hashes).fetchall():
            grouped[str(row["text_hash"])].append(row)
        return grouped

    def _prefetch_source_core_map(
        self,
        connection: sqlite3.Connection,
        resolver: TextMapCache,
        source_rows_by_hash: dict[str, list[sqlite3.Row]],
        *,
        source_lang: str,
        player_name: str,
        player_gender: str,
    ) -> dict[tuple[str, str], dict[str, str]]:
        grouped_keys: dict[str, set[str]] = defaultdict(set)
        for rows in source_rows_by_hash.values():
            for row in rows:
                grouped_keys[str(row["source_type"])].add(str(row["source_key"]))

        core_map: dict[tuple[str, str], dict[str, str]] = {}

        if grouped_keys.get("mission"):
            placeholders = ",".join("?" for _ in grouped_keys["mission"])
            sql = f"SELECT mission_id, name_hash FROM mission WHERE mission_id IN ({placeholders})"
            for row in connection.execute(sql, list(grouped_keys["mission"])).fetchall():
                mission_key = str(row["mission_id"])
                core_map[("mission", mission_key)] = {
                    "title": resolver.get_normalized_text(
                        row["name_hash"],
                        source_lang,
                        prefer_main=True,
                        player_name=player_name,
                        player_gender=player_gender,
                    ) or f"任务 {mission_key}",
                    "subtitle": f"任务 {mission_key}",
                }

        if grouped_keys.get("book"):
            placeholders = ",".join("?" for _ in grouped_keys["book"])
            sql = f"SELECT book_id, title_hash, series_name_hash FROM book WHERE book_id IN ({placeholders})"
            for row in connection.execute(sql, list(grouped_keys["book"])).fetchall():
                book_key = str(row["book_id"])
                core_map[("book", book_key)] = {
                    "title": resolver.get_normalized_text(
                        row["title_hash"],
                        source_lang,
                        prefer_main=True,
                        player_name=player_name,
                        player_gender=player_gender,
                    ) or f"书籍 {book_key}",
                    "subtitle": resolver.get_normalized_text(
                        row["series_name_hash"],
                        source_lang,
                        prefer_main=True,
                        player_name=player_name,
                        player_gender=player_gender,
                    ),
                }

        if grouped_keys.get("message"):
            placeholders = ",".join("?" for _ in grouped_keys["message"])
            sql = f"SELECT * FROM message_thread WHERE thread_id IN ({placeholders})"
            for row in connection.execute(sql, list(grouped_keys["message"])).fetchall():
                message_key = str(row["thread_id"])
                core_map[("message", message_key)] = {
                    "title": self._resolve_message_thread_name(connection, resolver, row, source_lang),
                    "subtitle": "群聊" if row["thread_type"] == "group" else "短信",
                }

        if grouped_keys.get("voice"):
            placeholders = ",".join("?" for _ in grouped_keys["voice"])
            sql = (
                f"SELECT ve.entry_key, ve.voice_id, ve.title_hash, a.name_hash, a.full_name_hash "
                "FROM voice_entry ve "
                "LEFT JOIN avatar a ON a.avatar_id = ve.avatar_id "
                f"WHERE ve.entry_key IN ({placeholders})"
            )
            for row in connection.execute(sql, list(grouped_keys["voice"])).fetchall():
                voice_key = str(row["entry_key"])
                avatar_name = self._resolve_avatar_name(
                    resolver,
                    row["name_hash"],
                    row["full_name_hash"],
                    source_lang,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                voice_title = resolver.get_normalized_text(
                    row["title_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                ) or f"角色语音 {row['voice_id']}"
                core_map[("voice", voice_key)] = {
                    "title": " · ".join(part for part in [avatar_name, voice_title] if part),
                    "subtitle": "角色语音",
                }

        if grouped_keys.get("story"):
            placeholders = ",".join("?" for _ in grouped_keys["story"])
            sql = (
                f"SELECT se.entry_key, se.story_id, se.title_hash, se.content_hash, a.name_hash, a.full_name_hash "
                "FROM story_entry se "
                "LEFT JOIN avatar a ON a.avatar_id = se.avatar_id "
                f"WHERE se.entry_key IN ({placeholders})"
            )
            for row in connection.execute(sql, list(grouped_keys["story"])).fetchall():
                story_key = str(row["entry_key"])
                avatar_name = self._resolve_avatar_name(
                    resolver,
                    row["name_hash"],
                    row["full_name_hash"],
                    source_lang,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                story_title = resolver.get_normalized_text(
                    row["title_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                story_content = resolver.get_normalized_text(
                    row["content_hash"],
                    source_lang,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                resolved_title = self._resolve_story_display_title(story_title, avatar_name, story_content)
                core_map[("story", story_key)] = {
                    "title": " · ".join(part for part in [avatar_name, resolved_title] if part),
                    "subtitle": "角色故事",
                }

        return core_map

    def _build_prefetched_source_object(
        self,
        row: sqlite3.Row,
        source_core_map: dict[tuple[str, str], dict[str, str]],
        version_tag_map: dict[int, str],
    ) -> dict[str, object]:
        source_type = str(row["source_type"])
        source_key = str(row["source_key"])
        core = source_core_map.get((source_type, source_key), {})
        return {
            "sourceType": source_type,
            "sourceKey": source_key,
            "title": core.get("title") or f"未归类文本 {source_key}",
            "subtitle": core.get("subtitle") or "",
            "role": str(row["role"] or ""),
            "createdVersion": version_tag_map.get(int(row["created_version_id"] or 0), ""),
            "updatedVersion": version_tag_map.get(int(row["updated_version_id"] or 0), ""),
            "detailQuery": self._build_detail_query(source_type, source_key),
        }

    def _get_version_tag_map(self, connection: sqlite3.Connection) -> dict[int, str]:
        return {
            int(row["id"]): str(row["version_tag"] or "")
            for row in connection.execute("SELECT id, version_tag FROM version_dim").fetchall()
        }

    def _build_text_search_result(
        self,
        connection: sqlite3.Connection,
        resolver: TextMapCache,
        row: sqlite3.Row,
        result_langs: list[str],
        *,
        source_lang: str,
        player_name: str,
        player_gender: str,
    ) -> dict[str, object]:
        text_hash = str(row["hash"])
        translates = self._resolve_translations(
            resolver,
            text_hash,
            result_langs,
            player_name=player_name,
            player_gender=player_gender,
        )
        source_rows = self._query_sources_by_hash(connection, text_hash)
        sources = [
            self._build_source_object(
                connection,
                resolver,
                source_row,
                source_lang,
                player_name=player_name,
                player_gender=player_gender,
            )
            for source_row in source_rows
        ]
        primary_source = sources[0] if sources else self._build_unknown_source(text_hash)
        return {
            "hash": text_hash,
            "translates": translates,
            "createdVersion": self._resolve_version_tag(connection, row["created_version_id"]),
            "updatedVersion": self._resolve_version_tag(connection, row["updated_version_id"]),
            "primarySource": primary_source,
            "sourceCount": len(sources),
        }

    def _resolve_translations(
        self,
        resolver: TextMapCache,
        text_hash: str | None,
        languages: list[str],
        *,
        player_name: str,
        player_gender: str,
    ) -> dict[str, str]:
        translates: dict[str, str] = {}
        for lang in languages:
            translated = resolver.get_normalized_text(
                text_hash,
                lang,
                player_name=player_name,
                player_gender=player_gender,
            )
            if translated:
                translates[lang] = translated
        return translates

    def _query_sources_by_hash(self, connection: sqlite3.Connection, text_hash: str) -> list[sqlite3.Row]:
        sql = (
            "SELECT sr.id AS source_record_id, sr.source_type, sr.source_key, sr.created_version_id, sr.updated_version_id, "
            "tsl.role, tsl.sort_order "
            "FROM text_source_link tsl "
            "JOIN source_record sr ON sr.id = tsl.source_record_id "
            "WHERE tsl.text_hash=? "
            "ORDER BY "
            "CASE tsl.role "
            "WHEN 'content' THEN 0 WHEN 'content_alt' THEN 1 WHEN 'option' THEN 2 "
            "WHEN 'title' THEN 3 WHEN 'speaker' THEN 4 ELSE 9 END, "
            "CASE sr.source_type "
            "WHEN 'mission' THEN 1 WHEN 'message' THEN 2 WHEN 'book' THEN 3 "
            "WHEN 'voice' THEN 4 WHEN 'story' THEN 5 ELSE 99 END, "
            "tsl.sort_order, sr.source_key"
        )
        return connection.execute(sql, (text_hash,)).fetchall()

    def _build_source_object(
        self,
        connection: sqlite3.Connection,
        resolver: TextMapCache,
        row: sqlite3.Row,
        source_lang: str,
        *,
        player_name: str,
        player_gender: str,
    ) -> dict[str, object]:
        source_type = str(row["source_type"])
        source_key = str(row["source_key"])
        title = ""
        subtitle = ""
        if source_type == "mission":
            mission = connection.execute("SELECT mission_id, name_hash FROM mission WHERE mission_id=?", (int(source_key),)).fetchone()
            if mission:
                title = resolver.get_normalized_text(
                    mission["name_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                ) or f"任务 {source_key}"
                subtitle = f"任务 {source_key}"
        elif source_type == "book":
            book = connection.execute("SELECT book_id, title_hash, series_name_hash FROM book WHERE book_id=?", (int(source_key),)).fetchone()
            if book:
                title = resolver.get_normalized_text(
                    book["title_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                ) or f"书籍 {source_key}"
                series = resolver.get_normalized_text(
                    book["series_name_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                subtitle = series
        elif source_type == "message":
            thread = connection.execute("SELECT * FROM message_thread WHERE thread_id=?", (int(source_key),)).fetchone()
            if thread:
                title = self._resolve_message_thread_name(connection, resolver, thread, source_lang)
                subtitle = "群聊" if thread["thread_type"] == "group" else "短信"
        elif source_type == "voice":
            voice = connection.execute(
                """
                SELECT ve.entry_key, ve.voice_id, ve.title_hash, a.name_hash, a.full_name_hash
                FROM voice_entry ve
                LEFT JOIN avatar a ON a.avatar_id = ve.avatar_id
                WHERE ve.entry_key=?
                """,
                (source_key,),
            ).fetchone()
            if voice:
                avatar_name = resolver.get_normalized_text(
                    voice["name_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                ) or resolver.get_normalized_text(
                    voice["full_name_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                voice_title = resolver.get_normalized_text(
                    voice["title_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                title = " · ".join(part for part in [avatar_name, voice_title or f"角色语音 {voice['voice_id']}"] if part)
                subtitle = "角色语音"
        elif source_type == "story":
            story = connection.execute(
                """
                SELECT se.entry_key, se.story_id, se.title_hash, se.content_hash, a.name_hash, a.full_name_hash
                FROM story_entry se
                LEFT JOIN avatar a ON a.avatar_id = se.avatar_id
                WHERE se.entry_key=?
                """,
                (source_key,),
            ).fetchone()
            if story:
                avatar_name = resolver.get_normalized_text(
                    story["name_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                ) or resolver.get_normalized_text(
                    story["full_name_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                story_title = resolver.get_normalized_text(
                    story["title_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                story_content = resolver.get_normalized_text(
                    story["content_hash"],
                    source_lang,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                title = " · ".join(
                    part for part in [avatar_name, self._resolve_story_display_title(story_title, avatar_name, story_content)] if part
                )
                subtitle = "角色故事"

        if not title:
            title = f"未归类文本 {source_key}"

        return {
            "sourceType": source_type,
            "sourceKey": source_key,
            "title": title,
            "subtitle": subtitle,
            "role": str(row["role"] or ""),
            "createdVersion": self._resolve_version_tag(connection, row["created_version_id"]),
            "updatedVersion": self._resolve_version_tag(connection, row["updated_version_id"]),
            "detailQuery": self._build_detail_query(source_type, source_key),
        }

    def _build_unknown_source(self, text_hash: str) -> dict[str, object]:
        return {
            "sourceType": "unknown",
            "sourceKey": text_hash,
            "title": "未归类文本",
            "subtitle": f"TextMap Hash {text_hash}",
            "role": "content",
            "createdVersion": "",
            "updatedVersion": "",
            "detailQuery": {"kind": "text", "hash": text_hash},
        }

    def _build_dialogue_line(
        self,
        resolver: TextMapCache,
        row: sqlite3.Row,
        *,
        source_lang: str,
        result_langs: list[str],
        player_name: str,
        player_gender: str,
    ) -> dict[str, object]:
        speaker = resolver.get_normalized_text(
            row["speaker_hash"],
            source_lang,
            prefer_main=True,
            player_name=player_name,
            player_gender=player_gender,
        )
        translates = self._resolve_translations(
            resolver,
            row["text_hash"],
            result_langs,
            player_name=player_name,
            player_gender=player_gender,
        )
        return {
            "lineOrder": int(row["line_order"]),
            "lineType": str(row["line_type"]),
            "talkSentenceId": int(row["talk_sentence_id"]),
            "speaker": speaker,
            "translates": translates,
        }

    def _collect_message_reachable(
        self,
        items_by_id: dict[int, sqlite3.Row],
        start_ids: list[int],
        *,
        max_nodes: int = 5000,
    ) -> dict[int, int]:
        next_ids_by_item_id: dict[int, list[int]] = {}
        for item_id, item in items_by_id.items():
            next_ids_by_item_id[item_id] = [int(value) for value in json.loads(item["next_item_ids_json"] or "[]")]

        depths: dict[int, int] = {}
        queue: deque[tuple[int, int]] = deque()
        for start_id in start_ids:
            if start_id in items_by_id:
                queue.append((start_id, 0))

        while queue and len(depths) < max_nodes:
            current_id, depth = queue.popleft()
            if current_id in depths:
                continue
            depths[current_id] = depth
            for next_id in next_ids_by_item_id.get(current_id, []):
                if next_id in items_by_id and next_id not in depths:
                    queue.append((next_id, depth + 1))

        return depths

    def _resolve_message_branch_join_id(
        self,
        items_by_id: dict[int, sqlite3.Row],
        branch_start_ids_by_option: dict[int, list[int]],
    ) -> int | None:
        if not branch_start_ids_by_option:
            return None

        reachable_by_option = [
            self._collect_message_reachable(items_by_id, start_ids)
            for start_ids in branch_start_ids_by_option.values()
        ]
        if not reachable_by_option:
            return None

        common: set[int] | None = None
        for reachable in reachable_by_option:
            if common is None:
                common = set(reachable.keys())
            else:
                common &= set(reachable.keys())
            if not common:
                return None

        def sort_key(candidate_id: int) -> tuple[int, int, int]:
            max_depth = max(reachable.get(candidate_id, 10**9) for reachable in reachable_by_option)
            item_order = int(items_by_id[candidate_id]["item_order"] or 0) if candidate_id in items_by_id else 0
            return (max_depth, item_order, candidate_id)

        return min(common, key=sort_key) if common else None

    def _append_message_nodes(
        self,
        nodes: list[dict[str, object]],
        items_by_id: dict[int, sqlite3.Row],
        resolver: TextMapCache,
        visited: set[int],
        item_id: int,
        *,
        source_lang: str,
        result_langs: list[str],
        player_name: str,
        player_gender: str,
        stop_item_ids: set[int] | None = None,
    ) -> None:
        if stop_item_ids and item_id in stop_item_ids:
            return
        if item_id in visited:
            return
        item = items_by_id.get(item_id)
        if item is None:
            return
        visited.add(item_id)
        next_ids = [int(value) for value in json.loads(item["next_item_ids_json"] or "[]")]
        option_children = [items_by_id.get(next_id) for next_id in next_ids]
        option_children = [child for child in option_children if child is not None]

        main_text = self._resolve_translations(
            resolver,
            item["main_text_hash"],
            result_langs,
            player_name=player_name,
            player_gender=player_gender,
        )

        if main_text:
            nodes.append(
                {
                    "type": self._map_message_node_type(item),
                    "sender": self._map_message_sender(item),
                    "itemId": int(item["item_id"]),
                    "itemType": str(item["item_type"] or ""),
                    "translates": main_text,
                }
            )

        if option_children and all(child["option_text_hash"] for child in option_children):
            options = []
            option_branches = []
            branch_start_ids_by_option: dict[int, list[int]] = {}

            for child in option_children:
                child_id = int(child["item_id"])
                visited.add(child_id)
                option_translates = self._resolve_translations(
                    resolver,
                    child["option_text_hash"],
                    result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                content_translates = self._resolve_translations(
                    resolver,
                    child["main_text_hash"],
                    result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                options.append(
                    {
                        "itemId": child_id,
                        "label": option_translates,
                        "content": content_translates,
                    }
                )
                branch_start_ids_by_option[child_id] = [
                    int(value) for value in json.loads(child["next_item_ids_json"] or "[]")
                ]

            join_id = self._resolve_message_branch_join_id(items_by_id, branch_start_ids_by_option)

            for option_item_id, start_ids in branch_start_ids_by_option.items():
                branch_nodes: list[dict[str, object]] = []
                branch_visited: set[int] = set()
                for start_id in start_ids:
                    self._append_message_nodes(
                        branch_nodes,
                        items_by_id,
                        resolver,
                        branch_visited,
                        start_id,
                        source_lang=source_lang,
                        result_langs=result_langs,
                        player_name=player_name,
                        player_gender=player_gender,
                        stop_item_ids={join_id} if join_id else None,
                    )
                if branch_visited:
                    visited.update(branch_visited)
                option_branches.append(
                    {
                        "optionItemId": option_item_id,
                        "nodes": branch_nodes,
                    }
                )

            nodes.append(
                {
                    "type": "option_group",
                    "sender": "player",
                    "groupId": int(item["item_id"]),
                    "options": options,
                    "optionBranches": option_branches,
                }
            )

            if join_id is not None:
                self._append_message_nodes(
                    nodes,
                    items_by_id,
                    resolver,
                    visited,
                    join_id,
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                    stop_item_ids=stop_item_ids,
                )
            return

        for next_id in next_ids:
            self._append_message_nodes(
                nodes,
                items_by_id,
                resolver,
                visited,
                next_id,
                source_lang=source_lang,
                result_langs=result_langs,
                player_name=player_name,
                player_gender=player_gender,
                stop_item_ids=stop_item_ids,
            )

    def _map_message_node_type(self, item: sqlite3.Row) -> str:
        item_type = str(item["item_type"] or "").lower()
        if item_type == "image":
            return "image"
        if item_type == "link":
            return "link"
        return "player" if self._map_message_sender(item) == "player" else "npc"

    def _map_message_sender(self, item: sqlite3.Row) -> str:
        sender = str(item["sender"] or "").lower()
        if sender.startswith("player"):
            return "player"
        return "npc"

    def _resolve_version_tag(self, connection: sqlite3.Connection, version_id: int | None) -> str:
        if not version_id:
            return ""
        row = connection.execute(
            "SELECT version_tag FROM version_dim WHERE id=?",
            (int(version_id),),
        ).fetchone()
        return row["version_tag"] if row else ""

    def _resolve_version_filter_id(self, connection: sqlite3.Connection, version_text: str | None) -> int | None:
        normalized = str(version_text or "").strip()
        if not normalized:
            return None
        row = connection.execute(
            "SELECT id FROM version_dim WHERE version_tag=? OR raw_version=? LIMIT 1",
            (normalized, normalized),
        ).fetchone()
        return int(row["id"]) if row else None

    def _resolve_message_thread_name(
        self,
        connection: sqlite3.Connection,
        resolver: TextMapCache,
        thread: sqlite3.Row,
        source_lang: str,
    ) -> str:
        return (
            resolver.get_normalized_text(thread["display_name_hash"], source_lang, prefer_main=True)
            or f"短信 {thread['thread_id']}"
        )

    def _resolve_message_camp(
        self,
        connection: sqlite3.Connection,
        resolver: TextMapCache,
        camp_id: int | None,
        source_lang: str,
    ) -> dict[str, object] | None:
        if not camp_id:
            return None
        row = connection.execute(
            "SELECT camp_id, name_hash FROM message_camp WHERE camp_id=?",
            (int(camp_id),),
        ).fetchone()
        if row is None:
            return {"id": int(camp_id), "label": "未知阵营"}
        label = resolver.get_normalized_text(row["name_hash"], source_lang, prefer_main=True) or "未知阵营"
        return {"id": int(row["camp_id"]), "label": label}

    def _get_message_camp_options(self, connection: sqlite3.Connection, source_lang: str) -> list[dict[str, object]]:
        resolver = TextMapCache(connection)
        rows = connection.execute(
            "SELECT camp_id, name_hash FROM message_camp ORDER BY sort_id, camp_id"
        ).fetchall()
        return [
            {
                "id": int(row["camp_id"]),
                "label": resolver.get_normalized_text(row["name_hash"], source_lang, prefer_main=True) or "未知阵营",
            }
            for row in rows
        ]

    def _build_detail_query(self, source_type: str, source_key: str) -> dict[str, str]:
        if source_type == "mission":
            return {"kind": "mission", "missionId": source_key}
        if source_type == "book":
            return {"kind": "book", "bookId": source_key}
        if source_type == "message":
            return {"kind": "message", "threadId": source_key}
        if source_type == "voice":
            return {"kind": "voice", "entryKey": source_key}
        if source_type == "story":
            return {"kind": "story", "entryKey": source_key}
        return {"kind": "text", "hash": source_key}

    def _search_avatar_entries(
        self,
        *,
        kind: str,
        keyword: str,
        lang_code: str,
        source_lang: str,
        created_version: str | None,
        updated_version: str | None,
        page: int,
        size: int,
        player_gender: str = DEFAULT_PLAYER_GENDER,
    ) -> dict[str, object]:
        self._ensure_database()
        normalized_kind = self._normalize_avatar_kind(kind)
        normalized_language = self._normalize_language_code(lang_code)
        normalized_source_lang = self._normalize_language_code(source_lang or DEFAULT_SOURCE_LANGUAGE)
        normalized_keyword = self._normalize_keyword(keyword)
        normalized_player_gender = self._normalize_player_gender(player_gender)
        page, size = self._normalize_page(page, size)

        with self._connect() as connection:
            resolver = TextMapCache(connection)
            entries = self._collect_avatar_entries(
                connection,
                resolver,
                kind=normalized_kind,
                lang_code=normalized_language,
                source_lang=normalized_source_lang,
                avatar_keyword="",
                keyword=normalized_keyword,
                created_version=created_version,
                updated_version=updated_version,
                player_gender=normalized_player_gender,
                include_translations=False,
            )

        total = len(entries)
        start = (page - 1) * size
        sliced_entries = entries[start:start + size]
        results = [
            {
                "entityType": normalized_kind,
                "entityKey": entry["entryKey"],
                "avatarId": entry["avatarId"],
                "avatarName": entry["avatarName"],
                "title": entry["title"],
                "preview": entry["preview"],
                "createdVersion": entry["createdVersion"],
                "updatedVersion": entry["updatedVersion"],
                "detailQuery": entry["detailQuery"],
            }
            for entry in sliced_entries
        ]
        return {
            "keyword": keyword,
            "lang": normalized_language,
            "sourceLang": normalized_source_lang,
            "entityType": normalized_kind,
            "page": page,
            "size": size,
            "total": total,
            "results": results,
            "playerGender": normalized_player_gender,
        }

    def _collect_avatar_entries(
        self,
        connection: sqlite3.Connection,
        resolver: TextMapCache,
        *,
        kind: str,
        lang_code: str,
        source_lang: str,
        avatar_keyword: str,
        keyword: str,
        created_version: str | None,
        updated_version: str | None,
        player_gender: str,
        include_translations: bool,
        result_langs: list[str] | None = None,
        player_name: str | None = None,
        avatar_id: int | None = None,
    ) -> list[dict[str, object]]:
        normalized_kind = self._normalize_avatar_kind(kind)
        normalized_player_name = self._normalize_player_name(player_name)
        created_version_id = self._resolve_version_filter_id(connection, created_version)
        updated_version_id = self._resolve_version_filter_id(connection, updated_version)

        params: list[Any] = []
        if normalized_kind == "voice":
            sql = """
                SELECT ve.entry_key, ve.avatar_id, ve.voice_id, ve.sort_id, ve.title_hash, ve.text_hash_m, ve.text_hash_f,
                       ve.voice_path, ve.created_version_id, ve.updated_version_id,
                       cv.version_tag AS created_version_tag, uv.version_tag AS updated_version_tag,
                       COALESCE(cv.version_sort_key, 0) AS created_sort_key,
                       a.name_hash, a.full_name_hash
                FROM voice_entry ve
                LEFT JOIN avatar a ON a.avatar_id = ve.avatar_id
                LEFT JOIN version_dim cv ON cv.id = ve.created_version_id
                LEFT JOIN version_dim uv ON uv.id = ve.updated_version_id
            """
            if avatar_id is not None:
                sql += " WHERE ve.avatar_id=?"
                params.append(int(avatar_id))
            sql += " ORDER BY COALESCE(cv.version_sort_key, 0) ASC, ve.avatar_id ASC, ve.sort_id ASC, ve.voice_id ASC"
        else:
            sql = """
                SELECT se.entry_key, se.avatar_id, se.story_id, se.sort_id, se.title_hash, se.content_hash,
                       se.created_version_id, se.updated_version_id,
                       cv.version_tag AS created_version_tag, uv.version_tag AS updated_version_tag,
                       COALESCE(cv.version_sort_key, 0) AS created_sort_key,
                       a.name_hash, a.full_name_hash
                FROM story_entry se
                LEFT JOIN avatar a ON a.avatar_id = se.avatar_id
                LEFT JOIN version_dim cv ON cv.id = se.created_version_id
                LEFT JOIN version_dim uv ON uv.id = se.updated_version_id
            """
            if avatar_id is not None:
                sql += " WHERE se.avatar_id=?"
                params.append(int(avatar_id))
            sql += " ORDER BY COALESCE(cv.version_sort_key, 0) ASC, se.avatar_id ASC, se.sort_id ASC, se.story_id ASC"

        rows = connection.execute(sql, params).fetchall()
        entries: list[dict[str, object]] = []

        for row in rows:
            if created_version_id is not None and int(row["created_version_id"] or 0) != created_version_id:
                continue
            if updated_version_id is not None and int(row["updated_version_id"] or 0) != updated_version_id:
                continue

            avatar_display_name = self._resolve_avatar_name(
                resolver,
                row["name_hash"],
                row["full_name_hash"],
                source_lang,
                player_name=normalized_player_name,
                player_gender=player_gender,
            )
            avatar_search_name = self._resolve_avatar_name(
                resolver,
                row["name_hash"],
                row["full_name_hash"],
                lang_code,
                player_name=normalized_player_name,
                player_gender=player_gender,
            )
            if avatar_keyword and not self._matches_text(avatar_search_name, avatar_keyword):
                continue

            if normalized_kind == "voice":
                title_display = resolver.get_normalized_text(
                    row["title_hash"],
                    source_lang,
                    prefer_main=True,
                    player_name=normalized_player_name,
                    player_gender=player_gender,
                ) or f"角色语音 {row['voice_id']}"
                title_search = resolver.get_normalized_text(
                    row["title_hash"],
                    lang_code,
                    prefer_main=True,
                    player_name=normalized_player_name,
                    player_gender=player_gender,
                )
                content_hash = row["text_hash_f"] if player_gender == "female" and row["text_hash_f"] else row["text_hash_m"] or row["text_hash_f"]
                content_search = resolver.get_normalized_text(
                    content_hash,
                    lang_code,
                    player_name=normalized_player_name,
                    player_gender=player_gender,
                )
                if keyword and not (
                    self._matches_text(title_search, keyword)
                    or self._matches_text(content_search, keyword)
                    or self._matches_text(avatar_search_name, keyword)
                ):
                    continue
                entry = {
                    "kind": "voice",
                    "entryKey": str(row["entry_key"]),
                    "avatarId": int(row["avatar_id"]),
                    "avatarName": avatar_display_name,
                    "title": title_display,
                    "preview": summarize_text(content_search),
                    "createdVersion": str(row["created_version_tag"] or ""),
                    "updatedVersion": str(row["updated_version_tag"] or ""),
                    "createdSortKey": int(row["created_sort_key"] or 0),
                    "detailQuery": {"kind": "voice", "entryKey": str(row["entry_key"])},
                    "voicePath": str(row["voice_path"] or ""),
                    "voiceId": int(row["voice_id"]),
                }
                if include_translations:
                    entry["translates"] = self._resolve_translations(
                        resolver,
                        content_hash,
                        result_langs or [source_lang],
                        player_name=normalized_player_name,
                        player_gender=player_gender,
                    )
                entries.append(entry)
                continue

            raw_title = resolver.get_normalized_text(
                row["title_hash"],
                source_lang,
                prefer_main=True,
                player_name=normalized_player_name,
                player_gender=player_gender,
            )
            story_content_display = resolver.get_normalized_text(
                row["content_hash"],
                source_lang,
                player_name=normalized_player_name,
                player_gender=player_gender,
            )
            title_display = self._resolve_story_display_title(raw_title, avatar_display_name, story_content_display)
            title_search = resolver.get_normalized_text(
                row["title_hash"],
                lang_code,
                prefer_main=True,
                player_name=normalized_player_name,
                player_gender=player_gender,
            )
            story_content_search = resolver.get_normalized_text(
                row["content_hash"],
                lang_code,
                player_name=normalized_player_name,
                player_gender=player_gender,
            )
            if keyword and not (
                self._matches_text(title_search, keyword)
                or self._matches_text(story_content_search, keyword)
                or self._matches_text(avatar_search_name, keyword)
            ):
                continue
            entry = {
                "kind": "story",
                "entryKey": str(row["entry_key"]),
                "avatarId": int(row["avatar_id"]),
                "avatarName": avatar_display_name,
                "title": title_display,
                "preview": summarize_text(story_content_search),
                "createdVersion": str(row["created_version_tag"] or ""),
                "updatedVersion": str(row["updated_version_tag"] or ""),
                "createdSortKey": int(row["created_sort_key"] or 0),
                "detailQuery": {"kind": "story", "entryKey": str(row["entry_key"])},
                "storyId": int(row["story_id"]),
            }
            if include_translations:
                entry["translates"] = self._resolve_translations(
                    resolver,
                    row["content_hash"],
                    result_langs or [source_lang],
                    player_name=normalized_player_name,
                    player_gender=player_gender,
                )
            entries.append(entry)

        return entries

    def _resolve_avatar_name(
        self,
        resolver: TextMapCache,
        name_hash: str | None,
        full_name_hash: str | None,
        lang_code: str,
        *,
        player_name: str,
        player_gender: str,
    ) -> str:
        return (
            resolver.get_normalized_text(
                name_hash,
                lang_code,
                prefer_main=True,
                player_name=player_name,
                player_gender=player_gender,
            )
            or resolver.get_normalized_text(
                full_name_hash,
                lang_code,
                prefer_main=True,
                player_name=player_name,
                player_gender=player_gender,
            )
            or ""
        )

    def _resolve_story_display_title(self, title: str, avatar_name: str, content: str) -> str:
        normalized_title = str(title or "").strip()
        if normalized_title and normalized_title.lower() not in PLACEHOLDER_STORY_TITLES:
            return normalized_title
        summary = summarize_text(content, limit=28).strip()
        if summary:
            if avatar_name:
                return f"{avatar_name} · {summary}"
            return summary
        if avatar_name:
            return f"{avatar_name} 故事"
        return "角色故事"

    def _matches_text(self, value: str | None, keyword: str) -> bool:
        if not keyword:
            return True
        normalized_value = normalize_text_for_search(value or "").lower()
        normalized_keyword = normalize_text_for_search(keyword).lower()
        return bool(normalized_keyword) and normalized_keyword in normalized_value

    def _normalize_avatar_kind(self, kind: str) -> str:
        normalized = str(kind or "").strip().lower()
        if normalized not in {"voice", "story"}:
            raise InvalidQueryError(f"不支持的角色条目类型：{normalized or kind}")
        return normalized

    def _build_search_cache_key(self, **kwargs: object) -> tuple[Any, ...]:
        db_mtime = self.db_path.stat().st_mtime_ns if self.db_path.exists() else 0
        items = tuple(sorted((key, tuple(value) if isinstance(value, list) else value) for key, value in kwargs.items()))
        return (db_mtime, *items)

    def _get_cached_search_payload(self, cache_key: tuple[Any, ...]) -> dict[str, object] | None:
        with self._cache_lock:
            return self._search_cache.get(cache_key)

    def _set_cached_search_payload(self, cache_key: tuple[Any, ...], payload: dict[str, object]) -> None:
        with self._cache_lock:
            self._search_cache[cache_key] = payload
            while len(self._search_cache) > SEARCH_CACHE_LIMIT:
                self._search_cache.pop(next(iter(self._search_cache)))

    def _build_text_map_match_query(self, keyword: str, lang_code: str) -> str:
        normalized = normalize_text_for_search(keyword)
        tokens = [token for token in normalized.split(" ") if token]
        if not tokens:
            return 'lang_scope:"normal%s"' % lang_code
        escaped_tokens = [token.replace('"', '""') for token in tokens]
        search_terms = " AND ".join(f'search_content:"{token}"' for token in escaped_tokens)
        return f'lang_scope:"normal{lang_code}" AND {search_terms}'

    def _build_fts_query(self, keyword: str) -> str:
        normalized = normalize_text_for_search(keyword)
        tokens = [token for token in normalized.split(" ") if token]
        if not tokens:
            return '""'
        return " ".join(f'"{token.replace("\"", "\"\"")}"' for token in tokens)

    def _normalize_keyword(self, keyword: str) -> str:
        return " ".join(str(keyword or "").strip().split())

    def _normalize_language_code(self, lang_code: str) -> str:
        normalized = str(lang_code or "").strip().lower()
        if not normalized:
            raise InvalidLanguageError("请选择有效的语言。")
        if normalized not in LANGUAGE_LABELS:
            raise InvalidLanguageError(f"不支持的语言代码：{normalized}")
        return normalized

    def _normalize_player_name(self, player_name: str | None) -> str:
        normalized = str(player_name or "").strip()
        return normalized or DEFAULT_PLAYER_NAME

    def _normalize_player_gender(self, player_gender: str) -> str:
        normalized = str(player_gender or "").strip().lower()
        if normalized not in VALID_PLAYER_GENDERS:
            raise InvalidPlayerGenderError("玩家性别必须是 male、female 或 both。")
        return normalized

    def _normalize_page(self, page: int, size: int) -> tuple[int, int]:
        if page < 1:
            raise InvalidQueryError("页码必须大于等于 1。")
        if size < 1:
            raise InvalidQueryError("每页数量必须大于等于 1。")
        return page, min(size, MAX_PAGE_SIZE)

    def _resolve_result_languages(self, result_langs: list[str], search_lang: str) -> list[str]:
        seen = set()
        resolved = []
        for code in [search_lang, *result_langs]:
            normalized = self._normalize_language_code(code)
            if normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(normalized)
        return resolved or [search_lang]

    def _normalize_source_type(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in SOURCE_TYPE_PRIORITY:
            raise InvalidQueryError(f"不支持的来源类型：{normalized}")
        return normalized

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_database(self) -> None:
        if self.db_path.is_file():
            return
        with self._build_lock:
            if self.db_path.is_file():
                return
            builder = StarrailDatabaseBuilder(self.db_path)
            builder.build_database(verbose=False)
