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
    # 6, not 5, since the self-ID answers stopped going through bestOption:
    # a Hispanic/Latino question offering Yes and No used to be written off
    # as "a yes/no question with no matching saved answer" before the saved
    # answer was ever tried against it.
    "eeo.html": {"filled": 6, "review": 1},
    "experience_repeater.html": {"filled": 9, "review": 0},
    "false_positive_check.html": {"filled": 0, "review": 0},
    "icims.html": {"filled": 3, "review": 0},
    "icims_profile.html": {"filled": 24, "review": 1},
    "jazzhr_eeo.html": {"filled": 4, "review": 0},
    "jazzlike.html": {"filled": 7, "review": 0},
    "ldg_form.html": {"filled": 13, "review": 0},
    "ldg_real.html": {"filled": 33, "review": 2},
    "multipage.html": {"filled": 3, "review": 0},
    "routing.html": {"filled": 1, "review": 0},
    "screening.html": {"filled": 11, "review": 2},
    "select2_state.html": {"filled": 1, "review": 0},
    "test_form.html": {"filled": 12, "review": 1},
    "unknowns.html": {"filled": 1, "review": 0},
    "workday_questions.html": {"filled": 6, "review": 0},
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


def test_workday_listbox_buttons(browser):
    """Workday asks its questionnaire with <button aria-haspopup="listbox">:
    no <select> anywhere, and no options in the DOM at all until the button
    is clicked and its popup renders. Every one of them was invisible to a
    scan of `input, select, textarea`, so the whole step filled nothing.

    The fixture's open-state behaviour is a stand-in for Workday's own
    bundle, written to the ARIA contract that aria-haspopup="listbox"
    declares (see the note at the top of the fixture) -- which is what
    filler.js drives, rather than any vendor's class names.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'workday_questions.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        page.evaluate("(profile) => fillForm(profile, null)", PROFILE)
        answers = page.evaluate(
            """() => Object.fromEntries(
                Array.from(document.querySelectorAll('button[aria-haspopup=\"listbox\"]'))
                     .map((b) => [b.closest('fieldset').querySelector('b').textContent,
                                  b.textContent.trim()])
            )"""
        )
        # Nothing may be left hanging open over the rest of the form.
        still_open = page.evaluate(
            "() => document.querySelectorAll('[role=\"listbox\"]').length"
        )
    finally:
        page.close()

    assert answers["Are you 18 years of age or older?"] == "Yes"  # over_18
    assert answers["Are you eligible to work in the US?"] == "Yes"  # work_authorized
    assert answers["Highest level of education?"] == "Bachelor's Degree"
    assert answers["Have you worked with us before?"] == "No"  # previously_employed_here
    assert (
        answers["Do you currently require visa sponsorship to work in the country in "
                "which the job you wish to be employed is located?"] == "No"
    )
    assert still_open == 0


def test_icims_custom_dropdowns_and_work_history(browser):
    """iCIMS hides the real <select> (display:none, holding only an empty
    placeholder <option>) behind its own widget, and keeps the actual choices
    in a sibling <ul> of <li role="option"> -- so these fields were never
    even extracted, and there were no options to match a value against if
    they had been. Its work-history block is the other half of the problem:
    the fields there are named opaquely (rcf3212) and labelled generically
    ("Employer", "City", "Month"), so they only make sense relative to the
    section they sit in.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'icims_profile.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        report = page.evaluate("(profile) => fillForm(profile, null)", PROFILE)
        shown = page.evaluate(
            """() => {
                const text = (id) => {
                    const el = document.getElementById(id + '_fakeSelected_icimsDropdown');
                    return el ? el.textContent.trim() : null;
                };
                const val = (id) => document.getElementById(id).value;
                return {
                    country: text('-1_PersonProfileFields.AddressCountry'),
                    state: text('-1_PersonProfileFields.AddressState'),
                    school: text('-1_CandProfileFields.School'),
                    degree: text('-1_CandProfileFields.Degree'),
                    current_job: text('-1_PersonProfileFields.rcf3269'),
                    employer: val('-1_PersonProfileFields.rcf3212'),
                    title: val('-1_PersonProfileFields.rcf3213'),
                    city: val('-1_PersonProfileFields.rcf3216'),
                    start_month: val('-1_PersonProfileFields.rcf3214_Month'),
                    start_year: val('-1_PersonProfileFields.rcf3214_Year'),
                    end_year: val('-1_PersonProfileFields.rcf3215_Year'),
                    employer_state: val('-1_PersonProfileFields.rcf3217'),
                    other_school: val('-1_CandProfileFields.OtherSchool'),
                    sms_consent: val('rcf3553'),
                };
            }"""
        )
    finally:
        page.close()

    entry = PROFILE["experience"][0]
    assert shown["country"] == "United States"
    # Both of these only exist on the widget's second page of results, which
    # it fetches through its own search box.
    assert shown["state"] == "New York"
    assert shown["school"] == "State University"
    assert shown["degree"] == "BS"  # closest listed spelling of the saved "B.S."

    assert shown["employer"] == entry["company"]
    assert shown["title"] == entry["title"]
    # "Springfield, NY" belongs in a Location box, not in a City box that has
    # its own State box beside it.
    assert shown["city"] == "Springfield"
    assert shown["start_month"] == "06"
    assert shown["start_year"] == "2023"
    # end_date is "Present", so the end boxes stay empty and the block's own
    # "Is this your current job?" dropdown carries that instead.
    assert shown["end_year"] == ""
    assert shown["current_job"] == "Yes"

    # The employer's State is not the applicant's.
    assert shown["employer_state"] in ("", "-999")
    # "Other School" is the escape hatch for a school the list doesn't have.
    assert shown["other_school"] == ""
    # An SMS-consent question is never answered automatically.
    assert shown["sms_consent"] == ""
    consent = next(
        r for r in report["results"] if "consent to receive text" in r["label"].lower()
    )
    # Nothing saved for it, so nothing is consented to. (With sms_consent set
    # in the profile it would be answered -- see the sensitive-answers tests.)
    assert consent["action"] != "filled"
    assert consent["required"] is True


def _llm_pass(browser, fname, answers, skipped=None):
    """Run the normal fill, then apply a fabricated set of Claude answers."""
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, fname)}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        return page.evaluate(
            """async ({profile, answers, skipped}) => {
                const report = await fillForm(profile, null);
                const offered = llmFieldsFor(report);
                // Address the fabricated answers by label, the way a caller
                // reading the report would, rather than by internal id.
                const idFor = (label) => {
                    const f = (report.fields || []).find(
                        (x) => (x.label || '').toLowerCase().includes(label.toLowerCase())
                    );
                    return f ? f.ja_id : null;
                };
                const byId = {};
                for (const [label, value] of Object.entries(answers)) {
                    const id = idFor(label);
                    if (id) byId[id] = value;
                }
                const filled = await applyLlmAnswers(report, byId, skipped || {});
                return {
                    filled,
                    offered: offered.map((f) => f.label),
                    requested: Object.keys(byId).length,
                    values: Object.fromEntries(
                        Object.entries(byId).map(([id, _]) => {
                            const el = document.querySelector(`[data-ja-id="${id}"]`);
                            return [id, el ? (el.type === 'checkbox' ? String(el.checked) : el.value) : null];
                        })
                    ),
                };
            }""",
            {"profile": PROFILE, "answers": answers, "skipped": skipped or {}},
        )
    finally:
        page.close()


def test_llm_pass_never_offers_sensitive_or_consent_fields(browser):
    """The set of fields handed to Claude is built here, not chosen by it.
    Self-identification, criminal-history and consent questions must never be
    in it, whatever the model would have done with them -- and neither must
    checkboxes or radios, which is how forms ask you to agree to things.
    """
    offered = _llm_pass(browser, "icims_profile.html", {})["offered"]
    # Guard against the assertions below passing because nothing at all was
    # offered -- this form has plenty the matcher can't place.
    assert len(offered) >= 5, offered
    joined = " | ".join(offered).lower()
    for forbidden in ("consent to receive text", "password", "gender", "race",
                      "ethnicity", "veteran", "disability"):
        assert forbidden not in joined, f"{forbidden!r} was offered to the model: {offered}"

    # A form that is nothing but self-identification and criminal-history
    # questions has nothing to hand over at all.
    for eeo_form in ("eeo.html", "cc305_form.html", "jazzhr_eeo.html"):
        assert _llm_pass(browser, eeo_form, {})["offered"] == []

    offered = _llm_pass(browser, "screening.html", {})["offered"]
    joined = " | ".join(offered).lower()
    for forbidden in ("felony", "convict", "background check", "drug", "authoriz", "agree"):
        assert forbidden not in joined, f"{forbidden!r} was offered to the model: {offered}"


def test_llm_answers_for_fields_that_were_never_offered_are_dropped(browser):
    """An answer is applied only for a field this side put up for answering.
    A model that returns an answer for a consent box, a self-ID question, or
    a field that was already filled gets ignored -- the guarantee is enforced
    on the way in, not asked of the prompt.
    """
    result = _llm_pass(
        browser,
        "icims_profile.html",
        {
            "Do you consent to receive text": "Yes",
            "First Name": "Should Not Overwrite",
        },
    )
    assert result["requested"] == 2  # both were addressed by the fabricated answer
    assert result["filled"] == 0  # neither was applied
    values = list(result["values"].values())
    assert "Yes" not in values
    assert "Should Not Overwrite" not in values
    assert "Jamie" in values  # the real fill stands untouched


