"""Learning a page on purpose, and finding it again when the wording moves.

Two complaints this answers, both from real use. Answers typed into a form
often weren't learned at all -- the watcher set up after a fill can only
watch the fields that existed when the fill ran, which on a multi-step
application is the step you were on and nothing after it. And when something
was learned, the next form like it still didn't fill: answers were filed
under the question's exact wording, and no two postings word a question the
same way twice.
"""

from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("playwright.sync_api")

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
EXT_DIR = os.path.join(ROOT, "extension")
FIXTURES_DIR = os.path.join(_HERE, "fixtures")
SCRIPT_FILES = ["field_aliases.js", "matcher.js", "extractor.js", "credentials.js", "filler.js"]

with open(os.path.join(FIXTURES_DIR, "profile.json"), encoding="utf-8") as f:
    PROFILE = json.load(f)


def _page(browser, html):
    page = browser.new_page()
    page.set_content(html)
    for js in SCRIPT_FILES:
        page.add_script_tag(path=os.path.join(EXT_DIR, js))
    return page


def _learn(page):
    return page.evaluate("(profile) => learnPageNow(profile)", PROFILE)


# The same question as two different postings on one system word it, with
# the markup underneath unchanged -- which is the point.
FIRST_POSTING = """
  <form>
    <label for="q1">Which shift are you available for?</label>
    <input id="q1" name="shiftPreference" data-automation-id="shiftPreference">
  </form>"""

SECOND_POSTING = """
  <form>
    <label for="x9">Please tell us the shift you'd like to be considered for</label>
    <input id="x9" name="shiftPreference" data-automation-id="shiftPreference">
  </form>"""


def test_it_learns_what_is_on_the_page_when_the_button_is_pressed(browser):
    """No fill needs to have run, and nothing needs to have been watched --
    it reads the page as it stands.
    """
    page = _page(browser, FIRST_POSTING)
    try:
        page.fill("#q1", "Night shift")
        learned = _learn(page)
    finally:
        page.close()

    assert learned["answers"]["which shift are you available for"] == "Night shift"
    # And under the markup, which is what survives the question being reworded.
    assert learned["markup"]["shift preference"]["answer"] == "Night shift"


def test_the_next_posting_fills_from_the_markup_when_the_wording_changed(browser):
    """The complaint in one test: learned on one form, and the next form
    like it still didn't fill, because the wording moved.
    """
    page = _page(browser, FIRST_POSTING)
    try:
        page.fill("#q1", "Night shift")
        learned = _learn(page)
    finally:
        page.close()

    page = _page(browser, SECOND_POSTING)
    try:
        # Only what a rewritten posting shares with the first: not the label.
        report = page.evaluate(
            """async ({profile, markup}) => {
                setLearnedFields(markup);
                return await fillForm(profile, null, {});
            }""",
            {"profile": PROFILE, "markup": learned["markup"]},
        )
        filled = page.input_value("#x9")
    finally:
        page.close()

    assert filled == "Night shift"
    assert report["results"][0]["action"] == "filled"


def test_a_field_with_no_label_at_all_is_still_learned(browser):
    """A label is the half of a question a form is free not to have."""
    page = _page(browser, """
      <form><input id="q" name="employeeReferralName" aria-label=" "></form>""")
    try:
        page.fill("#q", "Dana Chen")
        learned = _learn(page)
    finally:
        page.close()

    assert learned["markup"]["employee referral name"]["answer"] == "Dana Chen"


def test_a_generated_id_is_not_mistaken_for_an_identity(browser):
    """"input-14" is a render counter, and "answer" belongs to every form
    on the internet. Matching on either would pour one answer into
    unrelated boxes on the next page.
    """
    page = _page(browser, """
      <form><input id="input-14" name="answer"></form>""")
    try:
        page.fill("#input-14", "Something")
        learned = _learn(page)
    finally:
        page.close()

    assert learned["markup"] == {}
    assert learned["skipped"]


