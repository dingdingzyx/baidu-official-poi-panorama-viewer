from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseSurfaceTests(unittest.TestCase):
    def test_public_entrypoint_has_no_legacy_crawler_import(self) -> None:
        entrypoint = (ROOT / "wmx.py").read_text(encoding="utf-8")
        self.assertIn("official_viewer.server", entrypoint)
        self.assertNotIn("pano_crawler", entrypoint)

    def test_ignore_rules_exclude_legacy_and_runtime_content(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for required_rule in (
            "/pano_crawler/",
            "/benchmarks/",
            "/_legacy_private/",
            "/.official-viewer/",
        ):
            self.assertIn(required_rule, ignored)

    def test_manifest_excludes_private_legacy_directories(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        for required_rule in (
            "prune pano_crawler",
            "prune benchmarks",
            "prune tests",
            "prune _legacy_private",
        ):
            self.assertIn(required_rule, manifest)

    def test_browser_code_does_not_render_or_export_panorama_ids(self) -> None:
        browser_code = (ROOT / "official_viewer" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("getPanoramaByPOIId", browser_code)
        self.assertIn("state.panorama.setId(data.id)", browser_code)
        self.assertIn('searchParams.set("callback", callbackName)', browser_code)
        self.assertIn('searchParams.set("s", "1")', browser_code)
        self.assertNotIn("panoid", browser_code.lower())
        self.assertNotIn("download", browser_code.lower())
