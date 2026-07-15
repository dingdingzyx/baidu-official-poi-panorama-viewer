"""Configuration loading without exposing credentials in logs or responses."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when local configuration is malformed."""


@dataclass(frozen=True)
class ViewerSettings:
    """Runtime settings for the local official API viewer.

    API keys are intentionally excluded from ``repr`` so normal diagnostics cannot
    accidentally disclose them.
    """

    server_ak: str | None = field(repr=False)
    browser_ak: str | None = field(repr=False)
    usage_dir: Path
    daily_place_limit: int = 4500
    daily_panorama_limit: int = 100
    page_size: int = 20
    max_pages_per_query: int = 20
    request_timeout_seconds: float = 10.0

    @property
    def max_results_per_query(self) -> int:
        return self.page_size * self.max_pages_per_query

    @property
    def place_search_configured(self) -> bool:
        return bool(self.server_ak)

    @property
    def panorama_configured(self) -> bool:
        return bool(self.browser_ak)


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read a minimal .env file without evaluating shell syntax or expansions."""

    if not path.exists():
        return {}
    if not path.is_file():
        raise ConfigurationError(f"{path.name} must be a regular file.")

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigurationError(f"Unable to read {path.name}.") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ConfigurationError(f"Invalid .env assignment on line {line_number}.")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            raise ConfigurationError(f"Invalid .env key on line {line_number}.")
        if value[:1] in {"'", '"'}:
            quote = value[0]
            if len(value) < 2 or not value.endswith(quote):
                raise ConfigurationError(
                    f"Unclosed quoted value on line {line_number}."
                )
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def _get_value(name: str, dotenv: dict[str, str]) -> str | None:
    value = os.environ.get(name, dotenv.get(name, "")).strip()
    return value or None


def _positive_int(
    name: str,
    value: str | None,
    default: int,
    *,
    maximum: int,
) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if not 1 <= parsed <= maximum:
        raise ConfigurationError(f"{name} must be between 1 and {maximum}.")
    return parsed


def load_settings(
    *,
    env_file: Path | None = None,
    cwd: Path | None = None,
) -> ViewerSettings:
    """Load supported variables from environment variables and an optional .env."""

    working_directory = (cwd or Path.cwd()).resolve()
    dotenv_path = env_file or working_directory / ".env"
    dotenv = _read_dotenv(dotenv_path)

    usage_raw = _get_value("PANO_VIEWER_HOME", dotenv)
    usage_dir = (
        Path(usage_raw).expanduser()
        if usage_raw
        else working_directory / ".official-viewer"
    )
    if not usage_dir.is_absolute():
        usage_dir = working_directory / usage_dir

    return ViewerSettings(
        server_ak=_get_value("BAIDU_MAP_SERVER_AK", dotenv),
        browser_ak=_get_value("BAIDU_MAP_BROWSER_AK", dotenv),
        usage_dir=usage_dir.resolve(),
        daily_place_limit=_positive_int(
            "BAIDU_MAP_DAILY_PLACE_LIMIT",
            _get_value("BAIDU_MAP_DAILY_PLACE_LIMIT", dotenv),
            4500,
            maximum=100_000,
        ),
        daily_panorama_limit=_positive_int(
            "BAIDU_MAP_DAILY_PANORAMA_LIMIT",
            _get_value("BAIDU_MAP_DAILY_PANORAMA_LIMIT", dotenv),
            100,
            maximum=100_000,
        ),
    )


def public_configuration(settings: ViewerSettings) -> dict[str, object]:
    """Return only values that are safe and necessary for the local browser UI."""

    return {
        # Browser AKs are designed to be present in browser-delivered JS. Their
        # security boundary is the referer allowlist; Server AKs never leave Python.
        "browser_ak": settings.browser_ak,
        "browser_ak_configured": settings.panorama_configured,
        "server_ak_configured": settings.place_search_configured,
        "page_size": settings.page_size,
        "max_pages_per_query": settings.max_pages_per_query,
        "max_results_per_query": settings.max_results_per_query,
    }
