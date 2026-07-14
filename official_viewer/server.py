"""Loopback-only HTTP server for interactive official API viewing."""

from __future__ import annotations

import argparse
import json
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import (
    ConfigurationError,
    ViewerSettings,
    load_settings,
    public_configuration,
)
from .place_api import (
    InputValidationError,
    OfficialApiError,
    OfficialApiUnavailable,
    OfficialPlaceClient,
)
from .quota import (
    DailyQuotaExceeded,
    DailyUsageLedger,
    QuotaError,
    RuntimeLock,
    RuntimeLockError,
    UsageLedgerError,
)

STATIC_DIRECTORY = Path(__file__).with_name("static")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_UID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_JSON_BYTES = 4 * 1024


class LocalViewerServer(ThreadingHTTPServer):
    """Threaded server that is deliberately bound to loopback only."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], context: "ViewerContext") -> None:
        self.context = context
        super().__init__(address, ViewerRequestHandler)

    def server_close(self) -> None:
        try:
            self.context.place_client.close()
        finally:
            try:
                super().server_close()
            finally:
                self.context.runtime_lock.release()


class ViewerContext:
    """Dependencies shared by local HTTP handlers."""

    def __init__(
        self,
        settings: ViewerSettings,
        ledger: DailyUsageLedger,
        place_client: OfficialPlaceClient,
        runtime_lock: RuntimeLock,
    ) -> None:
        self.settings = settings
        self.ledger = ledger
        self.place_client = place_client
        self.runtime_lock = runtime_lock

    def health(self) -> dict[str, object]:
        return {
            "service": "baidu-official-poi-panorama-viewer",
            "place_search_configured": self.settings.place_search_configured,
            "panorama_configured": self.settings.panorama_configured,
            "page_size": self.settings.page_size,
            "max_pages_per_query": self.settings.max_pages_per_query,
            "max_results_per_query": self.settings.max_results_per_query,
            "usage": self.ledger.snapshot(),
        }


def create_server(
    settings: ViewerSettings,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    usage_path: Path | None = None,
    session: Any | None = None,
) -> LocalViewerServer:
    """Create a local server; public network binding is intentionally unsupported."""

    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("The viewer only supports loopback binding.")
    state_path = usage_path or settings.usage_dir / "usage.json"
    runtime_lock = RuntimeLock(settings.usage_dir / "viewer.lock")
    runtime_lock.acquire()
    client: OfficialPlaceClient | None = None
    try:
        ledger = DailyUsageLedger(
            state_path,
            place_limit=settings.daily_place_limit,
            panorama_limit=settings.daily_panorama_limit,
        )
        client = OfficialPlaceClient(settings, ledger, session=session)
        context = ViewerContext(settings, ledger, client, runtime_lock)
        return LocalViewerServer((host, port), context)
    except Exception:
        if client is not None:
            client.close()
        runtime_lock.release()
        raise


class ViewerRequestHandler(BaseHTTPRequestHandler):
    """Serve a fixed local UI and a very small same-origin JSON API."""

    protocol_version = "HTTP/1.1"

    def version_string(self) -> str:
        return "OfficialPOIViewer/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        """Avoid request logging that could retain user search terms locally."""

    @property
    def context(self) -> ViewerContext:
        return self.server.context  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        if not self._is_allowed_local_request():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "仅允许本机回环访问。"})
            return
        try:
            path = urlsplit(self.path).path
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "请求路径无效。"})
            return
        if path == "/api/health":
            self._run_endpoint(self._send_health)
            return
        if path == "/api/config":
            self._send_json(HTTPStatus.OK, public_configuration(self.context.settings))
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        if not self._is_allowed_local_request() or not self._is_allowed_origin():
            self._discard_rejected_body()
            self._send_json(
                HTTPStatus.FORBIDDEN, {"error": "请求来源未获本地服务允许。"}
            )
            return
        try:
            path = urlsplit(self.path).path
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "请求路径无效。"})
            return
        if path == "/api/search":
            self._run_endpoint(self._search)
            return
        if path == "/api/panorama-permit":
            self._run_endpoint(self._reserve_panorama)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在。"})

    def do_OPTIONS(self) -> None:
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "不支持跨域调用。"})

    def _send_health(self) -> None:
        self._send_json(HTTPStatus.OK, self.context.health())

    def _search(self) -> None:
        payload = self._read_json_body()
        result = self.context.place_client.search(
            payload.get("city"),
            payload.get("query"),
            payload.get("page", 0),
        )
        response = result.as_dict()
        response["usage"] = self.context.ledger.snapshot()
        self._send_json(HTTPStatus.OK, response)

    def _reserve_panorama(self) -> None:
        if not self.context.settings.panorama_configured:
            raise OfficialApiUnavailable("Browser AK 未配置，无法展示官方全景。")
        payload = self._read_json_body()
        uid = payload.get("uid")
        if not isinstance(uid, str) or not _UID_PATTERN.fullmatch(uid):
            raise InputValidationError("地点标识格式无效。")
        usage = self.context.ledger.reserve("panorama")
        self._send_json(HTTPStatus.OK, {"allowed": True, "usage": usage})

    def _read_json_body(self) -> dict[str, object]:
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise InputValidationError("请求必须使用 application/json。")
        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length) if raw_length is not None else -1
        except ValueError as exc:
            raise InputValidationError("请求长度无效。") from exc
        if not 0 <= content_length <= _MAX_JSON_BYTES:
            self.close_connection = True
            raise InputValidationError("请求内容过大或长度无效。")
        try:
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InputValidationError("请求 JSON 无效。") from exc
        if not isinstance(payload, dict):
            raise InputValidationError("请求 JSON 必须是对象。")
        return payload

    def _discard_rejected_body(self) -> None:
        """Drain only a bounded rejected body before returning a local 403."""

        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            content_length = -1
        if not 0 <= content_length <= _MAX_JSON_BYTES:
            self.close_connection = True
            return
        try:
            self.rfile.read(content_length)
        except OSError:
            self.close_connection = True

    def _run_endpoint(self, endpoint: Any) -> None:
        try:
            endpoint()
        except InputValidationError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except DailyQuotaExceeded as exc:
            self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)})
        except UsageLedgerError as exc:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except OfficialApiUnavailable as exc:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except OfficialApiError as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except QuotaError:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "本地用量保护暂不可用，未发送请求。"},
            )
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "本地服务发生未预期错误。"},
            )

    def _is_allowed_local_request(self) -> bool:
        peer = self.client_address[0]
        if peer not in {"127.0.0.1", "::1"}:
            return False
        return self._is_allowed_host(self.headers.get("Host", ""))

    @staticmethod
    def _is_allowed_host(host_header: str) -> bool:
        return ViewerRequestHandler._local_authority(host_header) is not None

    def _is_allowed_origin(self) -> bool:
        origin_authority = self._local_authority(
            self.headers.get("Origin", ""), require_http_scheme=True
        )
        request_authority = self._local_authority(self.headers.get("Host", ""))
        return (
            origin_authority is not None
            and request_authority is not None
            and origin_authority == request_authority
        )

    @staticmethod
    def _local_authority(
        value: str, *, require_http_scheme: bool = False
    ) -> tuple[str, int] | None:
        """Return a normalized loopback host/port pair or reject the authority."""

        try:
            parsed = urlsplit(value if require_http_scheme else f"//{value}")
        except ValueError:
            return None
        if require_http_scheme:
            if (
                parsed.scheme != "http"
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                return None
        elif parsed.scheme or parsed.path or parsed.query or parsed.fragment:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        host = (parsed.hostname or "").rstrip(".").lower()
        if host not in LOCAL_HOSTS:
            return None
        try:
            port = parsed.port or 80
        except ValueError:
            return None
        if not 1 <= port <= 65535:
            return None
        return host, port

    def _serve_static(self, path: str) -> None:
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/assets/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/assets/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        asset = assets.get(path)
        if asset is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "资源不存在。"})
            return
        filename, content_type = asset
        try:
            content = (STATIC_DIRECTORY / filename).read_bytes()
        except OSError:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "本地界面资源不可用。"}
            )
            return
        self._send_bytes(HTTPStatus.OK, content_type, content)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _send_bytes(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self._send_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Permissions-Policy", "geolocation=(), camera=(), microphone=()"
        )
        self.send_header(
            "Content-Security-Policy",
            # Baidu's official JSAPI dynamically compiles its loaded modules.
            "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' https: 'unsafe-eval'; connect-src 'self' https:; font-src 'self' data:",
        )


def _port(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Loopback-only viewer using documented Baidu Map APIs."
    )
    parser.add_argument("--port", type=_port, default=8765, help="local TCP port")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser tab"
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="print safe configuration status and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2

    if args.check_config:
        print(
            f"Server AK configured: {'yes' if settings.place_search_configured else 'no'}"
        )
        print(
            f"Browser AK configured: {'yes' if settings.panorama_configured else 'no'}"
        )
        print(f"Place daily budget: {settings.daily_place_limit}")
        print(f"Panorama daily budget: {settings.daily_panorama_limit}")
        return (
            0
            if settings.place_search_configured and settings.panorama_configured
            else 2
        )

    try:
        server = create_server(settings, port=args.port)
    except RuntimeLockError as exc:
        print(f"Unable to start local viewer: {exc}")
        return 2
    except OSError as exc:
        if args.port != 8765:
            print(f"Unable to start local viewer: {exc}")
            return 2
        try:
            server = create_server(settings, port=0)
        except (OSError, RuntimeLockError) as fallback_error:
            print(f"Unable to start local viewer: {fallback_error}")
            return 2
        print("Port 8765 is unavailable; selected a different local port.")

    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"Official POI panorama viewer: {url}")
    print("Loopback-only. Server AK is never sent to the browser.")
    if not settings.place_search_configured or not settings.panorama_configured:
        print("Configuration is incomplete. See README.md and .env.example.")
    if not args.no_browser:
        threading.Thread(
            target=webbrowser.open_new_tab, args=(url,), daemon=True
        ).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLocal viewer stopped.")
    finally:
        server.shutdown()
        server.server_close()
    return 0