def test_llm_select_answer_must_match_an_option_exactly(browser):
    """Picking the wrong item out of a dropdown is worse than leaving it
    blank, so only an exact option string is accepted -- no fuzzy matching on
    the model's output.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'workday_questions.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        outcome = page.evaluate(
            """async (profile) => {
                const thin = {...profile};
                // Nothing saved for it, so the matcher leaves it to the second pass.
                delete thin.education_level;
                const report = await fillForm(thin, null);
                const target = (report.fields || []).find(
                    (f) => (f.label || '').includes('Highest level of education')
                );
                const near = await applyLlmAnswers(report, {[target.ja_id]: "Bachelors Degree"}, {});
                const afterNear = document.querySelector(
                    `[data-ja-id="${target.ja_id}"]`).textContent.trim();
                const exact = await applyLlmAnswers(report, {[target.ja_id]: "Bachelor's Degree"}, {});
                const afterExact = document.querySelector(
                    `[data-ja-id="${target.ja_id}"]`).textContent.trim();
                return {near, afterNear, exact, afterExact};
            }""",
            PROFILE,
        )
    finally:
        page.close()

    # "Bachelors Degree" is not one of the options; "Bachelor's Degree" is.
    assert outcome["near"] == 0
    assert outcome["afterNear"] == "Select One"
    assert outcome["exact"] == 1
    assert outcome["afterExact"] == "Bachelor's Degree"


def _llm_call(browser, responses, model=None):
    """Run llm.js against a stubbed fetch and report what it sent and returned.

    `responses` is the queue of {status, body} the fake API hands back, one
    per request, so a retry can be given a different answer than the first
    attempt.
    """
    page = browser.new_page()
    try:
        page.goto("about:blank")
        page.add_script_tag(path=os.path.join(EXT_DIR, "llm.js"))
        return page.evaluate(
            """async ({responses, profile, model}) => {
                if (model) LLM_MODEL = model;
                const sent = [];
                const queue = [...responses];
                window.fetch = async (url, init) => {
                    sent.push({url, headers: init.headers, body: JSON.parse(init.body)});
                    const next = queue.shift();
                    return {
                        ok: next.status === 200,
                        status: next.status,
                        text: async () => JSON.stringify(next.body),
                    };
                };
                const result = await resolveWithClaude({
                    apiKey: "sk-ant-test",
                    profile,
                    fields: [{ja_id: "ja-1", label: "Why do you want this role?",
                              type: "textarea", required: true, options: []}],
                    pageUrl: "https://example.com/apply",
                });
                return {sent, result};
            }""",
            {"responses": responses, "profile": PROFILE, "model": model},
        )
    finally:
        page.close()


def _ok_body(answers):
    return {
        "content": [{"type": "text", "text": json.dumps({"answers": answers})}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def test_llm_request_shape_and_answer_parsing(browser):
    out = _llm_call(
        browser,
        [{"status": 200, "body": _ok_body([
            {"ja_id": "ja-1", "value": "Because the work is hands-on.", "skip_reason": ""},
        ])}],
    )
    assert out["result"]["answers"] == {"ja-1": "Because the work is hands-on."}

    sent = out["sent"][0]
    assert sent["url"] == "https://api.anthropic.com/v1/messages"
    assert sent["headers"]["x-api-key"] == "sk-ant-test"
    assert sent["headers"]["anthropic-version"] == "2023-06-01"
    # Required to call the API from a browser context at all.
    assert sent["headers"]["anthropic-dangerous-direct-browser-access"] == "true"
    assert sent["body"]["model"] == "claude-sonnet-5"
    assert sent["body"]["output_config"]["format"]["type"] == "json_schema"

    # The resume and cover letter are stored as base64 data URLs for
    # attaching to upload fields; they have no business in a prompt.
    system = sent["body"]["system"][0]["text"]
    assert "resume_file" not in system
    assert "cover_letter_file" not in system
    assert PROFILE["first_name"] in system


def test_llm_retries_once_without_the_fallback_beta_on_a_400(browser):
    """The server-side fallbacks parameter is the newest thing in the request.
    If the API rejects the shape, still get an answer rather than failing the
    fill over an optional extra. Pinned to a model that sends it at all --
    see the test below for the one that doesn't.
    """
    out = _llm_call(
        browser,
        [
            {"status": 400, "body": {"error": {"message": "unsupported beta"}}},
            {"status": 200, "body": _ok_body([
                {"ja_id": "ja-1", "value": "Second time.", "skip_reason": ""},
            ])},
        ],
        model="claude-opus-5",
    )
    assert len(out["sent"]) == 2
    assert "anthropic-beta" in out["sent"][0]["headers"]
    assert "fallbacks" in out["sent"][0]["body"]
    assert "anthropic-beta" not in out["sent"][1]["headers"]
    assert "fallbacks" not in out["sent"][1]["body"]
    assert out["result"]["answers"] == {"ja-1": "Second time."}


def test_llm_surfaces_api_errors_and_refusals_instead_of_filling(browser):
    out = _llm_call(
        browser,
        [
            {"status": 401, "body": {"error": {"message": "invalid x-api-key"}}},
            {"status": 401, "body": {"error": {"message": "invalid x-api-key"}}},
        ],
    )
    # A 401 is not a 400, so it is not retried -- one attempt, error reported.
    assert len(out["sent"]) == 1
    assert out["result"]["error"] == "invalid x-api-key"

    out = _llm_call(browser, [{"status": 200, "body": {"content": [], "stop_reason": "refusal"}}])
    assert "declined" in out["result"]["error"]


def test_llm_blank_values_become_skips_not_empty_fills(browser):
    out = _llm_call(
        browser,
        [{"status": 200, "body": _ok_body([
            {"ja_id": "ja-1", "value": "", "skip_reason": "sensitive"},
        ])}],
    )
    assert out["result"]["answers"] == {}
    assert out["result"]["skipped"] == {"ja-1": "sensitive"}


def _llm_call_with_fields(browser, fields):
    page = browser.new_page()
    try:
        page.goto("about:blank")
        page.add_script_tag(path=os.path.join(EXT_DIR, "llm.js"))
        return page.evaluate(
            """async ({profile, fields}) => {
                let sent = null;
                window.fetch = async (url, init) => {
                    sent = JSON.parse(init.body);
                    return {ok: true, status: 200, text: async () => JSON.stringify({
                        content: [{type: "text", text: JSON.stringify({answers: []})}],
                        stop_reason: "end_turn",
                    })};
                };
                await resolveWithClaude({
                    apiKey: "sk-ant-test", profile, fields,
                    pageUrl: "https://example.com/apply",
                });
                return sent.system[0].text;
            }""",
            {"profile": PROFILE, "fields": fields},
        )
    finally:
        page.close()


def test_written_answers_are_only_sent_when_a_page_asks_an_open_question(browser):
    """A filled-in Answers tab is several thousand tokens and exists to supply
    the applicant's voice on essay questions. A page of contact boxes and
    dropdowns has none, so sending them there is most of the request's cost
    buying nothing.
    """
    answer_text = PROFILE["custom_answers"]["why do you want to work"]

    dropdowns_only = _llm_call_with_fields(browser, [
        {"ja_id": "ja-1", "label": "Country", "type": "select", "options": ["United States"]},
        {"ja_id": "ja-2", "label": "City", "type": "text", "options": []},
    ])
    assert answer_text not in dropdowns_only
    assert PROFILE["first_name"] in dropdowns_only  # the rest of the profile still goes

    with_textarea = _llm_call_with_fields(browser, [
        {"ja_id": "ja-1", "label": "Tell us about yourself", "type": "textarea", "options": []},
    ])
    assert answer_text in with_textarea

    # A one-line box can still hold a real question.
    with_question = _llm_call_with_fields(browser, [
        {"ja_id": "ja-1", "label": "Why do you want to work here?", "type": "text", "options": []},
    ])
    assert answer_text in with_question


def _fill_with(browser, fname, overrides):
    profile = {**PROFILE, **overrides}
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, fname)}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        report = page.evaluate("(profile) => fillForm(profile, null)", profile)
        checked = page.evaluate(
            """() => Array.from(document.querySelectorAll('input:checked'))
                        .map((el) => (
                            document.querySelector(`label[for="${el.id}"]`)?.textContent
                            || el.closest('label')?.textContent
                            || el.value
                        ).trim())"""
        )
        return report, checked
    finally:
        page.close()


def _result_for(report, needle):
    return next(r for r in report["results"] if needle.lower() in (r["label"] or "").lower())


def test_criminal_history_is_flagged_until_the_applicant_answers_it_themselves(browser):
    """It is never inferred -- not from the profile, not from the resume, and
    the AI-assist pass never sees it. Unset means flagged on every form.
    """
    report, checked = _fill_with(browser, "screening.html", {})
    felony = _result_for(report, "convicted of a felony")
    assert felony["action"] == "needs_review"
    assert "Criminal-history question" in felony["detail"]
    assert not any("felony" in c.lower() for c in checked)


def test_a_saved_criminal_history_answer_is_used(browser):
    """Having written the answer down under Eligibility, the applicant
    shouldn't have to retype it on every application.
    """
    report, checked = _fill_with(browser, "screening.html", {"criminal_history": False})
    felony = _result_for(report, "convicted of a felony")
    assert felony["action"] == "filled"
    assert felony["canonical"] == "criminal_history"
    assert felony["detail"].strip().lower() == "no"

    # false is a real answer, and must not be read as "nothing saved".
    report, _ = _fill_with(browser, "screening.html", {"criminal_history": True})
    assert _result_for(report, "convicted of a felony")["detail"].strip().lower() == "yes"


def test_a_saved_answer_only_satisfies_its_own_kind_of_question(browser):
    """A criminal-history answer must never be used for a demographic
    question, or the other way round -- each gate opens only for a profile
    field that belongs to it.
    """
    stripped = {k: "" for k in (
        "gender", "pronouns", "hispanic_latino", "race_ethnicity",
        "veteran_status", "disability_status", "sexual_orientation",
        "transgender_status",
    )}
    # A criminal-history answer saved, every self-ID answer cleared.
    report, _ = _fill_with(browser, "eeo.html", {**stripped, "criminal_history": False})
    filled = [r for r in report["results"] if r["action"] == "filled"]
    assert [r["canonical"] for r in filled] == ["criminal_history"]
    assert filled[0]["detail"] == "No"  # not the raw "false"
    for r in report["results"]:
        if r["canonical"] != "criminal_history":
            assert r["action"] == "needs_review", r

    # And the other way round: self-ID answered, criminal history not.
    report, _ = _fill_with(browser, "eeo.html", {"criminal_history": ""})
    felony = _result_for(report, "convicted of a felony")
    assert felony["action"] == "needs_review"
    assert sum(1 for r in report["results"] if r["action"] == "filled") >= 4


def test_sms_consent_is_answered_only_when_saved(browser):
    report, _ = _fill_with(browser, "icims_profile.html", {"sms_consent": True})
    consent = _result_for(report, "consent to receive text")
    assert consent["action"] == "filled"
    assert consent["detail"] == "Yes"

    report, _ = _fill_with(browser, "icims_profile.html", {"sms_consent": False})
    assert _result_for(report, "consent to receive text")["detail"] == "No"


def test_self_id_and_criminal_history_never_leave_the_machine(browser):
    """Claude is never asked one of those questions -- they are answered from
    the applicant's own saved answer or not at all -- so there is no request
    that could need the data, and no reason to send it.
    """
    system = _llm_call_with_fields(browser, [
        {"ja_id": "ja-1", "label": "Tell us about yourself", "type": "textarea", "options": []},
    ])
    for field in ("gender", "pronouns", "hispanic_latino", "race_ethnicity",
                  "veteran_status", "disability_status", "sexual_orientation",
                  "transgender_status", "criminal_history"):
        assert f'"{field}"' not in system, field
    for value in (PROFILE["race_ethnicity"], PROFILE["veteran_status"],
                  PROFILE["disability_status"], PROFILE["sexual_orientation"]):
        assert value not in system, value

    # The rest of the profile is still the reference it works from.
    assert PROFILE["email"] in system
    assert PROFILE["experience"][0]["company"] in system
    assert PROFILE["education"][0]["school"] in system


def _evaluate_on(browser, fname, script, arg):
    """A fresh page per call. Two fillForm runs against one page would see the
    fields the first run already filled, which is not what any of these are
    testing.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, fname)}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        return page.evaluate(script, arg)
    finally:
        page.close()


def test_radio_questions_are_offered_but_consent_and_self_id_ones_are_not(browser):
    """A screening question asked as radio buttons is a question like any
    other; a consent or self-ID group asked the same way is still not.
    """
    offered = _llm_pass(browser, "ldg_form.html", {})["offered"]
    # Without radio support this form offers nothing at all.
    assert offered, "no radio question was offered"

    for eeo_form in ("eeo.html", "jazzhr_eeo.html", "cc305_form.html"):
        assert _llm_pass(browser, eeo_form, {})["offered"] == []

    joined = " | ".join(_llm_pass(browser, "screening.html", {})["offered"]).lower()
    for forbidden in ("felony", "convict", "background check", "drug"):
        assert forbidden not in joined, forbidden


