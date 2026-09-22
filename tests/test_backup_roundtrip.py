"""Export everything, import it back, and still have everything.

This is the workflow the backup exists for: take the data out, look it over
(or hand it to someone who will), put it back. A round trip that quietly
drops a field is worse than no export at all, because the loss is only
noticed later, on a form, with the wrong answer already in it.

The Options page is loaded from disk with `chrome` stubbed in, so this is
the real options.html, options.js and profile_check.js.
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

STORES = {
    "settings": {"use_llm": True, "watch_and_learn": False},
    "learned_aliases": {"what is your home phone": "phone"},
    "learned_answers": {"what shift can you work": "Any"},
    "profile_suggestions": {"portfolio_url": "https://example.com"},
    "misses": {"spirit animal": {"label": "Spirit animal", "count": 3, "last": 1}},
    "applications": [{"host": "boards.greenhouse.io", "title": "Intern", "at": 1}],
}


def _open_options(browser, stored):
    """The Options page, with what storage holds and what it gets written."""
    page = browser.new_page()
    page.add_init_script(
        f"""window.__written = {{}};
            window.chrome = {{
              storage: {{ local: {{
                get: async () => ({json.dumps(stored)}),
                set: async (items) => Object.assign(window.__written, items),
              }} }},
            }};"""
    )
    page.goto(f"file://{os.path.join(EXT_DIR, 'options.html')}")
    page.wait_for_selector("#profile-warnings", state="attached", timeout=5000)
    return page


def _import(page, data, overwrite=True, raw=None):
    page.evaluate(
        """({text, overwrite}) => {
            document.getElementById('import-overwrite').checked = overwrite;
            document.getElementById('import-json').value = text;
            document.getElementById('import-json-btn').click();
        }""",
        {"text": raw if raw is not None else json.dumps(data), "overwrite": overwrite},
    )
    page.wait_for_function(
        "() => document.getElementById('import-status').textContent.trim() !== ''",
        timeout=5000,
    )
    return page.inner_text("#import-status")


def test_a_backup_carries_the_profile_and_everything_learned(browser):
    page = _open_options(browser, {"profile": PROFILE, **STORES})
    try:
        backup = page.evaluate("() => fullBackup()")
        wired = page.evaluate("() => typeof document.getElementById('export-all').onclick")
    finally:
        page.close()

    assert wired == "function"

    assert backup["profile"]["first_name"] == PROFILE["first_name"]
    assert backup["profile"]["custom_answers"] == PROFILE["custom_answers"]
    for key, value in STORES.items():
        assert backup[key] == value, key
    # A document is megabytes of base64 and a login is a password. Neither
    # belongs in a file meant to be pasted into a chat.
    assert "resume_file" not in backup["profile"]
    assert "credentials" not in backup
    assert "llm_api_key" not in backup



def test_a_backup_put_back_into_an_empty_install_restores_all_of_it(browser):
    """The actual round trip: everything out of one browser, into another
    that has never seen any of it.
    """
    source = _open_options(browser, {"profile": PROFILE, **STORES})
    backup = source.evaluate("() => fullBackup()")
    source.close()

    page = _open_options(browser, {})
    try:
        status = _import(page, backup)
        assert page.input_value('[data-f="first_name"]') == PROFILE["first_name"]
        assert page.input_value('[data-f="email"]') == PROFILE["email"]
        assert page.input_value('[data-f="city"]') == PROFILE["city"]
        # A yes/no answer is a <select>, and `false` is an answer -- reading
        # it as "nothing saved" is how a "no" turns into "ask me again".
        assert page.input_value('[data-bool="needs_sponsorship"]') == "false"
        assert page.input_value('[data-bool="work_authorized"]') == "true"
        assert page.evaluate("() => document.getElementById('edu-list').children.length") == len(
            PROFILE["education"]
        )
        assert page.evaluate("() => document.getElementById('answers-list').children.length") == len(
            PROFILE["custom_answers"]
        )

        written = page.evaluate("() => window.__written")
        for key, value in STORES.items():
            assert written[key] == value, key
        assert "learned label" in status and "application" in status
        # Restored settings reach the toggles, not just storage.
        assert page.evaluate("() => document.getElementById('s-use-llm').checked") is True
        assert page.evaluate("() => document.getElementById('s-watch-learn').checked") is False
    finally:
        page.close()


def test_the_plain_profile_export_can_be_imported_back(browser):
    """"Export profile" writes its fields at the top level, and the import
    read only `fields` -- so the tool's own export, put straight back, kept
    the education and the answers and silently dropped every scalar on it:
    name, email, phone, address, the lot.
    """
    source = _open_options(browser, {"profile": PROFILE})
    exported = source.evaluate("() => exportableProfile()")
    source.close()

    page = _open_options(browser, {})
    try:
        _import(page, exported)
        assert page.input_value('[data-f="first_name"]') == PROFILE["first_name"]
        assert page.input_value('[data-f="phone"]') == PROFILE["phone"]
        assert page.input_value('[data-f="address_line1"]') == PROFILE["address_line1"]
    finally:
        page.close()


def test_an_imported_alias_may_not_point_at_a_self_identification_field(browser):
    """A learned alias is consulted before every other check when a label is
    matched, so one pointing at a self-ID field is a way straight past the
    gate that exists to stop exactly that. A file is not a reason to relax
    it, however it was produced -- hand-edited, or written by a version of
    this tool that allowed it.
    """
    page = _open_options(browser, {"profile": PROFILE})
    try:
        status = _import(page, {
            "ja_backup": 1,
            "learned_aliases": {
                "did you graduate": "hispanic_latino",
                "sign here": "consent_general",
                "what is your home phone": "phone",
            },
        })
        written = page.evaluate("() => window.__written.learned_aliases")
        assert written == {"what is your home phone": "phone"}
        assert "2 refused" in status
    finally:
        page.close()


def test_importing_never_clears_what_the_file_does_not_mention(browser):
    """A backup from before a store existed, or one with a section deleted
    by hand, adds what it has. It does not wipe the rest -- and the
    documents, logins and API key it never carried are not its to remove.
    """
    page = _open_options(browser, {"profile": PROFILE, **STORES})
    try:
        _import(page, {"ja_backup": 1, "learned_answers": {"a": "b"}})
        written = page.evaluate("() => window.__written")
        assert written["learned_answers"] == {"a": "b"}
        for untouched in ("applications", "misses", "learned_aliases", "settings",
                          "credentials", "llm_api_key"):
            assert untouched not in written, untouched
    finally:
        page.close()


def test_junk_in_the_box_is_refused_rather_than_stored(browser):
    """The box takes a pasted file, and a paste can be anything."""
    page = _open_options(browser, {"profile": PROFILE})
    try:
        assert "not valid JSON" in _import(page, None, raw="}{ not json")
        assert page.evaluate("() => Object.keys(window.__written).length") == 0

        page.evaluate("() => (document.getElementById('import-status').textContent = '')")
        assert "expected an object" in _import(page, [1, 2, 3])
        assert page.evaluate("() => Object.keys(window.__written).length") == 0
    finally:
        page.close()


def test_a_backup_with_a_store_full_of_junk_does_not_break_the_page(browser):
    """Hand-edited files arrive in every shape there is."""
    page = _open_options(browser, {"profile": PROFILE})
    try:
        _import(page, {
            "ja_backup": 1,
            "learned_aliases": "not an object",
            "applications": {"not": "a list"},
            "misses": None,
            "settings": [1, 2],
        })
        written = page.evaluate("() => window.__written")
        assert written["learned_aliases"] == {}
        assert written["applications"] == []
        assert written["misses"] == {}
        assert written["settings"] == {}
        # And the page is still standing.
        assert page.input_value('[data-f="first_name"]') == PROFILE["first_name"]
    finally:
        page.close()
