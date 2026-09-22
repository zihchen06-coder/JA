"""The Options page's profile checkup, run in a real browser.

Every check here came from a value that was actually saved in a real
profile and actually cost a field on a real form -- a LinkedIn URL with no
scheme, a country abbreviated to "US". The point of the checkup is that
those are seen on the Options page rather than on the application that
rejects them, so these tests are about what it says, not how it looks.
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


@pytest.fixture
def check(browser):
    """profileWarnings(profile) -> the findings, as plain dicts."""
    page = browser.new_page()
    page.goto("about:blank")
    page.add_script_tag(path=os.path.join(EXT_DIR, "profile_check.js"))

    def _check(**overrides):
        return page.evaluate("(profile) => profileWarnings(profile)", {**PROFILE, **overrides})

    yield _check
    page.close()


def _for(findings, field):
    return [f for f in findings if f["field"] == field]


def test_a_url_without_a_scheme_is_an_error_with_the_fix_offered(check):
    """<input type="url"> rejects a bare host on submit, so the fill looks
    fine right up until the form refuses to go through.
    """
    findings = _for(check(linkedin_url="linkedin.com/in/someone"), "linkedin_url")
    assert len(findings) == 1
    assert findings[0]["level"] == "error"
    assert findings[0]["fix"] == "https://linkedin.com/in/someone"


def test_an_abbreviated_country_is_an_error_with_the_fix_offered(check):
    """A country dropdown is matched on its option text, and no real form
    lists "US".
    """
    findings = _for(check(country="US"), "country")
    assert len(findings) == 1
    assert findings[0]["level"] == "error"
    assert findings[0]["fix"] == "United States"
    # Already spelled out: nothing to say.
    assert _for(check(country="United States"), "country") == []


def test_a_company_specific_question_is_flagged_wherever_it_is_set(check):
    """One saved answer is reused at every employer, and this question is
    asked by each company about itself -- so a saved "no" is wrong at the
    company the applicant currently works for.
    """
    warned = _for(check(previously_employed_here=False, current_company="Acme"), "previously_employed_here")
    assert len(warned) == 1
    assert warned[0]["level"] == "warn"
    assert "Acme" in warned[0]["message"]
    # false is a real answer and so is true; unset is the one that doesn't
    # need saying, because unset already means "ask me on each form".
    assert _for(check(previously_employed_here=None), "previously_employed_here") == []


def test_questions_with_no_answer_yet_are_counted_not_faulted(check):
    """A blank answer is a question they mean to get to, so this is a count
    and a reminder of what it costs, not an error.
    """
    findings = _for(check(custom_answers={"why do you want to work": "", "career goals": "Build things."}),
                    "custom_answers")
    assert len(findings) == 1
    assert findings[0]["level"] == "info"
    assert "1 question" in findings[0]["message"]
    assert "why do you want to work" in findings[0]["message"]


def test_a_salary_answer_in_words_is_explained_not_faulted(check):
    """Refusing to name a number is a position, not a mistake. What's worth
    knowing is that a numeric box will drop it.
    """
    findings = _for(check(desired_salary="Depends on the budget for this role"), "desired_salary")
    assert len(findings) == 1
    assert findings[0]["level"] == "info"
    assert not findings[0]["fix"]


def test_dates_and_years_are_checked_in_the_form_the_fill_uses(check):
    """A work-history block is filled month-and-year from YYYY-MM, and a
    graduation-year box wants four digits.
    """
    findings = check(
        education=[{"school": "State University", "graduation_year": "May 2028"}],
        experience=[{"company": "Acme", "start_date": "05/2026", "end_date": "Present"}],
    )
    assert _for(findings, "education[0].graduation_year")[0]["level"] == "warn"
    assert _for(findings, "experience[0].start_date")[0]["level"] == "warn"
    # "Present" is how the profile says a job is current, not a bad date.
    assert _for(findings, "experience[0].end_date") == []


def test_the_shipped_example_profile_raises_nothing_a_form_would_reject(check):
    """The fake identity the rest of the suite fills forms with has to be a
    profile the checkup would pass, or every other test is working from one
    the tool itself considers broken.
    """
    findings = check()
    assert [f for f in findings if f["level"] == "error"] == []


def test_a_profile_with_nothing_in_it_does_not_throw(check):
    """The Options page runs this on first open, before anything is saved."""
    empty = {k: "" for k in PROFILE if isinstance(PROFILE[k], str)}
    empty.update(education=[], experience=[], custom_answers={}, previously_employed_here=None)
    page_findings = check(**empty)
    assert isinstance(page_findings, list)
    assert [f for f in page_findings if f["level"] == "error"] == []