def test_a_radio_answer_must_be_one_of_that_group_s_own_choices(browser):
    outcome = _evaluate_on(
        browser, "routing.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {answerSensitive: true});
            const offered = llmFieldsFor(report).find((f) => f.label.includes('shift'));
            const checked = () => document.querySelectorAll('input[name=shift]:checked').length;
            const invented = await applyLlmAnswers(
                report, {[offered.ja_id]: "Weekends only"}, {}, profile);
            const afterInvented = checked();
            const real = await applyLlmAnswers(
                report, {[offered.ja_id]: "Either"}, {}, profile);
            return {choices: offered.options, invented, afterInvented, real, afterReal: checked()};
        }""",
        PROFILE,
    )
    assert outcome["choices"] == ["Day", "Night", "Either"]
    # Text that is not one of the choices selects nothing at all.
    assert outcome["invented"] == 0
    assert outcome["afterInvented"] == 0
    assert outcome["real"] == 1
    assert outcome["afterReal"] == 1


def test_the_job_being_applied_for_is_sent_with_the_fields(browser):
    """Without it an answer to "why this role" can only be generic."""
    page = browser.new_page()
    try:
        page.goto("about:blank")
        page.add_script_tag(path=os.path.join(EXT_DIR, "llm.js"))
        sent = page.evaluate(
            """async ({profile, job}) => {
                let body = null;
                window.fetch = async (url, init) => {
                    body = JSON.parse(init.body);
                    return {ok: true, status: 200, text: async () => JSON.stringify({
                        content: [{type: "text", text: JSON.stringify({answers: []})}],
                        stop_reason: "end_turn",
                    })};
                };
                await resolveWithClaude({
                    apiKey: "k", profile, job, pageUrl: "https://x/apply",
                    fields: [{ja_id: "ja-1", label: "Why this role?",
                              type: "textarea", options: []}],
                });
                return {user: body.messages[0].content, system: body.system[0].text};
            }""",
            {"profile": PROFILE, "job": {
                "title": "Mechanical Engineering Intern",
                "company": "aerotech.com",
                "description": "Design and test motion control hardware.",
            }},
        )
    finally:
        page.close()

    assert "Mechanical Engineering Intern" in sent["user"]
    assert "motion control hardware" in sent["user"]
    # The job changes every application; keeping it out of the cached system
    # prefix is what stops it throwing the cache away on every request.
    assert "Mechanical Engineering Intern" not in sent["system"]


def test_a_saved_cover_letter_is_used_unless_tailoring_is_on(browser):
    script = """async ({profile, opts}) => {
        const report = await fillForm(profile, null, opts);
        const r = report.results.find((x) => x.canonical === 'cover_letter_text');
        return {action: r.action, detail: r.detail,
                offered: llmFieldsFor(report).some((f) => f.ja_id === r.ja_id)};
    }"""
    off = _evaluate_on(browser, "ldg_real.html", script, {"profile": PROFILE, "opts": {}})
    assert off["action"] == "filled"
    assert off["detail"] == PROFILE["cover_letter_text"]

    on = _evaluate_on(browser, "ldg_real.html", script,
                      {"profile": PROFILE, "opts": {"tailorCoverLetter": True}})
    assert on["action"] == "skipped_no_data"
    assert on["offered"] is True  # handed to Claude to write for this job


def test_learned_mappings_cover_a_label_the_aliases_do_not(browser):
    """The point of remembering one: the same odd wording resolves for free
    next time instead of costing another API call.
    """
    first = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const target = llmFieldsFor(report)[0];
            const answers = {[target.ja_id]: profile.city};
            await applyLlmAnswers(report, answers, {});
            return {label: target.label, learned: learnFromAnswers(report, answers, profile)};
        }""",
        PROFILE,
    )
    assert list(first["learned"].values()) == ["city"]

    # A later application, fresh page, same odd label.
    second = _evaluate_on(
        browser, "unknowns.html",
        """async ({profile, learned}) => {
            setLearnedAliases(learned);
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.canonical === 'city');
            const labels = llmFieldsFor(report).map((f) => f.label);
            return {action: r.action, detail: r.detail, label: r.label, stillOffered: labels};
        }""",
        {"profile": PROFILE, "learned": first["learned"]},
    )
    assert second["action"] == "filled"
    assert second["detail"] == PROFILE["city"]
    # That one label costs nothing now. The form's other unknowns still do.
    assert second["label"] == first["label"]
    assert first["label"] not in second["stillOffered"]


def test_only_mappings_are_learned_never_written_prose(browser):
    """A cover letter or an essay answer belongs to the job it was written
    for; remembering one would paste it into the next company's form.
    """
    learned = _evaluate_on(
        browser, "test_form.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const essay = llmFieldsFor(report).find((f) => f.type === 'textarea');
            const answers = {[essay.ja_id]:
                "I rebuilt the documentation pipeline at my last job."};
            await applyLlmAnswers(report, answers, {});
            return learnFromAnswers(report, answers, profile);
        }""",
        PROFILE,
    )
    assert learned == {}


def test_routing_off_leaves_every_radio_and_tick_box_alone(browser):
    """Without it, a self-ID group, a consent tick box and an ordinary
    screening radio the matcher doesn't know are all left for the applicant.
    """
    offered = _llm_pass(browser, "routing.html", {})["offered"]
    # An ordinary screening radio is fair game either way -- it is the
    # sensitive and consent ones that routing is the switch for.
    assert offered == ["Which shift are you available for?"]


def test_routing_on_offers_them_including_a_bland_headed_self_id_group(browser):
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'routing.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        offered = page.evaluate(
            """async (profile) => {
                const report = await fillForm(profile, null, {answerSensitive: true});
                return llmFieldsFor(report).map((f) => f.type + ': ' + f.label);
            }""",
            PROFILE,
        )
    finally:
        page.close()
    # The disability group isn't here: with disability_status saved, the
    # matcher answers it outright and there is nothing left to route.
    assert len(offered) == 3, offered
    assert any("shift" in o for o in offered)
    assert sum(1 for o in offered if o.startswith("checkbox:")) == 2


def test_a_sensitive_answer_must_trace_back_to_one_the_applicant_saved(browser):
    """Routing lets Claude work out which saved answer a question is asking
    for. It does not let it decide one -- so an answer that isn't the
    applicant's own is dropped before it reaches the page.
    """
    script = """async ({profile, answer}) => {
        const report = await fillForm(profile, null, {answerSensitive: true});
        const group = llmFieldsFor(report).find((f) => f.label.includes('check one of the boxes'));
        if (!group) return {offered: false, chosen: (document.querySelector(
            'input[name=dis]:checked') || {}).id || null};
        const applied = await applyLlmAnswers(report, {[group.ja_id]: answer}, {}, profile);
        const chosen = document.querySelector('input[name=dis]:checked');
        return {offered: true, applied, chosen: chosen ? chosen.id : null};
    }"""

    # With their answer saved, the matcher fills it outright -- nothing is
    # handed over at all, and the deterministic path chose correctly.
    out = _evaluate_on(browser, "routing.html", script, {
        "profile": PROFILE,
        "answer": "Yes, I have a disability, or have had one in the past",
    })
    assert out["offered"] is False
    assert out["chosen"] == "d2"  # their saved "No, I do not have a disability..."

    # Nothing saved: the question is handed over, but there is no answer of
    # theirs to route to it, so whatever comes back is dropped.
    for answer in ("No, I do not have a disability and have not had one in the past",
                   "Yes, I have a disability, or have had one in the past"):
        out = _evaluate_on(browser, "routing.html", script,
                           {"profile": {**PROFILE, "disability_status": ""}, "answer": answer})
        assert out["offered"] is True
        assert out["applied"] == 0
        assert out["chosen"] is None


def test_a_consent_box_is_ticked_only_from_a_consent_answer_that_was_set(browser):
    script = """async ({profile, answer}) => {
        const report = await fillForm(profile, null, {answerSensitive: true});
        const box = llmFieldsFor(report).find((f) => f.label.includes('certify'));
        const applied = box
            ? await applyLlmAnswers(report, {[box.ja_id]: answer}, {}, profile)
            : 0;
        return {offered: !!box, applied, ticked: document.getElementById('terms').checked};
    }"""

    # Nothing saved -- the default. The question is handed over, but there is
    # no consent of theirs to route to it, so nothing is agreed to.
    out = _evaluate_on(browser, "routing.html", script, {"profile": PROFILE, "answer": "Yes"})
    assert out["offered"] is True
    assert out["applied"] == 0
    assert out["ticked"] is False

    # Consenting to one thing is not consenting to another: a saved
    # background-check authorisation says nothing about certifying a form.
    out = _evaluate_on(browser, "routing.html", script, {
        "profile": {**PROFILE, "consent_background_check": True, "consent_drug_test": True},
        "answer": "Yes",
    })
    assert out["applied"] == 0
    assert out["ticked"] is False

    # Set to No on the Eligibility tab: still not a yes.
    out = _evaluate_on(browser, "routing.html", script,
                       {"profile": {**PROFILE, "consent_general": False}, "answer": "Yes"})
    assert out["applied"] == 0
    assert out["ticked"] is False

    # Set to Yes, so it is their standing answer -- and the matcher then
    # recognises the wording itself, with nothing left to hand over.
    out = _evaluate_on(browser, "routing.html", script,
                       {"profile": {**PROFILE, "consent_general": True}, "answer": "Yes"})
    assert out["offered"] is False
    assert out["ticked"] is True


def test_saved_answers_reach_the_prompt_only_when_routing_is_on(browser):
    page = browser.new_page()
    try:
        page.goto("about:blank")
        page.add_script_tag(path=os.path.join(EXT_DIR, "llm.js"))
        out = page.evaluate(
            """async (profile) => {
                const seen = [];
                window.fetch = async (url, init) => {
                    seen.push(JSON.parse(init.body));
                    return {ok: true, status: 200, text: async () => JSON.stringify({
                        content: [{type: "text", text: JSON.stringify({answers: []})}],
                        stop_reason: "end_turn",
                    })};
                };
                const call = (routeSavedAnswers) => resolveWithClaude({
                    apiKey: "k", profile, routeSavedAnswers, pageUrl: "https://x",
                    fields: [{ja_id: "ja-1", label: "Disability?", type: "radio", options: []}],
                });
                await call(false);
                await call(true);
                return seen.map((b) => b.system[0].text + "\\n" + b.messages[0].content);
            }""",
            PROFILE,
        )
    finally:
        page.close()

    off, on = out
    assert PROFILE["disability_status"] not in off
    assert PROFILE["veteran_status"] not in off
    assert PROFILE["disability_status"] in on
    # Still out of the cached system prefix either way.
    assert PROFILE["disability_status"] not in on.split("\n")[0]


def test_watching_the_applicant_type_remembers_the_answer(browser):
    """The source that needs no API call and no key: a field left blank gets
    filled by hand anyway, so notice what went in.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'routing.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        learned = page.evaluate(
            """async (profile) => {
                const report = await fillForm(profile, null, {});
                const seen = {};
                watchForCorrections(report, (m) => Object.assign(seen, m));

                // The applicant answers the shift question by hand.
                const night = document.getElementById('s2');
                night.checked = true;
                night.dispatchEvent(new Event('change', {bubbles: true}));
                return seen;
            }""",
            PROFILE,
        )
    finally:
        page.close()
    assert learned == {"which shift are you available for": "Night"}


