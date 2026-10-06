"""The applicant's own rules for what goes on an application, enforced in
code: what they won't claim, "Simplify" never appearing, no em dashes,
answers about one company never reused at another, the preferred-name box
left blank, the transcript attached, a job already applied to left alone,
and the Data Bank doc read into the profile.

Every one of these is a rule the browser skills already follow by being
told to. Here they hold whether or not anything was told anything.
"""

from __future__ import annotations

import json
import os

from .conftest import EXT_DIR, PROFILE, SCRIPT_FILES

NEVER = "CNC machining, waterjet, tolerance stack-up"


def _fill(page, profile, opts=None):
    return page.evaluate(
        """async ({profile, opts}) => {
            const report = await fillForm(profile, null, opts || {});
            return {
                results: report.results,
                values: Object.fromEntries(Array.from(
                    document.querySelectorAll('input:not([type=file]), textarea, select'))
                    .map((el) => [el.id, el.value])),
            };
        }""",
        {"profile": profile, "opts": opts or {}},
    )


def _by_label(out, label):
    for r in out["results"]:
        if r["label"].strip() == label:
            return r
    raise AssertionError(f"{label!r} not in {[r['label'] for r in out['results']]}")


# --- Never claim -------------------------------------------------------------

def test_a_saved_answer_naming_something_never_claimed_is_left_for_them(load):
    """The saved answers came from an old export that still says "CNC
    machining". Pasting it puts a claim on the form the applicant has said
    they can't back up.
    """
    page = load(html="""<form>
      <label for="fit">What makes you a good fit?</label><textarea id="fit"></textarea>
      <label for="goals">What are your career goals?</label><textarea id="goals"></textarea>
    </form>""")
    profile = {**PROFILE, "never_claim": NEVER, "custom_answers": {
        "good fit": "Hands-on with CNC machining and 3D printing, so my designs get built.",
        "career goals": "Designing structures that end up flying.",
    }}
    out = _fill(page, profile)

    fit = _by_label(out, "What makes you a good fit?")
    assert fit["action"] == "needs_review"
    assert "cnc machining" in fit["detail"].lower()
    assert out["values"]["fit"] == ""
    # An answer with nothing on the list is untouched by any of this.
    assert out["values"]["goals"] == "Designing structures that end up flying."


def test_a_skills_list_just_loses_the_items_never_claimed(load):
    page = load(html="""<form>
      <label for="s">List your technical skills</label><input id="s">
    </form>""")
    profile = {**PROFILE, "never_claim": NEVER, "custom_answers": {
        "technical skills": "PTC Creo, CNC Machining, ANSYS, Waterjet Cutting, GD&T, Tolerance Stack-Up Analysis",
    }}
    out = _fill(page, profile)

    assert out["values"]["s"] == "PTC Creo, ANSYS, GD&T"


def test_a_word_inside_another_word_is_not_a_claim(load):
    """Whole words only: never claiming "CAD" must not refuse "decade"."""
    page = load(html="<body></body>")
    out = page.evaluate(
        """() => ({
            decade: writableText("A decade of building things.", {never_claim: "CAD"}),
            cad: writableText("Modeled it in CAD.", {never_claim: "CAD"}),
        })"""
    )
    assert out["decade"] == {"text": "A decade of building things."}
    assert "refused" in out["cad"]


