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

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    def _handle_api_request(self, parsed_url) -> None:
        try:
            if parsed_url.path == "/api/meta":
                self._write_json(HTTPStatus.OK, self.service.get_meta())
                return

            if parsed_url.path == "/api/search":
                params = parse_qs(parsed_url.query)
                payload = self.service.search(
                    keyword=_get_first_param(params, "keyword", ""),
                    lang_code=_get_first_param(params, "lang", DEFAULT_LANGUAGE),
                    page=_parse_int_param(params, "page", 1),
                    size=_parse_int_param(params, "size", DEFAULT_PAGE_SIZE),
                    result_langs=_get_list_param(params, "resultLangs"),
                    player_name=_get_first_param(params, "playerName", DEFAULT_PLAYER_NAME),
                    player_gender=_get_first_param(params, "playerGender", DEFAULT_PLAYER_GENDER),
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
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def _get_first_param(params: dict, key: str, default: str) -> str:
    return params.get(key, [default])[0]


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
        maybe_open_browser("http://127.0.0.1:5000/")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down StarrailTextSearch server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