def test_watching_never_picks_up_sensitive_consent_or_prose(browser):
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'routing.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        learned = page.evaluate(
            """async (profile) => {
                // Nothing saved for any of them, so all are left to the applicant.
                const bare = {...profile, disability_status: "", consent_general: "",
                              sms_consent: ""};
                const report = await fillForm(bare, null, {});
                const seen = {};
                watchForCorrections(report, (m) => Object.assign(seen, m));

                for (const id of ['d1', 'terms', 'sms']) {
                    const el = document.getElementById(id);
                    el.checked = true;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                return seen;
            }""",
            PROFILE,
        )
    finally:
        page.close()
    # A disability declaration, a certification and an SMS consent. None of
    # these is ever answered from a remembered value.
    assert learned == {}


def test_a_remembered_answer_fills_the_question_next_time(browser):
    """The whole point: the second form never asks."""
    first = _evaluate_on(
        browser, "routing.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const seen = {};
            watchForCorrections(report, (m) => Object.assign(seen, m));
            const el = document.getElementById('s3');
            el.checked = true;
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return seen;
        }""",
        PROFILE,
    )
    assert first == {"which shift are you available for": "Either"}

    second = _evaluate_on(
        browser, "routing.html",
        """async ({profile, remembered}) => {
            setLearnedAnswers(remembered);
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.label.includes('shift'));
            return {action: r.action, detail: r.detail, canonical: r.canonical,
                    checked: (document.querySelector('input[name=shift]:checked') || {}).id,
                    stillOffered: llmFieldsFor(report).map((f) => f.label)};
        }""",
        {"profile": PROFILE, "remembered": first},
    )
    assert second["action"] == "filled"
    assert second["canonical"] == "learned"
    assert second["checked"] == "s3"
    # Nothing left to pay Claude for on that question.
    assert "Which shift are you available for?" not in second["stillOffered"]


def test_claude_declaring_the_field_it_used_is_what_makes_a_label_learnable(browser):
    """Comparing the answer text alone never worked: "New York" offered as
    "NY" to fit a dropdown looks nothing like the saved value.
    """
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const target = llmFieldsFor(report)[0];
            const answers = {[target.ja_id]: "NY"};
            // Without the declaration, the reshaped value is unrecognisable.
            const blind = learnFromAnswers(report, answers, profile, {});
            // With it, the label is learned.
            const declared = learnFromAnswers(
                report, answers, profile, {[target.ja_id]: "state"});
            return {label: target.label, blind, declared};
        }""",
        PROFILE,
    )
    assert out["blind"] == {}
    assert list(out["declared"].values()) == ["state"]


def test_a_declared_field_must_actually_exist_and_never_be_prose(browser):
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const target = llmFieldsFor(report)[0];
            const answers = {[target.ja_id]: "something"};
            return {
                invented: learnFromAnswers(
                    report, answers, profile, {[target.ja_id]: "not_a_real_field"}),
                prose: learnFromAnswers(
                    report, answers, profile, {[target.ja_id]: "cover_letter_text"}),
                custom: learnFromAnswers(
                    report, answers, profile, {[target.ja_id]: "custom_answers"}),
            };
        }""",
        PROFILE,
    )
    assert out["invented"] == {}
    assert out["prose"] == {}
    assert out["custom"] == {}


def test_the_panel_lists_every_field_and_can_point_at_one(browser):
    """The panel exists so "what went wrong" is something you can click,
    rather than a number that vanishes after fifteen seconds.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'screening.html')}")
        for js in SCRIPT_FILES + ["panel.js"]:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                const report = await fillForm(profile, null, {});
                const panel = createPanel();
                panel.log("Found 20 fields.");
                panel.showThinking("Left the felony question alone.");
                panel.showResults(report);

                const root = document.getElementById('ja-autofill-panel').shadowRoot;
                const rows = Array.from(root.querySelectorAll('.field'));
                const headings = Array.from(root.querySelectorAll('h4')).map((h) => h.textContent);

                // Clicking a row should reach the real field on the page.
                rows.find((r) => r.textContent.includes('felony')).click();
                await new Promise((r) => setTimeout(r, 30));
                const flashed = Array.from(document.querySelectorAll('input'))
                    .filter((el) => el.style.boxShadow).length;

                return {rows: rows.length, headings, flashed,
                        thinking: root.querySelector('.thinking').textContent};
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["rows"] > 0
    assert any("Filled" in h for h in out["headings"])
    assert any("Left for you" in h for h in out["headings"])
    assert out["thinking"] == "Left the felony question alone."
    assert out["flashed"] >= 1


def test_the_panel_is_isolated_from_the_page_it_is_injected_into(browser):
    """It lands on whatever job site the applicant is on, and those pages
    have their own opinions about how a div and a button should look.
    """
    page = browser.new_page()
    try:
        page.set_content(
            "<style>div,button,textarea{display:none!important;color:red!important}</style><body>"
        )
        for js in SCRIPT_FILES + ["panel.js"]:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """() => {
                const panel = createPanel();
                panel.log("still here");
                const host = document.getElementById('ja-autofill-panel');
                const wrap = host.shadowRoot.querySelector('.wrap');
                return {display: getComputedStyle(wrap).display,
                        text: host.shadowRoot.querySelector('.line').textContent};
            }"""
        )
    finally:
        page.close()
    # The page's blanket `display:none` on every div does not reach inside.
    assert out["display"] == "flex"
    assert "still here" in out["text"]


def test_the_chat_can_only_change_fields_the_fill_would_have(browser):
    """Its answers go through the same guarded path, so nothing it returns
    reaches a consent box or a self-identification question.
    """
    out = _evaluate_on(
        browser, "routing.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const shift = llmFieldsFor(report).find((f) => f.label.includes('shift'));
            const consentBox = (report.fields || []).find(
                (f) => (f.label || '').includes('certify'));
            // A reply that tries to set an allowed field and a consent box.
            const changed = await applyLlmAnswers(report, {
                [shift.ja_id]: "Either",
                [consentBox.ja_id]: "Yes",
            }, {}, profile);
            return {changed, ticked: document.getElementById('terms').checked,
                    shiftChosen: (document.querySelector('input[name=shift]:checked') || {}).id};
        }""",
        PROFILE,
    )
    assert out["changed"] == 1
    assert out["shiftChosen"] == "s3"
    assert out["ticked"] is False


def test_a_value_the_page_clears_is_not_reported_as_filled(browser):
    """Setting a value and it staying set are different claims. A framework
    that reverts one on its next render would otherwise leave the report
    saying filled while the box sits empty -- the worst kind of wrong,
    because it reads as done.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'test_form.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                const report = await fillForm(profile, null, {});
                const before = report.results.find(
                    (r) => r.canonical === 'email' && r.action === 'filled');

                // A form that wipes the field back out, the way a controlled
                // React input does when it re-renders from its own state.
                const el = document.querySelector(`[data-ja-id="${before.ja_id}"]`);
                Object.defineProperty(el, 'value', {
                    get: () => '', set: () => {}, configurable: true,
                });

                const lost = await verifyFilled(report, 0);
                const after = report.results.find((r) => r.ja_id === before.ja_id);
                return {lost, action: after.action, detail: after.detail};
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["lost"] == [out["lost"][0]]
    assert out["action"] == "needs_review"
    assert "cleared it" in out["detail"]


def test_a_deliberate_blank_is_not_mistaken_for_a_lost_value(browser):
    """An ongoing job's end date is filled by being left empty, on purpose.
    Verification must not flag its own correct outcome.
    """
    out = _evaluate_on(
        browser, "experience_repeater.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const lost = await verifyFilled(report, 0);
            // Two results share this canonical: the date box left empty on
            // purpose, and the "I currently work here" box that says why.
            const endDate = report.results.find(
                (r) => r.canonical === 'experience_end_date' && /Left blank/.test(r.detail));
            return {lost, action: endDate.action, detail: endDate.detail};
        }""",
        PROFILE,
    )
    assert out["lost"] == []
    assert out["action"] == "filled"
    assert "Left blank" in out["detail"]


def test_what_a_form_could_not_answer_is_recorded(browser):
    """One form's gaps are an anecdote; the same label coming back unfilled
    across thirty applications is the thing worth fixing.
    """
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            return missedFields(report);
        }""",
        PROFILE,
    )
    labels = [m["label"] for m in out]
    assert "What is your spirit animal?" in labels
    # Every entry carries what it needs to be counted and acted on later.
    for m in out:
        assert m["key"] and m["action"] and "type" in m


def test_the_docx_reader_gets_the_text_out(browser):
    """The applicant's resume is a .docx, and a Word file is a ZIP whose
    word/document.xml holds the text -- readable here without a library
    because Chrome can inflate a raw deflate stream itself.
    """
    with open(os.path.join(FIXTURES_DIR, "sample_resume.docx"), "rb") as f:
        import base64
        b64 = base64.b64encode(f.read()).decode()

    page = browser.new_page()
    try:
        page.goto("about:blank")
        # docxText is defined in options.js, which expects the options page's
        # DOM; the two functions under test are self-contained, so take them
        # rather than loading the whole page.
        source = open(os.path.join(EXT_DIR, "options.js"), encoding="utf-8").read()
        start = source.index("function dataUrlToBytes")
        end = source.index("async function resumeForParsing")
        page.add_script_tag(content=source[start:end])
        text = page.evaluate(
            "(b64) => docxText(dataUrlToBytes('data:application/octet-stream;base64,' + b64))",
            b64,
        )
    finally:
        page.close()

    assert "Jamie Rivera" in text
    assert "Test Engineer at Test Industries" in text
    # XML entities come back as the characters they stand for.
    assert "State University & Co" in text


def test_it_learns_from_another_extension_filling_the_same_form(browser):
    """Running this first and a second autofill extension after it: the
    fields left blank here are exactly the ones being watched, and any tool
    filling one has to dispatch input/change or React forms would never see
    the value. So what the other tool knows ends up remembered here.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'unknowns.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                const report = await fillForm(profile, null, {});
                const seen = {};
                watchForCorrections(report, (m) => Object.assign(seen, m));

                // Stand in for another extension: set the value through the
                // native setter and dispatch, which is what any of them must
                // do for a framework-controlled input to register it.
                const fillLike = (id, value, events) => {
                    const el = document.getElementById(id);
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, value);
                    for (const type of events) {
                        el.dispatchEvent(new Event(type, {bubbles: true}));
                    }
                };

                fillLike('q2', 'A peregrine falcon', ['input', 'change']);
                // A tool that only dispatches input, never change.
                fillLike('q4', 'Available from May 2027', ['input']);
                await new Promise((r) => setTimeout(r, 900));
                return seen;
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["what is your spirit animal"] == "A peregrine falcon"
    assert out["anything else we should know"] == "Available from May 2027"


def test_a_yes_no_answer_is_never_learned_as_a_self_id_field(browser):
    """The bug this exists to stop: "No" appears verbatim in several profile
    fields at once, so matching an answer's text against them picked
    whichever came first -- and every yes/no question on every form ended up
    learned as hispanic_latino. Worse than a messy list: a learned alias is
    consulted before anything else in matchField, so those labels would then
    pull a self-identification answer into an ordinary field, with the
    sensitive gate never firing because "Did you graduate?" isn't sensitive.
    """
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const target = llmFieldsFor(report)[0];
            return {
                // Short, ambiguous: several profile fields say "No".
                shortAnswer: learnFromAnswers(report, {[target.ja_id]: "No"}, profile, {}),
                // Even declared outright, a sensitive field is refused.
                declaredSensitive: learnFromAnswers(
                    report, {[target.ja_id]: "No"}, profile,
                    {[target.ja_id]: "hispanic_latino"}),
                declaredConsent: learnFromAnswers(
                    report, {[target.ja_id]: "Yes"}, profile,
                    {[target.ja_id]: "consent_background_check"}),
                // Long and unique to one field: still learnable.
                distinctive: learnFromAnswers(
                    report, {[target.ja_id]: profile.portfolio_url}, profile, {}),
            };
        }""",
        PROFILE,
    )
    assert out["shortAnswer"] == {}
    assert out["declaredSensitive"] == {}
    assert out["declaredConsent"] == {}
    assert list(out["distinctive"].values()) == ["portfolio_url"]