def test_claude_writing_something_never_claimed_is_not_applied(load):
    page = load(fixture="unknowns.html")
    out = page.evaluate(
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const target = llmFieldsFor(report).find((f) => f.type !== 'select');
            const applied = await applyLlmAnswers(report,
                {[target.ja_id]: "I ran the waterjet every day."}, {}, profile);
            return {applied, value: document.querySelector(`[data-ja-id="${target.ja_id}"]`).value};
        }""",
        {**PROFILE, "never_claim": NEVER},
    )
    assert out["applied"] == 0
    assert out["value"] == ""


def test_a_remembered_answer_naming_something_never_claimed_is_left_for_them(load):
    page = load(html="""<form>
      <label for="q">What shop equipment have you used?</label><input id="q">
    </form>""")
    out = page.evaluate(
        """async (profile) => {
            setLearnedAnswers({"what shop equipment have you used": "Waterjet and lathe"});
            const report = await fillForm(profile, null, {});
            return {action: report.results[0].action, value: document.getElementById('q').value};
        }""",
        {**PROFILE, "never_claim": NEVER},
    )
    assert out["action"] == "needs_review"
    assert out["value"] == ""


def test_a_work_history_description_naming_something_never_claimed_is_left(load):
    page = load(html="""<form><fieldset><legend>Work Experience</legend>
      <label for="d">Description</label>
      <textarea id="d" name="experience[0][description]"></textarea>
    </fieldset></form>""")
    profile = {**PROFILE, "never_claim": NEVER, "experience": [
        {"company": "Test Industries", "title": "Engineer", "location": "", "start_date": "2026-05",
         "end_date": "Present", "description": "Ran tolerance stack-up studies on fixtures."},
    ]}
    out = _fill(page, profile)
    assert out["values"]["d"] == ""


# --- Dashes and Simplify ----------------------------------------------------

def test_em_dashes_and_double_hyphens_never_reach_the_form(load):
    page = load(html="""<form>
      <label for="goals">What are your career goals?</label><textarea id="goals"></textarea>
    </form>""")
    profile = {**PROFILE, "custom_answers": {
        "career goals": "Design and analysis — FEA, tolerances -- then production, 2027–2028.",
    }}
    out = _fill(page, profile)
    assert out["values"]["goals"] == "Design and analysis, FEA, tolerances, then production, 2027-2028."


def test_how_did_you_hear_picks_the_company_site_and_never_simplify(load):
    page = load(html="""<form>
      <label for="h">How did you hear about us?</label>
      <select id="h"><option value="">Select</option>
        <option value="li">LinkedIn</option>
        <option value="si">Simplify</option>
        <option value="web">Company Website</option>
      </select>
    </form>""")
    for saved in ("LinkedIn", "Simplify", ""):
        out = _fill(page, {**PROFILE, "how_heard": saved})
        assert out["values"]["h"] == "web", saved
        page.evaluate("() => { document.getElementById('h').value = ''; }")


def test_how_did_you_hear_with_no_company_site_choice_is_not_guessed(load):
    page = load(html="""<form>
      <label for="h">How did you hear about us?</label>
      <select id="h"><option value="">Select</option>
        <option value="si">Simplify.jobs</option>
        <option value="fair">Career Fair</option>
      </select>
    </form>""")
    out = _fill(page, {**PROFILE, "how_heard": "Simplify"})
    assert out["values"]["h"] == ""
    assert "company-website" in _by_label(out, "How did you hear about us?")["detail"]


def test_how_did_you_hear_as_a_box_names_the_company(load):
    page = load(html="""<form>
      <label for="h">How did you hear about this job?</label><input id="h">
    </form>""")
    out = _fill(page, {**PROFILE, "how_heard": "Simplify"}, {"company": "Acme Rockets"})
    assert out["values"]["h"] == "Acme Rockets careers page"


def test_claude_is_never_allowed_to_answer_simplify(load):
    page = load(html="""<form>
      <label for="h">Where did you find this posting?</label><input id="h">
    </form>""")
    out = page.evaluate(
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const target = llmFieldsFor(report)[0];
            const applied = await applyLlmAnswers(report, {[target.ja_id]: "Simplify"}, {}, profile);
            return {applied, value: document.getElementById('h').value};
        }""",
        PROFILE,
    )
    assert out["applied"] == 0
    assert out["value"] == ""


# --- Answers about one company -------------------------------------------------

PER_JOB_FORM = """<form>
  <label for="why">Why do you want to work at Acme?</label><textarea id="why"></textarea>
  <label for="sum">Personal Summary</label><textarea id="sum"></textarea>
  <label for="int">What interests you about this role?</label><textarea id="int"></textarea>
</form>"""


def test_why_this_company_is_never_answered_from_a_saved_answer(load):
    page = load(html=PER_JOB_FORM)
    profile = {**PROFILE, "custom_answers": {
        "why do you want to work": "Boom is building the airliner I want to work on.",
        "personal summary": "Generic summary.",
        "interests you": "The supersonic part.",
    }}
    off = _fill(page, profile)
    assert all(off["values"][k] == "" for k in ("why", "sum", "int")), off["values"]
    assert {_by_label(off, l)["action"] for l in (
        "Why do you want to work at Acme?", "Personal Summary", "What interests you about this role?",
    )} == {"needs_review"}


def test_with_ai_assist_on_why_this_company_goes_to_claude(load):
    page = load(html=PER_JOB_FORM)
    out = page.evaluate(
        """async (profile) => {
            const report = await fillForm(profile, null, {writeForJob: true});
            return llmFieldsFor(report).map((f) => f.label);
        }""",
        PROFILE,
    )
    assert "Why do you want to work at Acme?" in out
    assert "Personal Summary" in out


def test_an_answer_about_one_company_is_never_remembered(load):
    """Typed into Boom's "why Boom" box, kept, and pasted into Varda's."""
    page = load(html=PER_JOB_FORM.replace(
        "</form>", '<label for="ok">Which shift do you prefer?</label><input id="ok"></form>'))
    out = page.evaluate(
        """async (profile) => {
            for (const [id, v] of [['why', 'Because of the rockets.'], ['ok', 'Days']]) {
                const el = document.getElementById(id);
                el.value = v;
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            const learned = learnPageNow(profile);
            return {answers: Object.keys(learned.answers),
                    markup: Object.values(learned.markup).map((m) => m.answer)};
        }""",
        PROFILE,
    )
    assert out["answers"] == ["which shift do you prefer"], out
    assert "Because of the rockets." not in out["markup"]


