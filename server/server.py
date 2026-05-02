from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from browser_session import (
    disconnect_browser_client,
    is_browser_auto_shutdown_enabled,
    start_browser_session_watchdog,
    touch_browser_client,
)
from textmap_service import (
    DEFAULT_LANGUAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_PLAYER_GENDER,
    DEFAULT_PLAYER_NAME,
    TextMapService,
    TextMapServiceError,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIST_DIR = PROJECT_ROOT / "webui" / "dist"
FALLBACK_TEMPLATE = PROJECT_ROOT / "server" / "templates" / "build_required.html"
DATA_ROOT = (PROJECT_ROOT.parent / "turnbasedgamedata").resolve()


class StarrailRequestHandler(BaseHTTPRequestHandler):
    server_version = "StarrailTextSearch/0.1"

    def __init__(self, *args, service: TextMapService, **kwargs):
        self.service = service
        super().__init__(*args, **kwargs)

    def do_OPTIONS(self) -> None:
        if self.path.startswith("/api/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_api_headers("application/json; charset=utf-8")
            self.end_headers()
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        if parsed_url.path.startswith("/api/"):
            self._handle_api_request(parsed_url)
            return
        self._serve_frontend(parsed_url.path)

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        if parsed_url.path in {
            "/api/browser-session/heartbeat",
            "/api/browser-session/disconnect",
        }:
            self._handle_browser_session_request(parsed_url.path)
            return

        if parsed_url.path.startswith("/api/"):
            self._write_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": f"接口不支持 POST：{parsed_url.path}"},
            )
            return

        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    def _handle_api_request(self, parsed_url) -> None:
        try:
            params = parse_qs(parsed_url.query)
            source_lang = _get_first_param(params, "sourceLang", DEFAULT_LANGUAGE)
            result_langs = _get_list_param(params, "resultLangs")
            player_name = _get_first_param(params, "playerName", DEFAULT_PLAYER_NAME)
            player_gender = _get_first_param(params, "playerGender", DEFAULT_PLAYER_GENDER)

            if parsed_url.path == "/api/startupStatus":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "data": {
                            "browserAutoShutdownEnabled": is_browser_auto_shutdown_enabled(),
                        },
                        "code": 200,
                        "msg": "ok",
                    },
                )
                return

            if parsed_url.path == "/api/meta":
                self._write_json(HTTPStatus.OK, self.service.get_meta(source_lang=source_lang))
                return

            if parsed_url.path == "/api/version":
                self._write_json(HTTPStatus.OK, self.service.get_versions())
                return

            if parsed_url.path == "/api/search":
                payload = self.service.search(
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", DEFAULT_PAGE_SIZE),
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    source_types=_get_list_param(params, "sourceTypes"),
                    source_lang=source_lang,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/text/sources":
                payload = self.service.get_text_sources(
                    text_hash=_get_first_param(params, "hash", _get_first_param(params, "textHash", "")),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/mission/search":
                payload = self.service.search_missions(
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    source_lang=source_lang,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", DEFAULT_PAGE_SIZE),
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/mission/detail":
                payload = self.service.get_mission_detail(
                    mission_id=_parse_required_int_param(params, "missionId"),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/book/search":
                payload = self.service.search_books(
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    source_lang=source_lang,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", DEFAULT_PAGE_SIZE),
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/book/detail":
                payload = self.service.get_book_detail(
                    book_id=_parse_required_int_param(params, "bookId"),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/talk/search":
                payload = self.service.search_talks(
                    keyword=_get_first_param(params, "keyword", ""),
                    speaker_keyword=_get_first_param(params, "speakerKeyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    source_lang=source_lang,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", DEFAULT_PAGE_SIZE),
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/talk/detail":
                payload = self.service.get_talk_detail(
                    talk_sentence_id=_parse_required_int_param(params, "talkSentenceId"),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/message/search":
                payload = self.service.search_messages(
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    source_lang=source_lang,
                    camp=_get_optional_param(params, "camp"),
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", 60),
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/message/detail":
                payload = self.service.get_message_detail(
                    thread_id=_parse_required_int_param(params, "threadId"),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/avatar/search":
                payload = self.service.search_avatars(
                    kind=_get_required_param(params, "kind"),
                    avatar_keyword=_get_first_param(params, "avatarKeyword", ""),
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    source_lang=source_lang,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/voice/search":
                payload = self.service.search_voices(
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    source_lang=source_lang,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    player_gender=player_gender,
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", DEFAULT_PAGE_SIZE),
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/voice/by-avatar":
                payload = self.service.get_avatar_entries(
                    kind="voice",
                    avatar_id=_parse_required_int_param(params, "avatarId"),
                    keyword=_get_first_param(params, "keyword", ""),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/voice/detail":
                payload = self.service.get_voice_detail(
                    entry_key=_get_required_param(params, "entryKey"),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/story/search":
                payload = self.service.search_stories(
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    source_lang=source_lang,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", DEFAULT_PAGE_SIZE),
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/story/by-avatar":
                payload = self.service.get_avatar_entries(
                    kind="story",
                    avatar_id=_parse_required_int_param(params, "avatarId"),
                    keyword=_get_first_param(params, "keyword", ""),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    created_version=_get_optional_param(params, "createdVersion"),
                    updated_version=_get_optional_param(params, "updatedVersion"),
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            if parsed_url.path == "/api/story/detail":
                payload = self.service.get_story_detail(
                    entry_key=_get_required_param(params, "entryKey"),
                    source_lang=source_lang,
                    result_langs=result_langs,
                    player_name=player_name,
                    player_gender=player_gender,
                )
                self._write_json(HTTPStatus.OK, payload)
                return

            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"error": f"未知接口：{parsed_url.path}"},
            )
        except TextMapServiceError as error:
            self._write_json(error.status_code, {"error": error.message})
        except ValueError as error:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:  # pragma: no cover - defensive branch
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"服务器内部错误：{error}"},
            )

    def _handle_browser_session_request(self, path: str) -> None:
        try:
            client_id = self._get_browser_client_id()
            if not client_id:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Missing clientId"})
                return

            if path == "/api/browser-session/heartbeat":
                active_clients = touch_browser_client(client_id)
            else:
                active_clients = disconnect_browser_client(client_id)

            self._write_json(
                HTTPStatus.OK,
                {
                    "data": {
                        "activeClients": active_clients,
                        "autoShutdownEnabled": is_browser_auto_shutdown_enabled(),
                    },
                    "code": 200,
                    "msg": "ok",
                },
            )
        except Exception as error:  # pragma: no cover - defensive branch
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"服务器内部错误：{error}"},
            )

    def _get_browser_client_id(self) -> str:
        payload = self._read_post_payload()
        if isinstance(payload, dict):
            client_id = payload.get("clientId", "")
            if isinstance(client_id, str):
                client_id = client_id.strip()
                if client_id:
                    return client_id
        return ""

    def _read_post_payload(self) -> dict:
        raw_length = self.headers.get("Content-Length", "").strip()
        try:
            content_length = int(raw_length) if raw_length else 0
        except ValueError:
            content_length = 0
        if content_length <= 0:
            return {}

        raw_body = self.rfile.read(content_length)
        content_type = self.headers.get("Content-Type", "")
        if "application/x-www-form-urlencoded" in content_type:
            parsed = parse_qs(raw_body.decode("utf-8", errors="replace"))
            return {key: values[0] for key, values in parsed.items() if values}

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _serve_frontend(self, request_path: str) -> None:
        if WEB_DIST_DIR.is_dir():
            target_path = self._resolve_dist_target(request_path)
            if target_path and target_path.is_file():
                self._serve_file(target_path)
                return

            index_path = WEB_DIST_DIR / "index.html"
            if index_path.is_file():
                self._serve_file(index_path)
                return

        self._serve_file(FALLBACK_TEMPLATE, status=HTTPStatus.OK)

    def _resolve_dist_target(self, request_path: str) -> Path | None:
        normalized = request_path.lstrip("/") or "index.html"
        candidate = (WEB_DIST_DIR / normalized).resolve()
        try:
            candidate.relative_to(WEB_DIST_DIR.resolve())
        except ValueError:
            return None
        return candidate

    def _serve_file(self, path: Path, status: int = HTTPStatus.OK) -> None:
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_api_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_api_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def _get_first_param(params: dict, key: str, default: str) -> str:
    return params.get(key, [default])[0]


def _get_optional_param(params: dict, key: str) -> str | None:
    value = _get_first_param(params, key, "").strip()
    return value or None


def _get_required_param(params: dict, key: str) -> str:
    value = _get_first_param(params, key, "").strip()
    if not value:
        raise ValueError(f"缺少必填参数：{key}")
    return value


def _get_list_param(params: dict, key: str) -> list[str]:
    normalized_values: list[str] = []
    for raw_value in params.get(key, []):
        for item in str(raw_value).split(","):
            text = item.strip()
            if text:
                normalized_values.append(text)
    return normalized_values


def _parse_int_param(params: dict, key: str, default: int) -> int:
    raw_value = params.get(key, [default])[0]
    try:
        return int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"参数 {key} 必须是整数。") from error


def _parse_required_int_param(params: dict, key: str) -> int:
    return _parse_int_param(params, key, int(_get_required_param(params, key)))


def maybe_open_browser(url: str) -> None:
    if os.environ.get("STS_NO_BROWSER", "").strip() == "1":
        return

    def _open() -> None:
        time.sleep(1.0)
        try:
            webbrowser.open(url, new=1)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def run() -> None:
    service = TextMapService(DATA_ROOT)
    handler = partial(StarrailRequestHandler, service=service)
    server = ThreadingHTTPServer(("127.0.0.1", 5000), handler)
    try:
        print(f"StarrailTextSearch server running at http://127.0.0.1:5000/")
        print(f"TextMap directory: {DATA_ROOT / 'TextMap'}")
        start_browser_session_watchdog(logger=print, shutdown_callback=server.shutdown)
        maybe_open_browser("http://127.0.0.1:5000/")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down StarrailTextSearch server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