def test_mappings_learned_before_these_rules_are_dropped_on_load(browser):
    """An existing store already holds them, so they have to be cleaned up
    rather than merely stopped from growing.
    """
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const polluted = {
                "did you graduate": "hispanic_latino",
                "are you willing to relocate": "transgender_status",
                "consent to a check": "consent_drug_test",
                "made up field": "not_a_real_profile_key",
                "personal website": "portfolio_url",
            };
            const clean = sanitizeLearnedAliases(polluted, profile);

            // And with the polluted map still in force, an ordinary question
            // must not pull a self-identification answer.
            setLearnedAliases(polluted);
            const bad = matchField("Did you graduate");
            setLearnedAliases(clean);
            const good = matchField("Did you graduate");
            return {clean, bad, good};
        }""",
        PROFILE,
    )
    assert out["clean"] == {"personal website": "portfolio_url"}
    assert out["bad"] == "hispanic_latino"   # what the bug did
    assert out["good"] is None               # what it does once cleaned


def test_it_learns_from_fields_that_were_already_filled(browser):
    """So the order stops mattering. Run another autofill extension first and
    what it knew is sitting on the page when this one arrives -- it was being
    stepped over in silence.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'unknowns.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                // Another tool got here first.
                document.getElementById('q2').value = 'A peregrine falcon';
                // And a field the matcher knows, that the profile is missing.
                const bare = {...profile, portfolio_url: ""};

                const report = await fillForm(bare, null, {});
                const learned = learnFromPrefilled(report, bare);
                return {
                    learned,
                    alreadyFilled: report.results.filter(
                        (r) => r.action === 'already_filled').length,
                };
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["alreadyFilled"] >= 1
    assert out["learned"]["answers"]["what is your spirit animal"] == "A peregrine falcon"


def test_a_page_value_for_a_missing_profile_field_is_suggested_not_saved(browser):
    """A page can hold a default nobody chose or someone else's value, so
    this is identity data to be offered, never written on its own.
    """
    out = _evaluate_on(
        browser, "test_form.html",
        """async (profile) => {
            const bare = {...profile, linkedin_url: ""};
            const report = await fillForm(bare, null, {});
            const first = learnFromPrefilled(report, bare);

            // Same page, but the profile already has an answer: nothing to
            // suggest, and the page's value must not override it.
            document.querySelectorAll('[data-ja-id]').forEach((el) => {
                el.removeAttribute('data-ja-id');
            });
            const second = await fillForm(profile, null, {});
            return {
                suggestedWhenMissing: first.suggestions,
                suggestedWhenSet: learnFromPrefilled(second, profile).suggestions,
            };
        }""",
        PROFILE,
    )
    # Nothing sensitive, and nothing already answered, ever appears here.
    for field in out["suggestedWhenMissing"]:
        assert field not in ("gender", "race_ethnicity", "veteran_status",
                             "disability_status", "criminal_history")
    assert "linkedin_url" not in out["suggestedWhenSet"]


def test_prefilled_sensitive_answers_never_become_label_keyed_answers(browser):
    """They are kept, but only ever as the profile field for that question.
    A label-keyed answer is consulted before every check, so one holding a
    disability declaration would pour it into any field carrying that label.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'routing.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                document.getElementById('terms').checked = true;
                document.getElementById('sms').checked = true;
                document.getElementById('d1').checked = true;
                const bare = {...profile, disability_status: "", consent_general: "",
                              sms_consent: ""};
                const report = await fillForm(bare, null, {});
                return learnFromPrefilled(report, bare);
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["answers"] == {}
    assert set(out["suggestions"]) <= {"disability_status", "consent_general", "sms_consent"}


def test_a_yes_no_answer_is_never_learned_as_a_self_id_field(browser):
    """The bug this exists to stop: "No" appears verbatim in several profile
    fields at once, so matching an answer's text against them picked
    whichever came first -- and every yes/no question on every form ended up
    learned as hispanic_latino. Worse than a messy list: a learned alias is
    consulted before anything else in matchField, so those labels would then
    pull a self-identification answer into an ordinary field, with the
    sensitive gate never firing because "Did you graduate?" isn't sensitive.
    """
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const target = llmFieldsFor(report)[0];
            return {
                // Short, ambiguous: several profile fields say "No".
                shortAnswer: learnFromAnswers(report, {[target.ja_id]: "No"}, profile, {}),
                // Even declared outright, a sensitive field is refused.
                declaredSensitive: learnFromAnswers(
                    report, {[target.ja_id]: "No"}, profile,
                    {[target.ja_id]: "hispanic_latino"}),
                declaredConsent: learnFromAnswers(
                    report, {[target.ja_id]: "Yes"}, profile,
                    {[target.ja_id]: "consent_background_check"}),
                // Long and unique to one field: still learnable.
                distinctive: learnFromAnswers(
                    report, {[target.ja_id]: profile.portfolio_url}, profile, {}),
            };
        }""",
        PROFILE,
    )
    assert out["shortAnswer"] == {}
    assert out["declaredSensitive"] == {}
    assert out["declaredConsent"] == {}
    assert list(out["distinctive"].values()) == ["portfolio_url"]


def test_mappings_learned_before_these_rules_are_dropped_on_load(browser):
    """An existing store already holds them, so they have to be cleaned up
    rather than merely stopped from growing.
    """
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            const polluted = {
                "did you graduate": "hispanic_latino",
                "are you willing to relocate": "transgender_status",
                "consent to a check": "consent_drug_test",
                "made up field": "not_a_real_profile_key",
                "personal website": "portfolio_url",
            };
            const clean = sanitizeLearnedAliases(polluted, profile);

            // And with the polluted map still in force, an ordinary question
            // must not pull a self-identification answer.
            setLearnedAliases(polluted);
            const bad = matchField("Did you graduate");
            setLearnedAliases(clean);
            const good = matchField("Did you graduate");
            return {clean, bad, good};
        }""",
        PROFILE,
    )
    assert out["clean"] == {"personal website": "portfolio_url"}
    assert out["bad"] == "hispanic_latino"   # what the bug did
    assert out["good"] is None               # what it does once cleaned


def test_it_learns_from_fields_that_were_already_filled(browser):
    """So the order stops mattering. Run another autofill extension first and
    what it knew is sitting on the page when this one arrives -- it was being
    stepped over in silence.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'unknowns.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                // Another tool got here first.
                document.getElementById('q2').value = 'A peregrine falcon';
                // And a field the matcher knows, that the profile is missing.
                const bare = {...profile, portfolio_url: ""};

                const report = await fillForm(bare, null, {});
                const learned = learnFromPrefilled(report, bare);
                return {
                    learned,
                    alreadyFilled: report.results.filter(
                        (r) => r.action === 'already_filled').length,
                };
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["alreadyFilled"] >= 1
    assert out["learned"]["answers"]["what is your spirit animal"] == "A peregrine falcon"


def test_a_page_value_for_a_missing_profile_field_is_suggested_not_saved(browser):
    """A page can hold a default nobody chose or someone else's value, so
    this is identity data to be offered, never written on its own.
    """
    out = _evaluate_on(
        browser, "test_form.html",
        """async (profile) => {
            const bare = {...profile, linkedin_url: ""};
            const report = await fillForm(bare, null, {});
            const first = learnFromPrefilled(report, bare);

            // Same page, but the profile already has an answer: nothing to
            // suggest, and the page's value must not override it.
            document.querySelectorAll('[data-ja-id]').forEach((el) => {
                el.removeAttribute('data-ja-id');
            });
            const second = await fillForm(profile, null, {});
            return {
                suggestedWhenMissing: first.suggestions,
                suggestedWhenSet: learnFromPrefilled(second, profile).suggestions,
            };
        }""",
        PROFILE,
    )
    # Nothing sensitive, and nothing already answered, ever appears here.
    for field in out["suggestedWhenMissing"]:
        assert field not in ("gender", "race_ethnicity", "veteran_status",
                             "disability_status", "criminal_history")
    assert "linkedin_url" not in out["suggestedWhenSet"]


def test_a_sensitive_answer_on_the_page_is_offered_for_the_profile(browser):
    """Answering a self-ID or consent question by hand is the applicant
    stating their own answer, and it was being thrown away. It is kept -- as
    the profile field for that question, so the gate that reads what is
    actually being asked still applies to it every time.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'routing.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                document.getElementById('d2').checked = true;   // disability: No
                document.getElementById('terms').checked = true; // certification
                document.getElementById('sms').checked = true;   // SMS consent
                const bare = {...profile, disability_status: "", consent_general: "",
                              sms_consent: ""};
                const report = await fillForm(bare, null, {});
                return learnFromPrefilled(report, bare);
            }""",
            PROFILE,
        )
    finally:
        page.close()

    # Kept as profile fields, never as label-keyed answers -- a label-keyed
    # one is consulted before every check and would pour a declaration into
    # any field carrying that label.
    assert out["answers"] == {}
    assert out["suggestions"]["consent_general"] == "Yes"
    assert out["suggestions"]["sms_consent"] == "Yes"
    assert "not have a disability" in out["suggestions"]["disability_status"]


def test_a_sensitive_answer_typed_by_hand_is_captured_too(browser):
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'routing.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                const bare = {...profile, disability_status: "", consent_general: ""};
                const report = await fillForm(bare, null, {});
                const learned = {}, suggested = {};
                watchForCorrections(report,
                    (m) => Object.assign(learned, m),
                    (m) => Object.assign(suggested, m));

                for (const id of ['d3', 'terms']) {
                    const el = document.getElementById(id);
                    el.checked = true;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                return {learned, suggested};
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["learned"] == {}
    assert "do not want to answer" in out["suggested"]["disability_status"]
    assert out["suggested"]["consent_general"] == "Yes"


def test_a_sensitive_answer_already_in_the_profile_is_not_re_suggested(browser):
    """Their saved answer is the one that counts; a page's version of it is
    not a correction to be offered back.
    """
    out = _evaluate_on(
        browser, "routing.html",
        """async (profile) => {
            document.getElementById('d1').checked = true;  // page says "Yes"
            const report = await fillForm(profile, null, {});  // profile says "No"
            return learnFromPrefilled(report, profile).suggestions;
        }""",
        PROFILE,
    )
    assert "disability_status" not in out


def test_an_unset_profile_yes_no_does_not_untick_a_box_you_ticked(browser):
    """"Not set" is not an answer of no. Read as one, a blank profile field
    reaches out and unticks a consent box the applicant ticked themselves --
    and reports it as filled.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'routing.html')}")
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                document.getElementById('terms').checked = true;
                const report = await fillForm(
                    {...profile, consent_general: ""}, null, {});
                const r = report.results.find((x) => x.canonical === 'consent_general');
                return {stillTicked: document.getElementById('terms').checked,
                        action: r.action};
            }""",
            PROFILE,
        )
    finally:
        page.close()

    assert out["stillTicked"] is True
    assert out["action"] == "skipped_no_data"


