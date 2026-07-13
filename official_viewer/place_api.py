"""Documented Baidu Place API client with no crawler behavior or retries."""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass
from typing import Any

import requests

from .config import ViewerSettings
from .quota import DailyUsageLedger

PLACE_SEARCH_URL = "https://api.map.baidu.com/place/v2/search"
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_CITY_SEPARATORS = frozenset({",", "，", ";", "；", "、"})


class InputValidationError(ValueError):
    """Raised when an interactive search request is outside the UI contract."""


class OfficialApiError(RuntimeError):
    """Raised for an official API response without exposing request credentials."""


class OfficialApiUnavailable(OfficialApiError):
    """Raised when an official request cannot complete safely."""


_STATUS_MESSAGES = {
    1: "官方地点服务暂不可用，请稍后手动重试。",
    2: "官方地点服务拒绝了请求参数，请检查城市和关键词。",
    3: "官方地点服务暂不可用，请稍后手动重试。",
    203: "AK 应用类型不匹配；地点检索需要 Server 类型 AK。",
    210: "Server AK 的 IP 白名单未匹配当前公网出口 IP。",
    220: "Browser AK 的 Referer 白名单未匹配当前页面来源。",
    230: "AK 配额不足或调用受限，请在百度地图开放平台控制台确认。",
    240: "所需百度地图服务未开通或 AK 没有相应权限。",
    302: "百度地图服务配额已用尽，请在官方控制台确认额度。",
    401: "百度地图服务并发受限；本程序已串行发送请求，请稍后手动重试。",
}


@dataclass(frozen=True)
class PlaceSearchPage:
    city: str
    query: str
    page: int
    total: int | None
    results: tuple[dict[str, object], ...]
    has_next: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "city": self.city,
            "query": self.query,
            "page": self.page,
            "total": self.total,
            "results": list(self.results),
            "has_next": self.has_next,
        }


def _clean_text(value: object, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise InputValidationError(f"{field_name} 必须是文本。")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum or _CONTROL_CHARACTER.search(cleaned):
        raise InputValidationError(f"{field_name} 格式无效。")
    return cleaned


def validate_search_input(
    city: object,
    query: object,
    page: object,
    *,
    max_pages: int,
) -> tuple[str, str, int]:
    """Validate one explicit city/keyword/page interaction."""

    cleaned_city = _clean_text(city, "城市", 50)
    cleaned_query = _clean_text(query, "关键词", 80)
    if any(
        character in _CITY_SEPARATORS or character.isspace()
        for character in cleaned_city
    ):
        raise InputValidationError("一次只能查询一个城市。")
    if isinstance(page, bool) or not isinstance(page, int):
        raise InputValidationError("页码格式无效。")
    if not 0 <= page < max_pages:
        raise InputValidationError("页码超出本次查询允许范围。")
    return cleaned_city, cleaned_query, page


def _safe_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().replace("\x00", "")[:maximum]


def _safe_location(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        latitude = float(value["lat"])
        longitude = float(value["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(number) for number in (latitude, longitude)):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return {"lat": latitude, "lng": longitude}


def _sanitize_place(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    uid = _safe_text(raw.get("uid"), 128)
    name = _safe_text(raw.get("name"), 160)
    location = _safe_location(raw.get("location"))
    if not uid or not name or location is None:
        return None
    return {
        "uid": uid,
        "name": name,
        "address": _safe_text(raw.get("address"), 240),
        "location": location,
    }


def _status_message(status: object) -> str:
    if isinstance(status, bool):
        return "官方地点服务返回了无法识别的状态。"
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "官方地点服务返回了无法识别的状态。"
    return _STATUS_MESSAGES.get(code, f"官方地点服务返回状态 {code}，请查阅官方文档。")


class OfficialPlaceClient:
    """One-request-at-a-time client for documented Place Search v2 requests."""

    def __init__(
        self,
        settings: ViewerSettings,
        ledger: DailyUsageLedger,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self._settings = settings
        self._ledger = ledger
        self._session = session or requests.Session()
        self._session.trust_env = False
        self._request_lock = threading.Lock()

    def close(self) -> None:
        self._session.close()

    def search(self, city: object, query: object, page: object) -> PlaceSearchPage:
        city_text, query_text, page_number = validate_search_input(
            city,
            query,
            page,
            max_pages=self._settings.max_pages_per_query,
        )
        if not self._settings.server_ak:
            raise OfficialApiUnavailable("Server AK 未配置，无法调用官方地点检索。")

        params = {
            "query": query_text,
            "region": city_text,
            "city_limit": "true",
            "output": "json",
            "scope": "1",
            "page_size": self._settings.page_size,
            "page_num": page_number,
            "ak": self._settings.server_ak,
        }
        # A single local process can serve multiple tabs. Serializing here avoids
        # self-inflicted API concurrency bursts and intentionally performs no retry.
        with self._request_lock:
            self._ledger.reserve("place")
            try:
                response = self._session.get(
                    PLACE_SEARCH_URL,
                    params=params,
                    timeout=self._settings.request_timeout_seconds,
                )
            except requests.RequestException as exc:
                raise OfficialApiUnavailable(
                    "官方地点服务暂不可用，请稍后手动重试。"
                ) from exc

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise OfficialApiUnavailable(
                "官方地点服务返回了无法识别的响应，请稍后手动重试。"
            ) from exc
        if not isinstance(payload, dict):
            raise OfficialApiUnavailable(
                "官方地点服务返回了无法识别的响应，请稍后手动重试。"
            )

        status = payload.get("status")
        if status != 0:
            raise OfficialApiError(_status_message(status))
        if not response.ok:
            raise OfficialApiUnavailable("官方地点服务暂不可用，请稍后手动重试。")

        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raw_results = []
        results = tuple(
            place
            for item in raw_results
            if (place := _sanitize_place(item)) is not None
        )
        total_value = payload.get("total")
        total = (
            total_value
            if isinstance(total_value, int)
            and not isinstance(total_value, bool)
            and total_value >= 0
            else None
        )
        has_next = page_number + 1 < self._settings.max_pages_per_query and (
            (total is not None and total > (page_number + 1) * self._settings.page_size)
            or len(results) == self._settings.page_size
        )
        return PlaceSearchPage(
            city=city_text,
            query=query_text,
            page=page_number,
            total=total,
            results=results,
            has_next=has_next,
        )