def test_what_the_profile_already_answers_is_not_remembered_here(browser):
    """Storing it would freeze today's profile into a store that never
    hears about tomorrow's edit -- and the fill has the profile anyway.
    """
    page = _page(browser, """
      <form>
        <label for="e">Email</label><input id="e" name="emailAddress" value="old@example.com">
      </form>""")
    try:
        learned = _learn(page)
    finally:
        page.close()

    assert learned["answers"] == {}
    assert learned["markup"] == {}


def test_a_gap_in_the_profile_is_offered_rather_than_remembered(browser):
    """A question the matcher knows, answered on the page but blank in the
    profile, belongs in the profile -- suggested, never written.
    """
    profile_without = {**PROFILE, "github_url": ""}
    page = _page(browser, """
      <form>
        <label for="g">GitHub URL</label><input id="g" name="githubProfile" value="https://github.com/x">
      </form>""")
    try:
        learned = page.evaluate("(profile) => learnPageNow(profile)", profile_without)
    finally:
        page.close()

    assert learned["suggestions"]["github_url"] == "https://github.com/x"
    assert learned["markup"] == {}


def test_a_self_identification_answer_is_never_filed_under_a_label_or_markup(browser):
    """Both stores are consulted before the gate that reads what a question
    is asking, so an answer to one of these sitting in either is a way
    straight past it. It goes to the profile field for that question, which
    the gate still governs.
    """
    page = _page(browser, """
      <form>
        <label for="r">Race / Ethnicity</label>
        <input id="r" name="raceEthnicity" data-automation-id="raceEthnicity" value="Asian">
        <label for="c">Have you ever been convicted of a felony?</label>
        <input id="c" name="felonyConviction" value="No">
        <label for="a">I agree to the terms and conditions</label>
        <input id="a" name="termsAgreement" value="Yes">
      </form>""")
    try:
        learned = page.evaluate(
            "(profile) => learnPageNow(profile)",
            {**PROFILE, "race_ethnicity": "", "criminal_history": None},
        )
    finally:
        page.close()

    assert learned["answers"] == {}
    assert "race ethnicity" not in learned["markup"]
    assert "felony conviction" not in learned["markup"]
    assert "terms agreement" not in learned["markup"]
    # The applicant's own answer is kept where it belongs.
    assert learned["suggestions"]["race_ethnicity"] == "Asian"


def test_a_markup_match_cannot_answer_a_sensitive_question(browser):
    """The store is keyed by markup, and markup is not what decides whether
    a question may be answered from a store. A handle learned on an
    innocuous form must not answer a self-ID question on another.
    """
    store = {"applicant notes": {"answer": "No"}}
    profile = {**PROFILE, "hispanic_latino": ""}

    page = _page(browser, """
      <form>
        <label for="q">Do you identify as Hispanic or Latino?</label>
        <input id="q" name="applicantNotes">
      </form>""")
    try:
        report = page.evaluate(
            """async ({profile, store}) => {
                setLearnedFields(store);
                return await fillForm(profile, null, {});
            }""",
            {"profile": profile, "store": store},
        )
        blocked = page.input_value("#q")
    finally:
        page.close()

    assert blocked == ""
    assert report["results"][0]["action"] == "needs_review"

    # Control: the same store and the same markup handle, against a
    # question that isn't sensitive -- so what stopped the fill above was
    # the gate reading the question, not the store failing to apply.
    page = _page(browser, """
      <form>
        <label for="q">Any notes for us?</label>
        <input id="q" name="applicantNotes">
      </form>""")
    try:
        page.evaluate(
            """async ({profile, store}) => {
                setLearnedFields(store);
                return await fillForm(profile, null, {});
            }""",
            {"profile": profile, "store": store},
        )
        assert page.input_value("#q") == "No"
    finally:
        page.close()