# --- The RTX/Workday form the applicant had already filled in once ---------

REMEMBERED_RTX = {
    "did you previously work for rtx including its predecessors or any of its "
    "businesses in any capacity": "No",
    "are you a current u s federal government civilian or military active duty "
    "or reserves employee": "No",
    "are you a former u s federal government civilian or military active duty "
    "or reserves employee": "No",
}


def test_a_remembered_answer_reaches_a_workday_listbox(browser):
    """Workday's questions are <button aria-haspopup="listbox"> with no options
    in the DOM until the button is clicked, so f.options is empty at extraction
    time. The remembered-answer path read that empty list instead of opening
    the widget, and reported every question answered on an earlier application
    as "Remembered 'No', but no option matched it".
    """
    out = _evaluate_on(
        browser, "workday_remembered.html",
        """async ({profile, remembered}) => {
            setLearnedAnswers(remembered);
            const report = await fillForm(profile, null, {});
            return {
                answers: Object.fromEntries(
                    Array.from(document.querySelectorAll('button[aria-haspopup="listbox"]'))
                         .map((b) => [b.name, b.textContent.trim()])),
                results: report.results
                    .filter((r) => r.detail && r.detail.includes('no option matched'))
                    .map((r) => r.label),
                stillOpen: document.querySelectorAll('[role="listbox"]').length,
            };
        }""",
        {"profile": PROFILE, "remembered": REMEMBERED_RTX},
    )

    assert out["answers"]["q1"] == "No"
    assert out["answers"]["q2"] == "No"
    assert out["answers"]["q3"] == "No"
    assert out["results"] == [], out["results"]
    # Nothing may be left hanging open over the rest of the form.
    assert out["stillOpen"] == 0


def test_a_work_authorisation_question_is_not_a_self_identification_question(browser):
    """8 U.S.C. 1324b calls a work-authorised applicant a "protected
    individual", so RTX's "Are you a U.S. Person?" -- a work-authorisation
    question wrapped in the statutory definition -- matched the sensitive
    gate's "protected" keyword and was flagged as self-identification on every
    form, with no answer the applicant could save that would ever fill it.
    """
    out = _evaluate_on(
        browser, "workday_remembered.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.label.includes('U.S. Person'));
            return {found: !!r, detail: r ? r.detail : null};
        }""",
        PROFILE,
    )

    assert out["found"], "the U.S. Person question was not reported at all"
    assert "Self-identification" not in (out["detail"] or ""), out["detail"]


def test_real_self_identification_wording_is_still_caught(browser):
    """The guard above narrows what counts as a self-ID question, so this is
    the other half of it: the wording that genuinely is one still is. Asserts
    the fixture offered these at all first -- an empty report would pass the
    absence check above trivially.
    """
    blank = {**PROFILE}
    for k in ("gender", "pronouns", "hispanic_latino", "race_ethnicity",
              "veteran_status", "disability_status"):
        blank[k] = ""

    out = _evaluate_on(
        browser, "eeo.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            return report.results
                .filter((r) => r.detail && r.detail.includes('Self-identification'))
                .map((r) => r.label);
        }""",
        blank,
    )

    assert len(out) >= 3, f"the EEO fixture flagged almost nothing: {out}"


def test_the_phone_number_never_goes_into_a_phone_extension_box(browser):
    """"phone" is a whole word inside "Phone Extension", so the alias matched
    and the full number went into the extension box -- on three Workday
    tenants, each of which then cleared it. An extension is not part of a
    phone number and is not on the profile: there is nothing to put here.
    """
    out = _evaluate_on(
        browser, "workday_remembered.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const ext = document.getElementById('phone-ext');
            return {
                extValue: ext.value,
                phoneValue: document.getElementById('phone-number').value,
                extResult: (report.results.find((r) => r.label.includes('Extension')) || {}).action,
            };
        }""",
        PROFILE,
    )

    assert out["extValue"] == "", f"phone extension got {out['extValue']!r}"
    # The real phone box still fills -- the guard is not a blanket phone block.
    assert out["phoneValue"] != ""
    assert out["extResult"] != "filled"


# --- "Learn this form" -----------------------------------------------------

def test_learning_a_form_remembers_what_was_typed_into_it(browser):
    """The form that comes round again: fill it in by hand once, press Learn,
    and the next one like it fills itself. watch-and-learn does not cover
    this -- it only watches what was left blank, and never sees an answer
    entered before the panel opened or one the applicant corrected.
    """
    out = _evaluate_on(
        browser, "unknowns.html",
        """async (profile) => {
            // The applicant fills it in themselves.
            const typed = {q2: 'Octopus', q4: 'Available from June.'};
            for (const [id, v] of Object.entries(typed)) {
                const el = document.getElementById(id);
                el.value = v;
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            const learned = learnFromPage(profile);
            // Nothing may be written to the page by learning it.
            return {
                answers: learned.answers,
                stillTyped: document.getElementById('q2').value,
                firstNameUntouched: document.getElementById('fn').value,
            };
        }""",
        PROFILE,
    )

    assert out["answers"].get("what is your spirit animal") == "Octopus"
    assert out["answers"].get("anything else we should know") == "Available from June."
    assert out["stillTyped"] == "Octopus"
    assert out["firstNameUntouched"] == ""


def test_learning_a_form_never_puts_a_self_id_answer_in_the_label_store(browser):
    """The safety property, on the new path. A label-keyed answer is consulted
    before every other check, so one holding a disability or veteran
    declaration would pour it into any field carrying that label. These go to
    the profile-suggestion store instead, which is not written automatically.
    """
    blank = {**PROFILE}
    for k in ("gender", "pronouns", "hispanic_latino", "race_ethnicity",
              "veteran_status", "disability_status"):
        blank[k] = ""

    out = _evaluate_on(
        browser, "eeo.html",
        """async (profile) => {
            const gender = document.getElementById('g');
            gender.selectedIndex = 1;
            gender.dispatchEvent(new Event('change', {bubbles: true}));
            const vet = document.getElementById('v1');
            vet.checked = true;
            vet.dispatchEvent(new Event('change', {bubbles: true}));
            const learned = learnFromPage(profile);
            return {answers: learned.answers, suggestions: learned.suggestions,
                    genderText: gender.options[gender.selectedIndex].text};
        }""",
        blank,
    )

    # Asserted non-empty first: an empty result would pass the absence check
    # below for the wrong reason.
    assert out["suggestions"], f"learned nothing at all: {out}"
    assert out["suggestions"].get("gender") == out["genderText"]
    assert out["suggestions"].get("veteran_status") == "I am not a protected veteran"

    joined = " ".join(out["answers"].keys()).lower()
    assert "gender" not in joined, out["answers"]
    assert "veteran" not in joined, out["answers"]


def test_a_field_the_applicant_hasnt_got_is_not_a_gap(browser):
    """An empty profile field is normally a gap worth filling, which is why
    the Gaps tab counts one. A middle name the applicant does not have is not
    a gap -- blank is the answer -- and counting it put 18 occurrences of two
    such fields at the top of a 250-occurrence list.
    """
    no_middle = {**PROFILE, "middle_name": ""}

    out = _evaluate_on(
        browser, "icims.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.canonical === 'middle_name');
            return {
                found: !!r,
                action: r ? r.action : null,
                detail: r ? r.detail : null,
                box: (document.getElementById('PersonProfileFields.MiddleName') || {}).value,
                counted: missedFields(report).map((m) => m.label),
            };
        }""",
        no_middle,
    )

    assert out["found"], "the middle name field was not reported at all"
    assert out["box"] == "", f"something was typed into it: {out['box']!r}"
    # Not outstanding, and not counted against the next thing worth fixing.
    assert out["action"] != "skipped_no_data"
    assert not any("middle" in m.lower() for m in out["counted"]), out["counted"]


def test_a_field_that_is_merely_empty_is_still_a_gap(browser):
    """The other half: the counting still works for everything else, or the
    check above passes because nothing is ever counted.
    """
    out = _evaluate_on(
        browser, "icims.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            return missedFields(report).length;
        }""",
        {**PROFILE, "middle_name": ""},
    )

    assert out > 0


def test_the_panel_offers_autofill_and_learn_as_separate_presses(browser):
    """Running alongside another autofill extension, filling on arrival is the
    wrong default: both tools listen for the same change events and overwrite
    each other. The panel has to be able to open having touched nothing, and
    let the applicant say which of the two things they want on this form.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'screening.html')}")
        for js in SCRIPT_FILES + ["panel.js"]:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async () => {
                const panel = createPanel();
                const pressed = [];
                panel.onFill(async () => { pressed.push('fill'); });
                panel.onLearn(async () => { pressed.push('learn'); return 'done'; });

                const root = document.getElementById('ja-autofill-panel').shadowRoot;
                const fill = root.querySelector('button.fill');
                const learn = root.querySelector('button.learn');
                const labels = {fillText: fill.textContent, learnText: learn.textContent};

                // Each handler is async and relabels its button while it runs,
                // so let both settle before reading anything back.
                fill.click();
                await new Promise((r) => setTimeout(r, 50));
                learn.click();
                await new Promise((r) => setTimeout(r, 50));

                return {
                    ...labels,
                    hasBoth: !!fill && !!learn,
                    // Back to their resting labels, not stuck on "Filling...".
                    fillAfter: fill.textContent,
                    learnAfter: learn.textContent,
                    enabledAfter: !fill.disabled && !learn.disabled,
                    pressed,
                };
            }"""
        )
    finally:
        page.close()

    assert out["hasBoth"]
    assert out["fillText"] == "Autofill"
    assert out["learnText"] == "Learn this form"
    assert out["pressed"] == ["fill", "learn"]
    assert out["fillAfter"] == "Autofill"
    assert out["learnAfter"] == "Learn this form"
    assert out["enabledAfter"]


def test_the_fill_is_a_function_the_button_can_call_rather_than_the_script_body():
    """run.js is not loaded by the browser fixtures, so this is a static check
    of the shape the buttons depend on: the fill has to be callable more than
    once, and the things that read its report have to tolerate it not having
    run at all.
    """
    src = open(os.path.join(EXT_DIR, "run.js"), encoding="utf-8").read()

    assert "async function doFill()" in src
    assert "panel?.onFill(doFill)" in src
    # Manual mode leaves report null; both readers have to be guarded.
    assert src.count("if (report && (!settings || settings.watch_and_learn !== false))") == 2
    assert "let report = null;" in src


def test_the_panel_can_be_dragged_off_the_submit_button(browser):
    """It is injected over someone else's form, and where it lands is often
    exactly where the submit button is. Dragging it by the header moves it;
    the header's own buttons stay buttons rather than becoming a grab handle.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'screening.html')}")
        for js in SCRIPT_FILES + ["panel.js"]:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """() => {
                const panel = createPanel();
                const root = document.getElementById('ja-autofill-panel').shadowRoot;
                const wrap = root.querySelector('.wrap');
                const head = root.querySelector('header');

                const drag = (fromX, fromY, toX, toY, target) => {
                    (target || head).dispatchEvent(new PointerEvent('pointerdown', {
                        clientX: fromX, clientY: fromY, bubbles: true, composed: true}));
                    window.dispatchEvent(new PointerEvent('pointermove', {
                        clientX: toX, clientY: toY, bubbles: true}));
                    window.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                };

                const before = wrap.getBoundingClientRect();
                drag(before.left + 40, before.top + 10, 300, 400);
                const afterDrag = wrap.getBoundingClientRect();

                // Pressing a header button must not drag the panel with it.
                const parked = wrap.getBoundingClientRect();
                drag(parked.left + 6, parked.top + 10, 900, 20,
                     root.querySelector('button.learn'));
                const afterButton = wrap.getBoundingClientRect();

                // Hurled far off-screen, a corner has to stay reachable.
                drag(afterButton.left + 40, afterButton.top + 10, -5000, -5000);
                const afterYeet = wrap.getBoundingClientRect();

                return {
                    movedX: Math.round(afterDrag.left), movedY: Math.round(afterDrag.top),
                    startedRight: Math.round(before.left),
                    buttonMovedTo: Math.round(afterButton.left),
                    parkedAt: Math.round(parked.left),
                    yeetX: Math.round(afterYeet.left), yeetY: Math.round(afterYeet.top),
                    width: Math.round(afterYeet.width),
                    viewport: {w: window.innerWidth, h: window.innerHeight},
                };
            }"""
        )
    finally:
        page.close()

    # It actually moved, and to roughly where it was dragged.
    assert out["movedX"] != out["startedRight"]
    assert abs(out["movedX"] - 260) <= 2, out
    assert abs(out["movedY"] - 390) <= 2, out
    # The button press left it where it was.
    assert out["buttonMovedTo"] == out["parkedAt"], out
    # Still grabbable after being thrown at the top-left corner.
    assert out["yeetX"] + out["width"] >= 64, out
    assert out["yeetY"] >= 0, out


