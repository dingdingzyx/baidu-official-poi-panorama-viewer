from __future__ import annotations

import tempfile
import threading
import unittest
from http.client import HTTPConnection, HTTPResponse
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from official_viewer.config import ViewerSettings
from official_viewer.server import create_server


class FakeResponse:
    ok = True

    def json(self) -> object:
        return {
            "status": 0,
            "total": 1,
            "results": [
                {
                    "uid": "poi-1",
                    "name": "示例地点",
                    "address": "示例地址",
                    "location": {"lat": 43.1, "lng": 124.3},
                }
            ],
        }


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.trust_env = True

    def get(
        self, url: str, *, params: dict[str, object], timeout: float
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    def close(self) -> None:
        return None


class LocalServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.settings = ViewerSettings(
            server_ak="server-secret",
            browser_ak="browser-public",
            usage_dir=root,
            daily_place_limit=10,
            daily_panorama_limit=5,
        )
        self.session = FakeSession()
        self.server = create_server(
            self.settings,
            port=0,
            usage_path=root / "usage.json",
            session=self.session,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.port = port
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.temporary.cleanup()

    def fetch(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        origin: str | None = None,
        host: str | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        headers: dict[str, str] = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        if host is not None:
            headers["Host"] = host
        request = Request(
            self.base_url + path, data=body, method=method, headers=headers
        )
        try:
            response: HTTPResponse = urlopen(request, timeout=3)
            return response.status, dict(response.headers.items()), response.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def test_health_and_client_configuration_never_expose_server_ak(self) -> None:
        status, headers, body = self.fetch("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertIn("OfficialPOIViewer/1.1.0", headers["Server"])
        self.assertIn(b'"max_results_per_query":400', body)
        self.assertNotIn(b"server-secret", body)

        status, _, body = self.fetch("/api/config")
        self.assertEqual(status, 200)
        self.assertIn(b"browser-public", body)
        self.assertNotIn(b"server-secret", body)

    def test_static_entrypoint_is_loopback_ui_with_security_headers(self) -> None:
        status, headers, body = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertIn(
            "script-src 'self' https: 'unsafe-eval'",
            headers["Content-Security-Policy"],
        )
        self.assertIn(
            "style-src 'self' 'unsafe-inline'",
            headers["Content-Security-Policy"],
        )
        self.assertIn(b"Baidu POI Panorama Viewer", body)
        self.assertNotIn(b"server-secret", body)

    def test_search_is_same_origin_and_has_no_download_route(self) -> None:
        body = b'{"city":"\xe5\x9b\x9b\xe5\xb9\xb3","query":"\xe9\x85\x92\xe5\xba\x97","page":0}'
        status, _, response = self.fetch(
            "/api/search", method="POST", body=body, origin=self.base_url
        )
        self.assertEqual(status, 200)
        self.assertIn("示例地点".encode("utf-8"), response)
        self.assertNotIn(b"server-secret", response)
        self.assertEqual(len(self.session.calls), 1)

        status, _, _ = self.fetch("/api/download")
        self.assertEqual(status, 404)

    def test_cross_origin_and_untrusted_host_are_rejected(self) -> None:
        body = b'{"city":"x","query":"y","page":0}'
        status, _, _ = self.fetch(
            "/api/search", method="POST", body=body, origin="http://example.invalid"
        )
        self.assertEqual(status, 403)
        self.assertEqual(self.session.calls, [])

        other_port = self.port + 1 if self.port < 65535 else self.port - 1
        status, _, _ = self.fetch(
            "/api/search",
            method="POST",
            body=body,
            origin=f"http://127.0.0.1:{other_port}",
        )
        self.assertEqual(status, 403)
        self.assertEqual(self.session.calls, [])

        connection = HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request("GET", "/api/health", headers={"Host": "example.invalid"})
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        connection.close()

    def test_panorama_permit_has_no_id_output(self) -> None:
        status, _, body = self.fetch(
            "/api/panorama-permit",
            method="POST",
            body=b'{"uid":"poi-1"}',
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertIn(b'"allowed":true', body)
        self.assertNotIn(b"panoid", body.lower())
