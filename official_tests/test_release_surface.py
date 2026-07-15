from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _ElementIdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)


class ReleaseSurfaceTests(unittest.TestCase):
    def test_public_entrypoint_delegates_to_official_viewer(self) -> None:
        entrypoint = (ROOT / "wmx.py").read_text(encoding="utf-8")
        self.assertIn("official_viewer.server", entrypoint)

    def test_ignore_rules_exclude_credentials_and_runtime_content(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for required_rule in (
            ".env",
            ".env.*",
            "!.env.example",
            "/.official-viewer/",
            "*.key",
            "*.zip",
        ):
            self.assertIn(required_rule, ignored)

    def test_manifest_contains_only_release_materials(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        for required_rule in (
            "include .env.example",
            "recursive-include official_viewer/static",
            "recursive-include official_tests",
            "*.cjs",
            "exclude .env",
        ):
            self.assertIn(required_rule, manifest)

    def test_browser_code_does_not_render_or_export_panorama_ids(self) -> None:
        browser_code = (ROOT / "official_viewer" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        session_code = (
            ROOT / "official_viewer" / "static" / "query_session.js"
        ).read_text(encoding="utf-8")
        markup = (ROOT / "official_viewer" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("getPanoramaByPOIId", browser_code)
        self.assertIn("state.panorama.setId(data.id)", browser_code)
        self.assertIn('searchParams.set("callback", callbackName)', browser_code)
        self.assertIn('searchParams.set("s", "1")', browser_code)
        self.assertIn('elements.form.addEventListener("submit"', browser_code)
        self.assertIn("pageCache: new Map()", browser_code)
        self.assertIn("inputsMatchActiveSearch", browser_code)
        self.assertIn("useCache: true", browser_code)
        self.assertIn("if (state.busy)", browser_code)
        self.assertIn("buildLoadedResultView", browser_code)
        self.assertIn("buildLoadedResultView", session_code)
        self.assertIn('<form id="query-form"', markup)
        self.assertIn('maxlength="45"', markup)
        self.assertIn('class="data-notice"', markup)
        self.assertLess(
            markup.index("/assets/query_session.js"),
            markup.index("/assets/app.js"),
        )
        self.assertNotIn("panoid", browser_code.lower())
        self.assertNotIn("panoid", session_code.lower())
        self.assertNotIn("download", browser_code.lower())
        self.assertNotIn("localStorage", browser_code)
        self.assertNotIn("sessionStorage", browser_code)
        self.assertNotIn("indexedDB", browser_code)

    def test_browser_element_references_exist_in_markup(self) -> None:
        browser_code = (ROOT / "official_viewer" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        markup = (ROOT / "official_viewer" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        collector = _ElementIdCollector()
        collector.feed(markup)
        marker = 'document.getElementById("'
        referenced_ids = {
            tail.split('"', 1)[0] for tail in browser_code.split(marker)[1:]
        }
        self.assertTrue(referenced_ids)
        self.assertEqual(referenced_ids - collector.ids, set())