def test_the_panel_does_not_run_the_full_height_of_the_window(browser):
    """A full-height right rail covers whatever the page has down that side,
    which on an application form is usually the submit button.
    """
    page = browser.new_page()
    try:
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'screening.html')}")
        for js in SCRIPT_FILES + ["panel.js"]:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """async (profile) => {
                const report = await fillForm(profile, null, {});
                const panel = createPanel();
                panel.showResults(report);
                const wrap = document.getElementById('ja-autofill-panel')
                    .shadowRoot.querySelector('.wrap');
                const box = wrap.getBoundingClientRect();
                return {height: box.height, width: box.width, viewportH: window.innerHeight};
            }""",
            PROFILE,
        )
    finally:
        page.close()

    # Leaves room below it even with a full report showing.
    assert out["height"] < out["viewportH"] * 0.92, out
    assert out["width"] <= 320, out


# --- Workday's race/ethnicity wording --------------------------------------

WORKDAY_ETHNICITY = [
    ("Asian", "Asian (Not Hispanic or Latino) (United States of America)"),
    ("White", "White (Not Hispanic or Latino) (United States of America)"),
    ("Black or African American",
     "Black or African American (Not Hispanic or Latino) (United States of America)"),
    ("Hispanic or Latino", "Hispanic or Latino (United States of America)"),
    ("Two or More Races",
     "Two or More Races (Not Hispanic or Latino) (United States of America)"),
    ("Decline to self-identify",
     "I do not wish to self-identify my ethnicity (United States of America)"),
]


@pytest.mark.parametrize("saved,expected", WORKDAY_ETHNICITY)
def test_a_saved_race_reaches_workdays_own_wording_for_it(browser, saved, expected):
    """The answer was in the profile the whole time. bestOption scores
    "Asian (Not Hispanic or Latino) (United States of America)" at 0.42
    against a saved "Asian", under its 0.5 bar, so the question came back
    required-and-blank on every Workday form -- and loosening that bar is the
    wrong fix, because every non-Hispanic choice contains the string
    "hispanic or latino" and a containment bonus picks the negation.
    """
    out = _evaluate_on(
        browser, "workday_ethnicity.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.canonical === 'race_ethnicity');
            return {
                action: r ? r.action : null,
                detail: r ? r.detail : null,
                button: document.querySelector('button[aria-haspopup="listbox"]').textContent.trim(),
                stillOpen: document.querySelectorAll('[role="listbox"]').length,
            };
        }""",
        {**PROFILE, "race_ethnicity": saved},
    )

    assert out["action"] == "filled", out
    assert out["button"] == expected, out
    assert out["stillOpen"] == 0


def test_an_unset_race_is_still_left_for_the_applicant(browser):
    """The gate does not move: nothing is inferred, and unset stays flagged.
    Without this the check above could be passing because the matcher got
    loose rather than because it got right.
    """
    out = _evaluate_on(
        browser, "workday_ethnicity.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results[0];
            return {action: r.action, detail: r.detail,
                    button: document.querySelector('button[aria-haspopup="listbox"]').textContent.trim()};
        }""",
        {**PROFILE, "race_ethnicity": ""},
    )

    assert out["action"] == "needs_review"
    assert "Self-identification" in out["detail"]
    assert out["button"] == "Select One"


# --- A campus screening questionnaire --------------------------------------

def test_a_question_asking_how_many_is_not_answered_from_a_noun_it_mentions(browser):
    """"How many credit hours towards your degree...?" put the applicant's
    "B.S." in a box asking for a number, because the label contains the word
    "degree". Refusing the alias alone moved the wrong answer along rather
    than stopping it: it fuzzy-matched gpa next, and then the machine-name
    fallback matched gpa again off the field id, which carries the
    questionnaire's name ("Campus - GPA Not Required - Clearance - 2025").
    """
    out = _evaluate_on(
        browser, "campus_questionnaire.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.label.includes('credit hours'));
            return {action: r.action, canonical: r.canonical, detail: r.detail,
                    box: document.querySelector('textarea').value};
        }""",
        {**PROFILE, "gpa": "3.7"},
    )

    assert out["action"] != "filled", out
    assert out["canonical"] is None, out
    assert out["box"] == "", f"something was typed into it: {out['box']!r}"


def test_how_many_years_of_experience_still_matches(browser):
    """The other half: the guard only refuses a single-word alias and the
    fuzzy pass, so a question naming the whole field still resolves.
    """
    page = browser.new_page()
    try:
        page.goto(f"file://{os.path.join(FIXTURES_DIR, 'campus_questionnaire.html')}")
        for js in ["field_aliases.js", "matcher.js"]:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            """() => ({
                years: matchField("How many years of experience do you have?"),
                credits: matchField("How many credit hours towards your degree do you anticipate having completed by the time you would start this position?"),
                gpa: matchField("What is your cumulative GPA?"),
            })"""
        )
    finally:
        page.close()

    assert out["years"] == "years_experience"
    assert out["credits"] is None
    assert out["gpa"] == "gpa"


@pytest.mark.parametrize("gpa,bracket", [
    ("3.7", "3.5 or higher"),
    ("4.0", "3.5 or higher"),
    ("3.5", "3.5 or higher"),
    ("3.49", "3.0 - 3.49"),
    ("2.6", "2.5 - 2.99"),
    ("2.0", "2.0 - 2.49"),
    ("1.8", "Below 2.0"),
    ("3.7/4.0", "3.5 or higher"),
])
def test_a_gpa_lands_in_the_bracket_that_contains_it(browser, gpa, bracket):
    """A GPA dropdown offers ranges and a GPA is a number: no amount of string
    matching gets 3.7 into "3.5 or higher".
    """
    out = _evaluate_on(
        browser, "campus_questionnaire.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.canonical === 'gpa');
            return {action: r.action, detail: r.detail};
        }""",
        {**PROFILE, "gpa": gpa},
    )

    assert out["action"] == "filled", out
    assert out["detail"] == bracket, out


def test_a_gpa_that_fits_no_bracket_is_left_alone(browser):
    """Nothing is forced into the nearest bracket."""
    out = _evaluate_on(
        browser, "campus_questionnaire.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.canonical === 'gpa');
            return {action: r.action, detail: r.detail};
        }""",
        {**PROFILE, "gpa": "first class honours"},
    )

    assert out["action"] != "filled", out


# --- The resume upload iCIMS hides -----------------------------------------

FAKE_RESUME = {
    "name": "resume.pdf",
    "dataUrl": "data:application/pdf;base64,JVBERi0xLjQgZmFrZQ==",
}


def test_a_resume_reaches_the_input_icims_hides(browser):
    """iCIMS's file input is display:none with no id, no name and no label;
    the "Upload Resume" button beside it is what the applicant sees and what
    its own script wires up. Skipped for being invisible, the resume was
    never attached on any iCIMS application -- and never reported as missing
    either, since the field was not in the report at all.
    """
    out = _evaluate_on(
        browser, "icims_resume.html",
        """async (profile) => {
            const fields = extractFields();
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.canonical === 'resume_file');
            const input = document.querySelector('input[type=file]');
            return {
                labels: fields.map((f) => f.label),
                action: r ? r.action : null,
                attached: input.files.length ? input.files[0].name : null,
            };
        }""",
        {**PROFILE, "resume_file": FAKE_RESUME},
    )

    assert out["labels"] == ["Upload Resume"], out
    assert out["action"] == "filled", out
    assert out["attached"] == "resume.pdf", out


def test_a_missing_resume_is_reported_rather_than_silently_skipped(browser):
    """Being invisible to the extractor is worse than being unanswerable:
    with no resume saved the applicant should at least be told.
    """
    out = _evaluate_on(
        browser, "icims_resume.html",
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const r = report.results.find((x) => x.canonical === 'resume_file');
            return {action: r ? r.action : null, detail: r ? r.detail : null};
        }""",
        {**PROFILE, "resume_file": None},
    )

    assert out["action"] == "needs_review"
    assert "No resume saved" in out["detail"]


def test_a_hidden_file_input_with_nothing_pointing_at_it_stays_hidden(browser):
    """The exception is for an input a visible control plainly stands in for.
    A hidden file input on its own is hidden for a reason and is left alone.
    """
    page = browser.new_page()
    try:
        page.set_content(
            "<body><form>"
            "<input type='file' style='display:none'>"
            "<div><input type='file' style='display:none'>"
            "<button type='button'>Continue</button></div>"
            "<label for='v'>Email</label><input id='v'>"
            "</form></body>"
        )
        for js in SCRIPT_FILES:
            page.add_script_tag(path=os.path.join(EXT_DIR, js))
        out = page.evaluate(
            "() => extractFields().map((f) => ({type: f.type, label: f.label}))"
        )
    finally:
        page.close()

    assert [f for f in out if f["type"] == "file"] == [], out
    # Asserted non-empty, or the check above passes for the wrong reason.
    assert any(f["label"] == "Email" for f in out), out


# --- Reading a resume ------------------------------------------------------

def _resume_call(browser, responses):
    """Run parseResumeWithClaude against a stubbed fetch. `responses` is the
    queue of {status, body} the fake API hands back, one per request.
    """
    page = browser.new_page()
    try:
        page.goto("about:blank")
        page.add_script_tag(path=os.path.join(EXT_DIR, "llm.js"))
        return page.evaluate(
            """async (responses) => {
                const sent = [];
                const queue = [...responses];
                window.fetch = async (url, init) => {
                    sent.push(JSON.parse(init.body));
                    const next = queue.shift();
                    return {
                        ok: next.status === 200,
                        status: next.status,
                        text: async () => JSON.stringify(next.body),
                    };
                };
                const result = await parseResumeWithClaude({
                    apiKey: "sk-ant-test",
                    text: "Jamie Rivera\\nTest Engineer at Test Industries",
                });
                return {sent, result};
            }""",
            responses,
        )
    finally:
        page.close()


