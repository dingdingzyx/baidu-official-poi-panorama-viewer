from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import requests

from official_viewer.config import ViewerSettings
from official_viewer.place_api import (
    PLACE_SEARCH_URL,
    InputValidationError,
    OfficialApiError,
    OfficialApiUnavailable,
    OfficialPlaceClient,
)
from official_viewer.quota import DailyUsageLedger


class FakeResponse:
    def __init__(self, payload: object, *, ok: bool = True) -> None:
        self._payload = payload
        self.ok = ok

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.trust_env = True
        self.closed = False

    def get(self, url: str, *, params: dict[str, object], timeout: float) -> object:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    def close(self) -> None:
        self.closed = True


class OfficialPlaceClientTests(unittest.TestCase):
    def make_client(
        self, root: Path, response: object
    ) -> tuple[OfficialPlaceClient, FakeSession]:
        settings = ViewerSettings(
            server_ak="server-secret",
            browser_ak="browser-public",
            usage_dir=root,
            daily_place_limit=10,
            daily_panorama_limit=5,
        )
        ledger = DailyUsageLedger(root / "usage.json", place_limit=10, panorama_limit=5)
        session = FakeSession(response)
        return OfficialPlaceClient(settings, ledger, session=session), session

    def test_uses_documented_parameters_once_and_sanitizes_result(self) -> None:
        payload = {
            "status": 0,
            "total": 21,
            "results": [
                {
                    "uid": "uid-1",
                    "name": "示例酒店",
                    "address": "示例路 1 号",
                    "location": {"lat": 43.1, "lng": 124.3},
                    "unexpected": "discarded",
                },
                {"uid": "broken", "name": "bad", "location": {}},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            client, session = self.make_client(Path(temporary), FakeResponse(payload))
            page = client.search("四平", "酒店", 0)

        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["url"], PLACE_SEARCH_URL)
        self.assertEqual(
            call["params"],
            {
                "query": "酒店",
                "region": "四平",
                "city_limit": "true",
                "output": "json",
                "scope": "1",
                "page_size": 20,
                "page_num": 0,
                "ak": "server-secret",
            },
        )
        self.assertFalse(session.trust_env)
        self.assertEqual(page.total, 21)
        self.assertEqual(len(page.results), 1)
        self.assertNotIn("unexpected", page.results[0])
        self.assertTrue(page.has_next)

    def test_invalid_input_does_not_call_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client, session = self.make_client(
                Path(temporary), FakeResponse({"status": 0, "results": []})
            )
            with self.assertRaises(InputValidationError):
                client.search("", "酒店", 0)
        self.assertEqual(session.calls, [])

    def test_query_length_matches_official_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client, session = self.make_client(
                Path(temporary), FakeResponse({"status": 0, "results": []})
            )
            client.search("四平", "酒" * 45, 0)
            with self.assertRaises(InputValidationError):
                client.search("四平", "酒" * 46, 0)
        self.assertEqual(len(session.calls), 1)

    def test_page_limit_matches_official_four_hundred_result_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client, session = self.make_client(
                Path(temporary), FakeResponse({"status": 0, "results": []})
            )
            client.search("四平", "酒店", 19)
            with self.assertRaises(InputValidationError):
                client.search("四平", "酒店", 20)
        self.assertEqual(len(session.calls), 1)

    def test_multiple_city_input_is_rejected_without_a_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client, session = self.make_client(
                Path(temporary), FakeResponse({"status": 0, "results": []})
            )
            with self.assertRaisesRegex(InputValidationError, "一个城市"):
                client.search("四平,福州", "酒店", 0)
        self.assertEqual(session.calls, [])

    def test_network_failure_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client, session = self.make_client(Path(temporary), requests.Timeout())
            with self.assertRaises(OfficialApiUnavailable):
                client.search("四平", "酒店", 0)
        self.assertEqual(len(session.calls), 1)

    def test_official_status_is_mapped_without_response_body(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client, _ = self.make_client(Path(temporary), FakeResponse({"status": 210}))
            with self.assertRaisesRegex(OfficialApiError, "IP 白名单"):
                client.search("四平", "酒店", 0)

    def test_official_statuses_return_actionable_messages(self) -> None:
        cases = {
            4: "配额",
            5: "Server AK",
            8: "关键词",
            9: "权限",
            200: "应用",
            201: "停用",
            211: "SN 校验",
            240: "未开通",
            401: "并发",
        }
        for status, expected in cases.items():
            with (
                self.subTest(status=status),
                tempfile.TemporaryDirectory() as temporary,
            ):
                client, _ = self.make_client(
                    Path(temporary), FakeResponse({"status": status})
                )
                with self.assertRaisesRegex(OfficialApiError, expected):
                    client.search("四平", "酒店", 0)

    def test_non_list_results_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client, _ = self.make_client(
                Path(temporary), FakeResponse({"status": 0, "results": None})
            )
            page = client.search("四平", "酒店", 0)
        self.assertEqual(page.results, ())

    def test_full_raw_page_keeps_next_page_when_invalid_items_are_filtered(
        self,
    ) -> None:
        payload = {"status": 0, "results": [{"invalid": index} for index in range(20)]}
        with tempfile.TemporaryDirectory() as temporary:
            client, _ = self.make_client(Path(temporary), FakeResponse(payload))
            page = client.search("四平", "酒店", 0)
        self.assertEqual(page.results, ())
        self.assertTrue(page.has_next)
