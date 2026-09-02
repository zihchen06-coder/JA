"""Regression tests for the browser extension's JS matching/filling logic.

Run against saved copies of real (or realistically reconstructed) job
application forms in a real headless Chromium via Playwright -- most of the
bugs this suite exists to catch are DOM-behavior bugs (a <select>'s
selectedIndex quirks, computed-style visibility, select2's hidden-accessible
pattern) that a mocked-fields unit test like tests/test_filler.py can't see,
since those only show up once real browser DOM APIs are involved.

This is slower than the rest of the suite (each test needs a real browser
page), by design -- that's the cost of testing real DOM behavior rather than
hand-built field dicts. Run just this file with:
    pytest tests/test_extension_regression.py -v

Fixture HTML files under tests/fixtures/ are frozen snapshots of real forms
encountered during development (with any real personal data scrubbed out
and replaced with the fake tests/fixtures/profile.json identity). They will
not track a live site's markup if that site changes its form later -- this
suite locks in *today's* correct behavior against *today's* saved copy, not
an ongoing guarantee the real site still looks like this.
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
PROFILE_JSON = json.dumps(PROFILE)

# Locked-in baseline: how many fields each saved form fills today with the
# fake profile above. A change that shifts one of these numbers either
# fixed something real (update the baseline to match, deliberately) or
# broke something (fix the code instead) -- never bump a number just to
# make a failing test pass without knowing which of those it is.
EXPECTED = {
    "cc305_form.html": {"filled": 2, "review": 0},
    "edu_form.html": {"filled": 8, "review": 1},
    "eeo.html": {"filled": 5, "review": 1},
    "experience_repeater.html": {"filled": 9, "review": 0},
    "false_positive_check.html": {"filled": 0, "review": 0},
    "icims.html": {"filled": 3, "review": 0},
    "jazzhr_eeo.html": {"filled": 4, "review": 0},
    "jazzlike.html": {"filled": 7, "review": 0},
    "ldg_form.html": {"filled": 12, "review": 0},
    "ldg_real.html": {"filled": 33, "review": 2},
    "multipage.html": {"filled": 3, "review": 0},
    "screening.html": {"filled": 11, "review": 2},
    "select2_state.html": {"filled": 1, "review": 0},
    "test_form.html": {"filled": 12, "review": 1},
    "unknowns.html": {"filled": 1, "review": 0},
}


@pytest.fixture(scope="module")
def browser():
    # Mirrors the CLI's own --browser-path / JA_BROWSER_PATH convention
    # (see ja/browser.py) -- unset, this launches Playwright's normal
    # installed Chromium, exactly what `playwright install chromium` sets
    # up; only set it if you need to point at a specific binary.
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


def _fill(browser, fname: str) -> dict:
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, fname)}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        return page.evaluate("(profile) => fillForm(profile, null)", PROFILE)
    finally:
        page.close()


@pytest.mark.parametrize("fname", sorted(EXPECTED))
def test_fixture_matches_baseline(browser, fname):
    report = _fill(browser, fname)
    filled = sum(1 for r in report["results"] if r["action"] == "filled")
    review = sum(1 for r in report["results"] if r["action"] == "needs_review")
    errors = [r for r in report["results"] if r["action"] == "error"]
    expected = EXPECTED[fname]
    assert not errors, f"{fname}: unexpected error(s): {errors}"
    assert filled == expected["filled"], f"{fname}: filled {filled}, expected {expected['filled']}"
    assert review == expected["review"], f"{fname}: review {review}, expected {expected['review']}"


def test_select2_duplicate_placeholder_state_dropdown(browser):
    """A templated State <select> with a duplicated placeholder option (two
    <option value=""> both marked selected, one also disabled) left the
    browser's real selectedIndex on 1 instead of 0 -- indistinguishable from
    a real answer under the old "selectedIndex > 0 means already answered"
    check. Must still resolve to the real value, not get skipped.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'select2_state.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        page.evaluate("(profile) => fillForm(profile, null)", PROFILE)
        value = page.eval_on_selector("#region", "el => el.value")
    finally:
        page.close()
    assert value == "NY"


def test_experience_repeater_fields(browser):
    """Bare 'Job title'/'Company'/'Location'/'From'/'To' fields inside a
    work-history repeater block (identified by machine name, e.g.
    experience[0][company], not label text -- see
    matcher.experience_field_for) must fill from profile.experience[0],
    including the "I currently work here" checkbox and leaving an ongoing
    job's end date blank instead of typing "Present" into a date field.
    Also checks the Degree->education_level fallback on the same fixture.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'experience_repeater.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        page.evaluate("(profile) => fillForm(profile, null)", PROFILE)

        job_title = page.eval_on_selector("#experience_job_title", "el => el.value")
        company = page.eval_on_selector("#experience_company", "el => el.value")
        location = page.eval_on_selector("#experience_location", "el => el.value")
        current_checked = page.eval_on_selector(
            'input[name="experience[0][current_work]"]', "el => el.checked"
        )
        work_start = page.eval_on_selector('input[name="experience[0][work_start]"]', "el => el.value")
        work_end = page.eval_on_selector('input[name="experience[0][work_end]"]', "el => el.value")
        degree_text = page.eval_on_selector(
            '[id="education[0][degree]"]', "el => el.options[el.selectedIndex].text"
        )
    finally:
        page.close()

    entry = PROFILE["experience"][0]
    assert job_title == entry["title"]
    assert company == entry["company"]
    assert location == entry["location"]
    assert current_checked is True  # end_date is "Present"
    assert work_start == "06/2023"  # "2023-06" -> MM/YYYY
    assert work_end == ""  # left blank; the checkbox represents "Present" instead
    assert degree_text == "Bachelors Degree"  # falls back to education_level, not the stored "B.S."