def _ok(text):
    return {"status": 200, "body": {"content": [{"type": "text", "text": text}]}}


PARSED = json.dumps({
    "education": [{"school": "State University", "degree": "B.S.",
                   "field_of_study": "Mechanical Engineering", "graduation_year": "2027"}],
    "experience": [],
    "fields": {"first_name": "Jamie", "last_name": "Rivera", "email": "", "phone": "",
               "city": "", "state": "", "linkedin_url": "", "github_url": "",
               "portfolio_url": "", "gpa": "", "education_level": "", "languages": "",
               "current_company": "", "current_title": ""},
})


def test_the_resume_schema_asks_for_one_shape_not_sixteen_thousand(browser):
    """Every scalar optional under required: [] asks the schema compiler to
    allow every subset of fourteen keys, and the API answered the whole
    request with "Schema is too complex" -- so reading a resume failed before
    the document was ever looked at. Requiring them all is one shape.
    """
    out = _resume_call(browser, [_ok(PARSED)])
    schema = out["sent"][0]["output_config"]["format"]["schema"]
    props = schema["properties"]["fields"]["properties"]

    assert sorted(schema["properties"]["fields"]["required"]) == sorted(props.keys())
    assert out["result"].get("error") is None, out["result"]


def test_a_refused_schema_still_gets_the_resume_read(browser):
    """A schema the API won't compile is a 400 before the resume is read, and
    the applicant sees an error about a schema they have never heard of.
    Asking for the same JSON in words guarantees nothing about the shape, but
    it is worth more than nothing.
    """
    out = _resume_call(browser, [
        {"status": 400, "body": {"error": {"message": "Schema is too complex."}}},
        _ok("```json\n" + PARSED + "\n```"),
    ])

    assert len(out["sent"]) == 2, out["sent"]
    # The retry drops the schema and asks in the prompt instead.
    assert "output_config" not in out["sent"][1]
    assert any(
        "JSON only" in b.get("text", "")
        for b in out["sent"][1]["messages"][0]["content"]
    ), out["sent"][1]
    # A fenced reply is still read.
    assert out["result"]["parsed"]["fields"]["first_name"] == "Jamie", out["result"]


def test_what_the_resume_does_not_say_is_not_offered_as_an_answer(browser):
    """Requiring every scalar means the reply carries "" for everything the
    document is silent about. An empty string offered as an import reads as
    an answer, and accepting it would blank a field already filled in by hand.
    """
    out = _resume_call(browser, [_ok(PARSED)])
    fields = out["result"]["parsed"]["fields"]

    assert fields == {"first_name": "Jamie", "last_name": "Rivera"}, fields
    # Asserted against something present, or the check above is vacuous.
    assert out["result"]["parsed"]["education"][0]["school"] == "State University"


def test_reading_a_resume_uses_sonnet(browser):
    """Extraction against a fixed schema, checked by the applicant before any
    of it becomes a profile -- not the judgement the fill itself needs.
    """
    out = _resume_call(browser, [_ok(PARSED)])
    assert out["sent"][0]["model"] == "claude-sonnet-5", out["sent"][0]["model"]


def test_sonnet_never_sends_the_fallback_beta_at_all(browser):
    """Server-side refusal fallbacks exist for the models that run safety
    classifiers and can answer with stop_reason: "refusal". Sonnet does not,
    so sending the parameter there buys a 400 and a silent retry on every
    request -- two calls where one would do.
    """
    out = _llm_call(
        browser,
        [{"status": 200, "body": _ok_body([
            {"ja_id": "ja-1", "value": "First time.", "skip_reason": ""},
        ])}],
    )

    assert len(out["sent"]) == 1, out["sent"]
    assert out["sent"][0]["body"]["model"] == "claude-sonnet-5"
    assert "anthropic-beta" not in out["sent"][0]["headers"]
    assert "fallbacks" not in out["sent"][0]["body"]


# --- Learning a mapping, not just an answer --------------------------------

def _map_call(browser, body, profile=None, items=None):
    page = browser.new_page()
    try:
        page.goto("about:blank")
        page.add_script_tag(path=os.path.join(EXT_DIR, "llm.js"))
        return page.evaluate(
            """async ({body, profile, items}) => {
                const sent = [];
                window.fetch = async (url, init) => {
                    sent.push(JSON.parse(init.body));
                    return {ok: true, status: 200, text: async () => JSON.stringify(body)};
                };
                const result = await mapLabelsWithClaude({
                    apiKey: "sk-ant-test", profile, items,
                });
                return {sent, result};
            }""",
            {"body": body, "profile": profile or {**PROFILE},
             "items": items or [{"label": "home telephone", "answer": "(555) 123-4567"}]},
        )
    finally:
        page.close()


def _mapping_body(rows):
    return {"content": [{"type": "text",
                         "text": json.dumps({"mappings": rows})}]}


def test_learning_asks_which_field_not_what_the_answer_is(browser):
    """A remembered answer is keyed by this form's exact wording, so the same
    question worded differently on the next site misses. An alias maps the
    question to a profile field and holds for any wording of it.
    """
    out = _map_call(browser, _mapping_body([
        {"label": "home telephone", "profile_field": "phone"},
    ]))

    assert out["result"]["mappings"] == {"home telephone": "phone"}
    # The applicant's own answer goes along as context -- "Number" on its own
    # says nothing -- but what comes back is a field name, never a value.
    sent = json.dumps(out["sent"][0])
    assert "(555) 123-4567" in sent
    schema = out["sent"][0]["output_config"]["format"]["schema"]
    props = schema["properties"]["mappings"]["items"]["properties"]
    assert set(props) == {"label", "profile_field"}


def test_a_mapping_onto_a_self_id_field_is_dropped(browser):
    """HANDOFF rule 5: a learned label mapping may never point at a sensitive
    field, because learned aliases are consulted before every other check and
    one pointing at race_ethnicity would bypass the sensitive gate entirely.
    Refused in the worker as well as by sanitizeLearnedAliases downstream.
    """
    out = _map_call(browser, _mapping_body([
        {"label": "what is your background", "profile_field": "race_ethnicity"},
        {"label": "do you agree to the terms", "profile_field": "consent_general"},
        {"label": "have you ever been convicted", "profile_field": "criminal_history"},
        {"label": "home telephone", "profile_field": "phone"},
    ]))

    # Asserted non-empty first, or the absence checks below pass trivially.
    assert out["result"]["mappings"] == {"home telephone": "phone"}


def test_a_sensitive_field_is_never_even_offered_as_a_choice(browser):
    """The list of field names sent to the model leaves them out, so the
    refusal above is a second line rather than the only one.
    """
    out = _map_call(browser, _mapping_body([]))
    sent = json.dumps(out["sent"][0])

    assert "race_ethnicity" not in sent, sent[:400]
    assert "veteran_status" not in sent
    assert "criminal_history" not in sent
    assert "consent_general" not in sent
    # Ordinary fields are offered, or the checks above mean nothing.
    assert "phone" in sent and "linkedin_url" in sent


def test_an_empty_mapping_is_not_stored_as_a_field_named_nothing(browser):
    """"" is what the model is told to return when none of the fields fits,
    and it has to stay nothing rather than becoming an alias to "".
    """
    out = _map_call(browser, _mapping_body([
        {"label": "which shift suits you", "profile_field": ""},
    ]))

    assert out["result"]["mappings"] == {}


def test_the_learn_button_runs_the_mapping_through_the_real_gate():
    """run.js is not loaded by the browser fixtures, so this is a static check
    that what comes back from the model goes through sanitizeLearnedAliases --
    which reads field_aliases.js's own sets -- before it reaches storage.
    """
    src = open(os.path.join(EXT_DIR, "run.js"), encoding="utf-8").read()
    learn = src[src.index("panel?.onLearn("):src.index("// Whatever arrived already filled")]

    assert '"ja-learn-map"' in learn
    assert "sanitizeLearnedAliases(reply.mappings, profile)" in learn
    # The sanitized set is what gets stored, not the raw reply.
    assert "learned: safe" in learn
    assert "learned: reply.mappings" not in learn


# --- iCIMS's own questionnaires --------------------------------------------

BOEING_Q1 = "1. Do your current job duties involve Boeing under any of the following conditions?"
BOEING_Q2 = ("2. Have you ever been employed by the U.S. Government (federal, state, county, "
             "or local, including publicly funded institutions) in either a civilian or "
             "military capacity?")


def test_icims_radio_options_get_the_word_that_names_them(browser):
    """The word is a bare text node after the input, with no <label>. Without
    it there is no way to tell the Yes radio from the No one, and the whole
    form was unanswerable for want of two words.
    """
    out = _evaluate_on(
        browser, "icims_questionnaire.html",
        """async () => extractFields()
            .filter((f) => f.type === 'radio')
            .map((f) => f.label)""",
        None,
    )

    assert out == ["Yes", "No", "Yes", "No"], out


def test_a_question_buried_under_its_own_bullet_lists_is_still_the_question(browser):
    """Question 1 states itself and then spends three bullet lists qualifying
    it. Over 300 characters the cell was given up on, and the nearest
    preceding text -- the last bullet -- was taken as the question instead.
    """
    out = _evaluate_on(
        browser, "icims_questionnaire.html",
        """async () => {
            const groups = {};
            for (const f of extractFields()) {
                if (f.type === 'radio') groups[f.name] = f.group_label;
            }
            return groups;
        }""",
        None,
    )

    assert out["icims_f_Q1"] == BOEING_Q1, out
    assert out["icims_f_Q2"] == BOEING_Q2, out


def test_a_question_written_straight_into_the_cell_is_read(browser):
    """Question 6 is a textarea preceded by a bare text node.
    nearestPrecedingText only walks previousElementSibling, so it had no
    label at all -- nothing to match against and nothing to learn.
    """
    out = _evaluate_on(
        browser, "icims_questionnaire.html",
        """async () => (extractFields().find((f) => f.tag === 'textarea') || {}).label""",
        None,
    )

    assert out.startswith("6. Describe how you found out about this job"), out


def test_an_icims_questionnaire_fills_from_what_it_was_taught(browser):
    """None of these can come from a profile -- they are about this company.
    What matters is that they can be answered once and fill from then on,
    which needs every one of the three readings above to work.
    """
    out = _evaluate_on(
        browser, "icims_questionnaire.html",
        """async ({profile, remembered}) => {
            setLearnedAnswers(remembered);
            const report = await fillForm(profile, null, {});
            const checked = [...document.querySelectorAll('input[type=radio]:checked')]
                .map((el) => el.id);
            return {checked, filled: report.results.filter((r) => r.action === 'filled').length};
        }""",
        {"profile": PROFILE, "remembered": {
            _norm_q(BOEING_Q1): "No",
            _norm_q(BOEING_Q2): "No",
        }},
    )

    assert sorted(out["checked"]) == ["icims_f_Q1_no", "icims_f_Q2_no"], out


def _norm_q(text):
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()
