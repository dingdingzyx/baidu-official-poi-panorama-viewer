from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from official_viewer.config import (
    ConfigurationError,
    load_settings,
    public_configuration,
)


class ConfigurationTests(unittest.TestCase):
    def test_dotenv_values_and_safe_public_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            env_file.write_text(
                "BAIDU_MAP_SERVER_AK=server-secret\n"
                "BAIDU_MAP_BROWSER_AK=browser-public\n"
                "BAIDU_MAP_DAILY_PLACE_LIMIT=123\n"
                "PANO_VIEWER_HOME=runtime\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(env_file=env_file, cwd=root)

            self.assertEqual(settings.usage_dir, (root / "runtime").resolve())
            self.assertEqual(settings.daily_place_limit, 123)
            self.assertEqual(settings.max_pages_per_query, 20)
            self.assertEqual(settings.max_results_per_query, 400)
            self.assertNotIn("server-secret", repr(settings))
            public = public_configuration(settings)
            self.assertNotIn("server_ak", public)
            self.assertNotIn("server-secret", str(public))
            self.assertEqual(public["browser_ak"], "browser-public")
            self.assertEqual(public["max_results_per_query"], 400)

    def test_process_environment_overrides_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            env_file.write_text("BAIDU_MAP_SERVER_AK=file-value\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"BAIDU_MAP_SERVER_AK": "environment-value"},
                clear=True,
            ):
                settings = load_settings(env_file=env_file, cwd=root)
            self.assertEqual(settings.server_ak, "environment-value")

    def test_invalid_budget_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            env_file.write_text("BAIDU_MAP_DAILY_PLACE_LIMIT=zero\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_settings(env_file=env_file, cwd=root)
