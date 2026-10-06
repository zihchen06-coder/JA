"""The Options page, opened against stored data that has gone bad.

This page is where every value the tool uses is entered and edited, so a
page that renders half of itself is worse here than anywhere else -- the
applicant sees empty boxes and reasonably concludes their profile is gone.
It has happened once already (commit 423eecb), which is why each section is
drawn on its own.

The page is loaded from disk with `chrome` stubbed in before its own
scripts run, so this is the real options.html and options.js.
"""

from __future__ import annotations

import json
import os

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
EXT_DIR = os.path.join(ROOT, "extension")
FIXTURES_DIR = os.path.join(_HERE, "fixtures")

with open(os.path.join(FIXTURES_DIR, "profile.json"), encoding="utf-8") as f:
    PROFILE = json.load(f)


def _open_options(browser, stored):
    page = browser.new_page()
    # Has to be in place before options.js runs, so it is injected as an
    # init script with the stored data baked into it.
    page.add_init_script(
        f"""window.chrome = {{
              storage: {{ local: {{
                get: async () => ({json.dumps(stored)}),
                set: async () => {{}},
              }} }},
            }};"""
    )
    page.goto(f"file://{os.path.join(EXT_DIR, 'options.html')}")
    return page


def test_a_profile_with_a_broken_list_still_draws_the_rest_of_the_page(browser):
    """`education` arriving as a string is what an old export or a hand-
    edited import looks like. It used to stop the render where it stood,
    taking the answers, the settings toggles and every list below it.
    """
    page = _open_options(browser, {
        "profile": {**PROFILE, "education": "not a list", "experience": [None, "junk"]},
        "settings": {"use_llm": True},
    })
    try:
        page.wait_for_function("() => document.getElementById('answers-list').children.length > 0",
                               timeout=5000)
        # Everything after the broken section: the answers list, the
        # settings toggles, and the basics at the top.
        assert page.evaluate("() => document.getElementById('answers-list').children.length") > 0
        assert page.evaluate("() => document.getElementById('s-use-llm').checked") is True
        assert page.input_value('[data-f="first_name"]') == PROFILE["first_name"]
    finally:
        page.close()


def test_the_checkup_shows_what_a_form_would_reject(browser):
    """The whole point of it being on this page is that the applicant sees
    it before the application does.
    """
    page = _open_options(browser, {
        "profile": {**PROFILE, "country": "US", "linkedin_url": "linkedin.com/in/someone"},
        "settings": {},
    })
    try:
        page.wait_for_selector("#profile-warnings .chk", timeout=5000)
        text = page.inner_text("#profile-warnings")
        assert "United States" in text
        assert "https://" in text

        # The offered fix puts the value in the box, and the finding it was
        # about goes away -- without saving, which stays the applicant's.
        page.click('#profile-warnings .chk:has-text("Country") button')
        assert page.input_value('[data-f="country"]') == "United States"
        assert "matches nothing" not in page.inner_text("#profile-warnings")
    finally:
        page.close()


def test_an_empty_install_opens_with_nothing_to_report(browser):
    """First open, before anything has been entered: no findings, no
    errors, and the page still draws.
    """
    page = _open_options(browser, {})
    try:
        page.wait_for_selector("#profile-warnings", state="attached", timeout=5000)
        assert page.inner_text("#profile-warnings").strip() == ""
        assert page.input_value('[data-f="first_name"]') == ""
    finally:
        page.close()