def test_correcting_an_answer_the_fill_got_wrong_teaches_it(browser):
    """The one moment the tool is demonstrably wrong used to teach it
    nothing: fields it had filled were skipped by the watcher entirely.
    """
    page = _page(browser, """
      <form>
        <label for="q">Which shift are you available for?</label>
        <input id="q" name="shiftPreference">
      </form>""")
    try:
        out = page.evaluate(
            """async (profile) => {
                setLearnedAnswers({"which shift are you available for": "Days"});
                const report = await fillForm(profile, null, {});
                const learned = {};
                watchForCorrections(report, (m) => Object.assign(learned, m));

                const el = document.getElementById("q");
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, "value").set;
                setter.call(el, "Nights");
                el.dispatchEvent(new Event("change", {bubbles: true}));
                return {filledWith: report.results[0].detail, learned};
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["filledWith"] == "Days"
    assert out["learned"]["which shift are you available for"] == "Nights"


# --- The button itself ------------------------------------------------------

RUN_SCRIPTS = SCRIPT_FILES + ["panel.js"]

LEARN_PAGE = """
  <form>
    <label for="a">First Name</label><input id="a" name="first_name">
    <label for="q">Which shift are you available for?</label>
    <input id="q" name="shiftPreference" value="Night shift">
  </form>"""


def _run_with_panel(browser, html):
    """The whole sequence run.js performs, with chrome stubbed and every
    message it sends recorded.
    """
    page = browser.new_page()
    page.set_content(html)
    for js in RUN_SCRIPTS:
        page.add_script_tag(path=os.path.join(EXT_DIR, js))
    page.add_script_tag(
        content=f"""
          window.__sent = [];
          window.chrome = {{
            storage: {{ local: {{ get: async () => ({{profile: {json.dumps(PROFILE)}, settings: {{}}}}) }} }},
            runtime: {{ sendMessage: async (m) => {{ window.__sent.push(m); return null; }} }},
          }};"""
    )
    page.add_script_tag(path=os.path.join(EXT_DIR, "run.js"))
    page.wait_for_function(
        """() => (document.getElementById('ja-autofill-panel')
                   ?.shadowRoot?.textContent || '').includes('Nothing submitted')""",
        timeout=5000,
    )
    return page


def test_the_panel_button_learns_the_page_it_is_on(browser):
    """The complaint was that pressing it did nothing. It has to read the
    page, store what it finds, and say what it kept.
    """
    page = _run_with_panel(browser, LEARN_PAGE)
    try:
        page.evaluate(
            """() => document.getElementById('ja-autofill-panel')
                       .shadowRoot.querySelector('.learn').click()"""
        )
        page.wait_for_function(
            """() => window.__sent.some((m) => m.type === 'ja-learned-fields')""",
            timeout=5000,
        )
        sent = page.evaluate("() => window.__sent")
        panel_text = page.evaluate(
            "() => document.getElementById('ja-autofill-panel').shadowRoot.textContent"
        )
    finally:
        page.close()

    fields = next(m for m in sent if m["type"] == "ja-learned-fields")
    assert fields["fields"]["shift preference"]["answer"] == "Night shift"
    answers = next(m for m in sent if m["type"] == "ja-learned-answers")
    assert answers["answers"]["which shift are you available for"] == "Night shift"
    # And it says so, rather than leaving you wondering whether it worked.
    assert "Learned" in panel_text and "markup" in panel_text


def test_the_button_reads_the_page_as_it_is_now_not_as_it_was(browser):
    """The reason it exists: on a multi-step application the fields worth
    learning are the ones rendered after the fill ran, which the watcher
    set up at fill time never saw.
    """
    page = _run_with_panel(browser, LEARN_PAGE)
    try:
        # The next step of the application, rendered after the fill.
        page.evaluate(
            """() => {
                const form = document.querySelector('form');
                form.innerHTML = `
                  <label for="n">Which of our machines have you worked on?</label>
                  <input id="n" name="machineExperience" value="Haas VF-2, Tormach 1100">`;
            }"""
        )
        page.evaluate(
            """() => document.getElementById('ja-autofill-panel')
                       .shadowRoot.querySelector('.learn').click()"""
        )
        page.wait_for_function(
            """() => window.__sent.some((m) => m.type === 'ja-learned-fields')""",
            timeout=5000,
        )
        sent = page.evaluate("() => window.__sent")
    finally:
        page.close()

    fields = next(m for m in sent if m["type"] == "ja-learned-fields")
    assert fields["fields"]["machine experience"]["answer"] == "Haas VF-2, Tormach 1100"
