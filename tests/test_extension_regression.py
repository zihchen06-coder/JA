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
    "icims_profile.html": {"filled": 24, "review": 1},
    "jazzhr_eeo.html": {"filled": 4, "review": 0},
    "jazzlike.html": {"filled": 7, "review": 0},
    "ldg_form.html": {"filled": 12, "review": 0},
    "ldg_real.html": {"filled": 33, "review": 2},
    "multipage.html": {"filled": 3, "review": 0},
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


def _llm_call(browser, responses):
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
            """async ({responses, profile}) => {
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
            {"responses": responses, "profile": PROFILE},
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
    assert sent["body"]["model"] == "claude-opus-5"
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
    fill over an optional extra.
    """
    out = _llm_call(
        browser,
        [
            {"status": 400, "body": {"error": {"message": "unsupported beta"}}},
            {"status": 200, "body": _ok_body([
                {"ja_id": "ja-1", "value": "Second time.", "skip_reason": ""},
            ])},
        ],
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
