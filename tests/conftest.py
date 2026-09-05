"""Shared browser fixture: the extension's JS is tested in a real Chromium,
since most of what can go wrong here is DOM behaviour a mock can't reproduce.
"""

from __future__ import annotations

import json
import os

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
EXT_DIR = os.path.join(ROOT, "extension")
FIXTURES_DIR = os.path.join(_HERE, "fixtures")
SCRIPT_FILES = ["field_aliases.js", "matcher.js", "extractor.js", "credentials.js", "filler.js"]

with open(os.path.join(FIXTURES_DIR, "profile.json"), encoding="utf-8") as f:
    PROFILE = json.load(f)


@pytest.fixture(scope="session")
def browser():
    browser_path = os.environ.get("JA_BROWSER_PATH") or None
    with sync_playwright() as p:
        kwargs = {"headless": True}
        if browser_path:
            kwargs["executable_path"] = browser_path
        try:
            b = p.chromium.launch(**kwargs)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium not available for Playwright ({exc}). Run: playwright install chromium")
            return
        yield b
        b.close()


@pytest.fixture
def load(browser):
    """Open a page with the extension's scripts in it. `html` for inline
    markup, `fixture` for a saved form under tests/fixtures/.
    """
    pages = []

    def _load(html=None, fixture=None, scripts=None):
        page = browser.new_page()
        pages.append(page)
        if fixture:
            page.goto(f"file://{os.path.join(FIXTURES_DIR, fixture)}")
        else:
            page.set_content(html or "<body></body>")
        for js in (scripts or SCRIPT_FILES):
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        return page

    yield _load
    for page in pages:
        page.close()