# --- Preferred name ----------------------------------------------------------

def test_preferred_name_stays_blank_unless_the_form_requires_it(load):
    page = load(html="""<form>
      <label for="p1">Preferred Name</label><input id="p1">
    </form>""")
    profile = {**PROFILE, "preferred_name": ""}
    out = _fill(page, profile)
    assert out["values"]["p1"] == ""
    assert _by_label(out, "Preferred Name")["action"] == "filled"  # settled, not a gap

    page2 = load(html="""<form>
      <label for="p2">Preferred First Name *</label><input id="p2" required>
    </form>""")
    out = _fill(page2, profile)
    assert out["values"]["p2"] == PROFILE["first_name"]


# --- Transcript --------------------------------------------------------------

TRANSCRIPT = {"name": "transcript.pdf", "dataUrl": "data:application/pdf;base64,JVBERi0xLjQK"}
RESUME = {"name": "resume.pdf", "dataUrl": "data:application/pdf;base64,JVBERi0xLjQK"}


def test_the_transcript_goes_where_a_transcript_is_asked_for(load):
    page = load(html="""<form>
      <label for="t">Unofficial Transcript</label><input type="file" id="t">
      <label for="r">Resume and transcript (one file)</label><input type="file" id="r">
    </form>""")
    out = page.evaluate(
        """async (profile) => {
            await fillForm(profile, null, {});
            return {t: document.getElementById('t').files[0]?.name,
                    r: document.getElementById('r').files[0]?.name};
        }""",
        {**PROFILE, "resume_file": RESUME, "transcript_file": TRANSCRIPT},
    )
    assert out == {"t": "transcript.pdf", "r": "resume.pdf"}


# --- Already applied -----------------------------------------------------------

def _click_run(browser, html):
    page = browser.new_page()
    page.add_init_script(
        """((profileJson) => {
            const store = {profile: JSON.parse(profileJson), settings: {}};
            window.chrome = {
                storage: {local: {
                    get: async (keys) => Object.fromEntries(
                        (Array.isArray(keys) ? keys : [keys])
                            .filter((k) => k in store).map((k) => [k, store[k]])),
                    set: async () => {},
                }},
                runtime: {
                    sendMessage: async () => ({}),
                    onMessage: {addListener: () => {}, removeListener: () => {}},
                },
            };
            globalThis.__JA_VIA_CLICK = true;
        })(PROFILE_JSON);""".replace("PROFILE_JSON", repr(json.dumps(PROFILE)))
    )
    page.goto("about:blank")
    page.set_content(html)
    for js in SCRIPT_FILES + ["panel.js", "run.js"]:
        page.add_script_tag(path=os.path.join(EXT_DIR, js))
    page.wait_for_timeout(500)
    out = page.evaluate(
        """() => ({
            panel: document.getElementById('ja-autofill-panel').shadowRoot.querySelector('.body').textContent,
            email: document.getElementById('e').value,
        })"""
    )
    page.close()
    return out


def test_a_job_already_applied_to_is_not_filled(browser):
    out = _click_run(browser, """<body>
      <div class="banner">You are currently submitted to this job.</div>
      <form><label for="e">Email</label><input id="e" name="email"></form></body>""")
    assert "already applied" in out["panel"]
    assert out["email"] == ""


def test_an_ordinary_form_still_fills(browser):
    out = _click_run(browser, """<body>
      <p>Apply now. Applications reviewed on a rolling basis.</p>
      <form><label for="e">Email</label><input id="e" name="email"></form></body>""")
    assert "already applied" not in out["panel"]
    assert out["email"] == PROFILE["email"]


# --- The Data Bank -----------------------------------------------------------

# Same shape as the real doc's Markdown export, with a made-up person.
DATA_BANK = r"""# **Job Application Data Bank**

*Claude reads this whole doc at the start of every application session.*

## **1. Rules for Claude**

  - Never click Submit without a yes.

## **3\. Contact info**

> * First name: Jamie  
  - Last name: Rivera
  - Middle name: (none, leave blank)
  - Preferred name: ALWAYS leave blank. Only if required, enter the legal first name.
  - Email: jamie.rivera@example.com
  - Phone: (555) 123-4567
  - Address line 1: 123 Test Street
  - City: Springfield
  - State: NY
  - ZIP: 10001
> * LinkedIn: https\://linkedin.com/in/jamierivera  
  - GitHub: (none, leave blank)

## **4. Education**

> * Example State University, B.S. Mechanical Engineering, expected May 2028  
  - Start: 2024 | GPA: 3.61 / 4.00 | Degree status: in progress, not completed
  - Completed semesters by Summer 2027: \[FILL: e.g. 5 or 6\]

## **5. Work authorization, logistics, screening questions**

  - Citizenship: U.S. Citizen (qualifies as a 'U.S. person')
  - Authorized to work in U.S.: Yes
  - Needs sponsorship now or future: No
  - Over 18: Yes
  - Driver's license: Yes
  - Consent to background check: Yes
  - Previously employed by this company (default): No
  - Criminal history: No
  - Pay expectation: Depends on the budget allocated for this role
> * Current: Manufacturing Engineering Co-op, Test Industries | Years experience: 1  

## **6. Experience**

  - Current: Senior Machinist, Old Shop | Years experience: 9
  - Ran CNC machining for everything.

## **7. Skills (copy-paste)**

CNC Machining, Waterjet Cutting

## **8. Saved answers to common questions**

### **greatest strength**

Learning fast.

## **9. Voluntary self-ID (EEO)**

  - Gender: Female
  - Pronouns: (blank: decline to answer)
  - Hispanic/Latino: No
  - Race/ethnicity: White
  - Veteran status: I am not a protected veteran
  - Disability status: No, I do not have a disability and have not had one in the past
"""


def test_the_data_bank_reads_into_the_profile(load):
    page = load(html="<body></body>", scripts=["field_aliases.js", "matcher.js", "databank.js"])
    out = page.evaluate("(text) => parseDataBank(text)", DATA_BANK)

    assert out["first_name"] == "Jamie"
    assert out["middle_name"] == ""
    assert out["preferred_name"] == ""
    assert out["github_url"] == ""
    assert out["postal_code"] == "10001"
    assert out["linkedin_url"] == "https://linkedin.com/in/jamierivera"
    assert out["gpa"] == "3.61"
    assert out["education"] == [{"school": "Example State University", "degree": "B.S.",
                                 "field_of_study": "Mechanical Engineering",
                                 "graduation_year": "2028"}]
    assert out["citizenship_status"] == "U.S. Citizen"
    assert out["work_authorized"] is True
    assert out["needs_sponsorship"] is False
    assert out["criminal_history"] is False
    assert out["current_title"] == "Manufacturing Engineering Co-op"
    assert out["current_company"] == "Test Industries"
    assert out["years_experience"] == "1"
    assert out["gender"] == "Female"
    assert out["race_ethnicity"] == "White"
    assert out["pronouns"] == ""
    assert out["disability_status"].startswith("No, I do not have a disability")


def test_the_data_bank_sections_marked_outdated_are_not_read(load):
    """Experience, skills and saved answers still carry claims the applicant
    has since dropped, and the doc itself says not to use them.
    """
    page = load(html="<body></body>", scripts=["field_aliases.js", "matcher.js", "databank.js"])
    out = page.evaluate("(text) => parseDataBank(text)", DATA_BANK)

    assert "CNC" not in json.dumps(out)
    assert "Learning fast" not in json.dumps(out)
    assert "custom_answers" not in out and "experience" not in out
    assert any("Experience" in s for s in out["_databank"]["skipped"])


def test_the_data_bank_pasted_as_plain_text_reads_the_same(load):
    """Select-all and copy out of Google Docs gives no Markdown at all."""
    import re
    plain = re.sub(r"\*\*|^## |^\s*(?:> )?[-*] ", "", DATA_BANK, flags=re.M).replace("\\", "")
    page = load(html="<body></body>", scripts=["field_aliases.js", "matcher.js", "databank.js"])
    md = page.evaluate("(text) => parseDataBank(text)", DATA_BANK)
    pt = page.evaluate("(text) => parseDataBank(text)", plain)
    del md["_databank"], pt["_databank"]
    assert pt == md


def test_pasting_the_data_bank_on_the_options_page_fills_the_boxes(browser):
    from .test_hardening import _options_page

    page = _options_page(browser, seed={"profile": {}, "settings": {}})
    try:
        page.wait_for_timeout(200)
        out = page.evaluate(
            """async (text) => {
                document.getElementById('import-json').value = text;
                await document.getElementById('import-json-btn').onclick();
                return {
                    first: document.querySelector('[data-f="first_name"]').value,
                    gender: document.querySelector('[data-f="gender"]').value,
                    authorized: document.querySelector('[data-bool="work_authorized"]').value,
                    school: document.querySelector('#edu-list [data-k="school"]').value,
                    status: document.getElementById('import-status').textContent,
                };
            }""",
            DATA_BANK,
        )
    finally:
        page.close()

    assert out["first"] == "Jamie"
    assert out["gender"] == "Female"
    assert out["authorized"] == "true"
    assert out["school"] == "Example State University"
    assert "Data Bank" in out["status"] and "Experience" in out["status"]
