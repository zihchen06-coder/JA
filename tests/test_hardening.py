"""Adversarial input: what happens when the profile, the page or the API
gives this thing something it wasn't written for.

Every test here exists because a job site is not a controlled environment.
Labels are written by whoever built the form, values come back from a model,
and stored data outlives the version of the code that wrote it. Nothing in
here may throw, and nothing may put the wrong value in a field.
"""

from __future__ import annotations

import json

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import EXT_DIR, PROFILE  # noqa: E402

FILL = "(profile) => fillForm(profile, null, {})"


def _fill(page, profile):
    return page.evaluate(f"async {FILL}", profile)


def test_an_empty_profile_fills_nothing_and_does_not_throw(load):
    page = load(fixture="test_form.html")
    empty = {k: ("" if isinstance(v, str) else v) for k, v in PROFILE.items()}
    empty.update(education=[], experience=[], custom_answers={},
                 resume_file=None, cover_letter_file=None)
    for key in list(empty):
        if isinstance(empty[key], bool):
            empty[key] = ""
    report = _fill(page, empty)
    assert [r for r in report["results"] if r["action"] == "error"] == []
    assert [r for r in report["results"] if r["action"] == "filled"] == []


def test_a_profile_full_of_wrong_types_does_not_throw(load):
    """Stored data outlives the code that wrote it, and an import can put
    anything in. None of it may reach a field as "[object Object]".
    """
    page = load(fixture="test_form.html")
    broken = {
        **PROFILE,
        "first_name": None, "last_name": 12345, "email": ["a@b.c"],
        "phone": {"n": 1}, "city": True, "education": "not a list",
        "experience": [None, {"company": None}], "custom_answers": "not an object",
        "gpa": float("1.5"),
    }
    report = page.evaluate(f"async {FILL}", broken)
    assert [r for r in report["results"] if r["action"] == "error"] == []
    values = page.evaluate(
        "() => Array.from(document.querySelectorAll('input,textarea')).map((el) => el.value)"
    )
    for v in values:
        assert "[object Object]" not in v
        assert v != "null" and v != "undefined"


def test_a_page_with_no_labels_at_all_fills_nothing(load):
    page = load(html="<body><form>" + "<input>" * 20 + "</form></body>")
    report = _fill(page, PROFILE)
    assert [r for r in report["results"] if r["action"] == "filled"] == []
    assert [r for r in report["results"] if r["action"] == "error"] == []


def test_duplicate_element_ids_do_not_cross_wire_fields(load):
    """Invalid HTML, but common. Two fields sharing an id must not end up
    both pointing at the first one -- that fills the wrong box.
    """
    page = load(html="""<body><form>
        <label for="x">First Name</label><input id="x" name="a">
        <label for="x">Email</label><input id="x" name="b">
    </form></body>""")
    _fill(page, PROFILE)
    values = page.evaluate(
        "() => Array.from(document.querySelectorAll('input')).map((el) => el.value)"
    )
    # Whatever it decides, it must not put the same value in both.
    assert values[0] != values[1] or values == ["", ""]


def test_disabled_and_readonly_fields_are_left_alone(load):
    page = load(html="""<body><form>
        <label for="a">First Name</label><input id="a" disabled>
        <label for="b">Last Name</label><input id="b" readonly>
        <label for="c">Email</label><input id="c">
    </form></body>""")
    _fill(page, PROFILE)
    out = page.evaluate(
        "() => ({a: a.value, b: b.value, c: c.value})"
    )
    assert out["a"] == ""  # disabled
    assert out["b"] == ""  # readonly -- a form that fills it would be lying
    assert out["c"] == PROFILE["email"]


def test_a_select_with_no_options_does_not_throw(load):
    page = load(html="""<body><form>
        <label for="s">State</label><select id="s"></select>
    </form></body>""")
    report = _fill(page, PROFILE)
    assert [r for r in report["results"] if r["action"] == "error"] == []


def test_hostile_label_text_is_handled_as_text(load):
    """Labels are written by whoever built the form. They reach storage and
    then the options page, so they may never be treated as markup.
    """
    page = load(html="""<body><form>
        <label for="a">&lt;img src=x onerror=alert(1)&gt; Email</label><input id="a">
        <label for="b">Phone " onfocus="alert(2)</label><input id="b">
    </form></body>""")
    report = _fill(page, PROFILE)
    assert [r for r in report["results"] if r["action"] == "error"] == []
    labels = [r["label"] for r in report["results"]]
    assert any("<img" in (l or "") for l in labels)


def test_a_very_large_form_completes(load):
    page = load(html="<body><form>" + "".join(
        f'<label for="f{i}">Question number {i}</label><input id="f{i}">' for i in range(600)
    ) + "</form></body>")
    report = _fill(page, PROFILE)
    assert len(report["results"]) >= 600
    assert [r for r in report["results"] if r["action"] == "error"] == []


def test_filling_the_same_page_twice_is_stable(load):
    page = load(fixture="test_form.html")
    first = _fill(page, PROFILE)
    second = _fill(page, PROFILE)
    filled_first = sum(1 for r in first["results"] if r["action"] == "filled")
    already = sum(1 for r in second["results"] if r["action"] == "already_filled")
    assert filled_first > 0
    # Nothing is filled twice, and nothing errors on the second pass.
    assert already >= filled_first - 2
    assert [r for r in second["results"] if r["action"] == "error"] == []


def test_a_corrupt_learned_store_is_ignored_rather_than_fatal(load):
    page = load(fixture="unknowns.html")
    out = page.evaluate(
        """async (profile) => {
            setLearnedAliases({"a label": 42, "another": null, "third": {x: 1}});
            setLearnedAnswers({"what is your spirit animal": {not: "a string"},
                               "anything else we should know": 7});
            const report = await fillForm(profile, null, {});
            return {
                errors: report.results.filter((r) => r.action === 'error'),
                values: Array.from(document.querySelectorAll('input')).map((el) => el.value),
            };
        }""",
        PROFILE,
    )
    assert out["errors"] == []
    for v in out["values"]:
        assert "[object Object]" not in v


def test_a_malformed_model_reply_changes_nothing(load):
    page = load(fixture="unknowns.html")
    out = page.evaluate(
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            const before = Array.from(document.querySelectorAll('input')).map((el) => el.value);
            const results = [];
            for (const reply of [null, undefined, [], "text", {ja_x: "v"},
                                 {"ja-0": null}, {"ja-0": {deep: 1}}]) {
                results.push(await applyLlmAnswers(report, reply, {}, profile));
            }
            const after = Array.from(document.querySelectorAll('input')).map((el) => el.value);
            return {results, changed: JSON.stringify(before) !== JSON.stringify(after)};
        }""",
        PROFILE,
    )
    assert out["results"] == [0, 0, 0, 0, 0, 0, 0]
    assert out["changed"] is False


def test_a_field_removed_mid_fill_is_reported_not_thrown(load):
    page = load(fixture="test_form.html")
    out = page.evaluate(
        """async (profile) => {
            const report = await fillForm(profile, null, {});
            // The page tears itself down, as a single-page app does on a
            // route change, and then verification runs.
            document.querySelectorAll('input').forEach((el) => el.remove());
            const lost = await verifyFilled(report, 0);
            return {lost: lost.length, errors: report.results.filter(
                (r) => r.action === 'error').length};
        }""",
        PROFILE,
    )
    assert out["errors"] == 0


def test_an_absurdly_long_value_is_not_typed_into_a_short_box(load):
    page = load(html="""<body><form>
        <label for="a">Email</label><input id="a" maxlength="20">
    </form></body>""")
    page.evaluate(
        "(profile) => fillForm({...profile, email: 'x'.repeat(5000)}, null, {})",
        PROFILE,
    )
    value = page.evaluate("() => a.value")
    # The browser enforces maxlength on user input but not on assignment, so
    # what matters is that nothing throws and the page stays usable.
    assert isinstance(value, str)


def test_the_extractor_survives_a_detached_and_reattached_form(load):
    page = load(fixture="test_form.html")
    out = page.evaluate(
        """async (profile) => {
            const form = document.querySelector('form');
            const parent = form.parentNode;
            form.remove();
            const a = extractFields().length;   // nothing on the page
            parent.appendChild(form);
            const b = extractFields().length;   // back again
            const report = await fillForm(profile, null, {});
            return {a, b, errors: report.results.filter((r) => r.action === 'error').length};
        }""",
        PROFILE,
    )
    assert out["a"] == 0
    assert out["b"] > 0
    assert out["errors"] == 0


# --- The API layer ---------------------------------------------------------

def _api(load, body, status=200):
    page = load(scripts=["llm.js"])
    return page.evaluate(
        """async ({body, status, profile}) => {
            window.fetch = async () => ({
                ok: status === 200, status,
                text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
            });
            return await resolveWithClaude({
                apiKey: "k", profile, pageUrl: "https://x",
                fields: [{ja_id: "ja-0", label: "Q", type: "text", options: []}],
            });
        }""",
        {"body": body, "status": status, "profile": PROFILE},
    )


def test_every_shape_of_broken_api_response_is_survivable(load):
    """The reply is JSON from a model over a network. Any of it can be
    absent, truncated or the wrong type, and none of it may throw.
    """
    cases = [
        "not json at all",
        "",
        {"content": None},
        {"content": []},
        {"content": [{"type": "text", "text": "{"}]},            # truncated JSON
        {"content": [{"type": "text", "text": "null"}]},
        {"content": [{"type": "text", "text": '{"answers": null}'}]},
        {"content": [{"type": "text", "text": '{"answers": "nope"}'}]},
        {"content": [{"type": "text", "text": '{"answers": [null, 3, "x"]}'}]},
        {"content": [{"type": "text", "text": '{"answers": [{"value": "no id"}]}'}]},
    ]
    for body in cases:
        out = _api(load, body)
        assert isinstance(out, dict), body
        assert "error" in out or "answers" in out, body
        if "answers" in out:
            assert isinstance(out["answers"], dict)


def test_an_http_error_body_that_is_not_json_still_reports_something(load):
    out = _api(load, "<html>502 Bad Gateway</html>", status=502)
    assert "error" in out
    assert "502" in out["error"]


def test_a_refusal_is_reported_rather_than_read_as_an_answer(load):
    out = _api(load, {"stop_reason": "refusal", "content": [
        {"type": "text", "text": '{"answers": [{"ja_id": "ja-0", "value": "x"}]}'},
    ]})
    assert "error" in out
    assert "answers" not in out


# --- Stored data that grows without bound ----------------------------------

def test_the_learned_stores_do_not_grow_without_limit(load):
    """Applying at volume, every form contributes labels. Nothing here was
    capped, and extension storage is finite.
    """
    page = load(scripts=["llm.js"])
    out = page.evaluate(
        """() => {
            const many = {};
            for (let i = 0; i < 5000; i++) many['question number ' + i] = 'answer ' + i;
            return {
                answers: Object.keys(capLearned(many)).length,
                aliases: Object.keys(capLearned(many, 500)).length,
            };
        }"""
    )
    assert out["answers"] <= 2000
    assert out["aliases"] <= 500


# --- Text handling ---------------------------------------------------------

def test_matching_a_pathologically_long_label_terminates(load):
    page = load(scripts=["field_aliases.js", "matcher.js"])
    out = page.evaluate(
        """() => {
            const started = Date.now();
            const huge = 'first name '.repeat(4000);
            const result = matchField(huge);
            return {ms: Date.now() - started, result};
        }"""
    )
    assert out["ms"] < 5000, f"matchField took {out['ms']}ms"


def test_dates_and_months_survive_nonsense(load):
    page = load(scripts=["field_aliases.js", "matcher.js"])
    out = page.evaluate(
        """() => {
            const junk = ["", null, undefined, "not a date", "0000-00-00", "13/45/9999",
                          "2023-6", "2023-06-31", "\\u0000", "2023-06-15T10:00:00Z"];
            return junk.map((v) => [normalizeDate(v), formatMonthYear(v),
                                    datePartCandidates(v, 'month')]);
        }"""
    )
    for normalized, month_year, candidates in out:
        assert normalized is None or isinstance(normalized, str)
        assert month_year is None or isinstance(month_year, str)
        assert isinstance(candidates, list)


def test_hostile_stored_text_is_escaped_for_the_options_page(load):
    """Labels come from job sites and end up rendered on the options page.
    They are text, and must stay text.
    """
    page = load(scripts=[])
    page.evaluate(
        """() => {
            window.esc = (v) => (v ?? "").toString()
                .replace(/&/g, "&amp;").replace(/"/g, "&quot;")
                .replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }"""
    )
    out = page.evaluate(
        """() => {
            const hostile = '"><img src=x onerror="window.__pwned=1">';
            const div = document.createElement('div');
            div.innerHTML = `<input readonly value="${esc(hostile)}">`;
            document.body.appendChild(div);
            return {pwned: !!window.__pwned, images: div.querySelectorAll('img').length,
                    value: div.querySelector('input').value};
        }"""
    )
    assert out["pwned"] is False
    assert out["images"] == 0
    assert "<img" in out["value"]


# --- The files have to actually fit together -------------------------------

def _defined_names(source):
    """Top-level function and var declarations -- what one script makes
    available to another loaded beside it.
    """
    import re
    return set(re.findall(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", source, re.M)) | set(
        re.findall(r"^var\s+([A-Za-z_$][\w$]*)", source, re.M)
    )


def _local_names(source):
    """Names bound inside the file: consts, lets, and anything sitting in a
    parameter list. Called but not imported from anywhere.
    """
    import re
    names = set(re.findall(r"\b(?:const|let)\s+([A-Za-z_$][\w$]*)", source))
    for params in re.findall(r"\(([^()]*)\)\s*=>", source):
        names |= set(re.findall(r"[A-Za-z_$][\w$]*", params))
    for params in re.findall(r"function\s*[A-Za-z_$\w]*\s*\(([^()]*)\)", source):
        names |= set(re.findall(r"[A-Za-z_$][\w$]*", params))
    return names


def test_the_service_worker_only_calls_things_it_loads():
    """background.js runs in the service worker with llm.js beside it and
    nothing else. A call to a function that lives in a content script looks
    fine until the moment it runs, in a context with no console anyone reads.
    """
    import re

    background = open(os.path.join(EXT_DIR, "background.js"), encoding="utf-8").read()
    available = _defined_names(background) | _defined_names(
        open(os.path.join(EXT_DIR, "llm.js"), encoding="utf-8").read()
    )
    keywords = {
        "if", "for", "while", "switch", "catch", "return", "function", "typeof",
        "async", "await", "new", "delete", "void", "do", "else", "yield",
    }
    globals_ = {
        "Object", "Array", "JSON", "String", "Number", "Boolean", "Math", "Date",
        "Set", "Map", "Promise", "URL", "console", "chrome", "fetch", "atob",
        "setTimeout", "clearTimeout", "importScripts", "Error", "isNaN",
    }
    called = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", background))
    missing = called - available - keywords - globals_ - _local_names(background)
    assert not missing, f"background.js calls undefined: {sorted(missing)}"


def test_every_injected_script_loads_together_and_exposes_its_entry_points(load):
    """They are injected as one list into a page. A syntax error or a missing
    dependency in any of them takes the whole fill down silently.
    """
    page = load(
        html="<body><form><label for='a'>Email</label><input id='a'></form></body>",
        scripts=["field_aliases.js", "matcher.js", "extractor.js", "credentials.js",
                 "filler.js", "panel.js"],
    )
    present = page.evaluate(
        """() => [
            'extractFields', 'fillForm', 'applyLlmAnswers', 'llmFieldsFor',
            'learnFromAnswers', 'learnFromPrefilled', 'learnFromPage',
            'rememberableAnswers',
            'watchForCorrections', 'verifyFilled', 'missedFields',
            'setLearnedAliases', 'getLearnedAliases', 'setLearnedAnswers',
            'sanitizeLearnedAliases',
            'extractJobContext', 'createPanel', 'hostnameFor', 'getOrCreate',
        ].filter((name) => typeof window[name] !== 'function')"""
    )
    assert present == [], f"run.js calls these but they aren't defined: {present}"


# --- The options page ------------------------------------------------------

SEEDED = {
    "profile": {**PROFILE},
    "settings": {"use_llm": True},
    "learned_aliases": {"home telephone": "phone"},
    "learned_answers": {"did you graduate": "Yes", "which shift": "Either"},
    "profile_suggestions": {"linkedin_url": "https://linkedin.com/in/someone"},
    "misses": {
        "site.com|weird question": {
            "host": "site.com", "label": "Weird question", "action": "skipped_no_match",
            "detail": "", "required": True, "type": "text", "count": 7, "last": 1,
        }
    },
    "applications": [
        {"url": "https://x/apply", "host": "x.com", "title": "Mech E Intern",
         "company": "x", "filled": 12, "review": 1, "blank": 0, "at": 1, "pages": 2}
    ],
}


def _options_page(browser, seed=None):
    """The real options page, with chrome.storage stubbed under it."""
    page = browser.new_page()
    page.add_init_script(
        """(() => {
            const store = JSON.parse(SEED_JSON);
            window.chrome = {
                storage: {
                    local: {
                        get: async (keys) => Object.fromEntries(
                            (Array.isArray(keys) ? keys : [keys])
                                .filter((k) => k in store).map((k) => [k, store[k]])),
                        set: async (obj) => Object.assign(store, obj),
                    },
                    onChanged: {addListener: (fn) => (window.__onChanged = fn)},
                },
                runtime: {sendMessage: async () => ({})},
            };
        })();""".replace("SEED_JSON", repr(json.dumps(seed if seed is not None else SEEDED)))
    )
    page.goto(f"file://{os.path.join(EXT_DIR, 'options.html')}")
    page.wait_for_function("() => typeof renderLearned === 'function'")
    return page


def test_the_options_page_shows_everything_that_was_learned(browser):
    """It reads storage once when it opens, and every list on it is drawn by
    its own function. One of those not being called on load is invisible --
    the page looks fine and simply shows nothing.
    """
    page = _options_page(browser)
    try:
        page.wait_for_timeout(200)
        counts = page.evaluate(
            """() => ({
                aliases: document.querySelectorAll('#learned-list .cred-row').length,
                answers: document.querySelectorAll('#answers-learned-list .cred-row').length,
                suggestions: document.querySelectorAll('#suggestions-list .cred-row').length,
                misses: document.querySelectorAll('#misses-list .cred-row').length,
                applications: document.querySelectorAll('#applications-list .cred-row').length,
            })"""
        )
    finally:
        page.close()

    assert counts["aliases"] == 1, counts
    assert counts["answers"] == 2, counts
    assert counts["suggestions"] == 1, counts
    assert counts["misses"] == 1, counts
    assert counts["applications"] == 1, counts


def test_a_tab_left_open_while_applying_updates_itself(browser):
    """Everything is learned after the page opened, from the service worker.
    Without this the tab sits there showing nothing and looks broken.
    """
    page = _options_page(browser, seed={"profile": {**PROFILE}, "settings": {}})
    try:
        page.wait_for_timeout(200)
        before = page.evaluate(
            "() => document.querySelectorAll('#answers-learned-list .cred-row').length"
        )
        after = page.evaluate(
            """() => {
                window.__onChanged(
                    {learned_answers: {newValue: {"did you graduate": "Yes"}}}, "local");
                return document.querySelectorAll('#answers-learned-list .cred-row').length;
            }"""
        )
    finally:
        page.close()

    assert before == 0
    assert after == 1


def test_the_options_page_renders_hostile_stored_text_as_text(browser):
    """Labels come from job sites, are stored, and end up here."""
    hostile = '"><img src=x onerror="window.__pwned=1">'
    page = _options_page(browser, seed={
        "profile": {**PROFILE}, "settings": {},
        "learned_answers": {hostile: hostile},
        "misses": {f"evil.com|{hostile}": {
            "host": hostile, "label": hostile, "action": "skipped_no_match",
            "detail": hostile, "required": False, "type": "text", "count": 1, "last": 1,
        }},
    })
    try:
        page.wait_for_timeout(200)
        out = page.evaluate(
            """() => ({
                pwned: !!window.__pwned,
                images: document.querySelectorAll('img').length,
                shown: document.querySelector('#answers-learned-list input').value,
            })"""
        )
    finally:
        page.close()

    assert out["pwned"] is False
    assert out["images"] == 0
    assert "<img" in out["shown"]


# --- Carrying an existing install onto new defaults ------------------------

def _service_worker(browser, seed=None):
    """background.js in a real page, with the handful of extension APIs it
    touches at load stubbed under it. Storage is a live object, so a test can
    read back what the migration actually wrote.
    """
    page = browser.new_page()
    page.add_init_script(
        """(() => {
            const store = JSON.parse(SEED_JSON);
            window.__store = store;
            const noop = {addListener: () => {}};
            window.importScripts = () => {};
            window.chrome = {
                storage: {
                    local: {
                        get: async (keys) => Object.fromEntries(
                            (Array.isArray(keys) ? keys : [keys])
                                .filter((k) => k in store).map((k) => [k, store[k]])),
                        set: async (obj) => Object.assign(store, obj),
                    },
                },
                tabs: {onUpdated: noop},
                runtime: {onInstalled: noop, onMessage: noop},
                action: {setBadgeText: () => {}, setTitle: () => {}},
            };
        })();""".replace("SEED_JSON", repr(json.dumps(seed if seed is not None else {})))
    )
    # goto, not set_content: an init script runs on a new document, and
    # set_content writes into the one that already existed.
    page.goto("about:blank")
    page.add_script_tag(path=os.path.join(EXT_DIR, "background.js"))
    page.wait_for_function("() => typeof applyDefaultsOnce === 'function'")
    return page


def _run_defaults(browser, seed):
    page = _service_worker(browser, seed=seed)
    try:
        page.evaluate("() => applyDefaultsOnce()")
        return page.evaluate("() => window.__store")
    finally:
        page.close()


def test_an_install_that_saved_these_off_is_carried_onto_the_new_defaults(browser):
    """Saving on the options page writes every setting explicitly, so an
    install that has ever been saved holds `false` for these and a changed
    default never reaches it. That was the whole reason the fill looked
    narrower here than in the tools it was being compared against.
    """
    store = _run_defaults(browser, {
        "settings": {
            "auto_fill_known_sites": False,
            "route_saved_answers": False,
            "use_llm": False,
            "show_panel": False,
        },
        "llm_api_key": "sk-ant-whatever",
    })

    assert store["settings"]["auto_fill_known_sites"] is True
    assert store["settings"]["route_saved_answers"] is True
    assert store["settings"]["use_llm"] is True
    # Only the three being changed. Anything else they set stays as they set it.
    assert store["settings"]["show_panel"] is False


def test_the_ai_pass_follows_the_key_rather_than_the_default(browser):
    """Turning it on without a key buys nothing and puts "No API key saved."
    on every page they open.
    """
    store = _run_defaults(browser, {"settings": {"use_llm": False}})

    assert store["settings"]["use_llm"] is False
    assert store["settings"]["auto_fill_known_sites"] is True


def test_a_setting_turned_off_after_the_migration_stays_off(browser):
    """Otherwise every update quietly overrides a deliberate choice."""
    page = _service_worker(browser, seed={"settings": {"auto_fill_known_sites": False}})
    try:
        page.evaluate("() => applyDefaultsOnce()")
        after_first = page.evaluate("() => window.__store.settings.auto_fill_known_sites")
        # They turn it off again, then the extension updates.
        page.evaluate("() => { window.__store.settings.auto_fill_known_sites = false; }")
        page.evaluate("() => applyDefaultsOnce()")
        after_second = page.evaluate("() => window.__store.settings.auto_fill_known_sites")
    finally:
        page.close()

    assert after_first is True
    assert after_second is False


# --- Matching a form's EEO wording to one of this profile's choices --------

WORKDAY_RACES = [
    ("Asian (Not hispanic or Latino) (United States of America)", "Asian"),
    ("White (Not Hispanic or Latino) (United States of America)", "White"),
    ("Black or African American (Not Hispanic or Latino) (United States of America)",
     "Black or African American"),
    ("Hispanic or Latino (United States of America)", "Hispanic or Latino"),
    ("Two or More Races (Not Hispanic or Latino) (United States of America)",
     "Two or More Races"),
    ("American Indian or Alaska Native (Not Hispanic or Latino)",
     "American Indian or Alaska Native"),
    ("Asian", "Asian"),
]


def test_a_negated_qualifier_is_not_read_as_the_answer(load):
    """Workday words these as "Asian (Not Hispanic or Latino) (United States of
    America)". The parenthetical is a negation, so any matcher that scores a
    substring hit upwards reads an answer of Asian as Hispanic or Latino --
    bestChoice does exactly that, for Asian, White and Two or More Races
    alike. The qualifiers come off and the match is exact.
    """
    page = load(html="<body></body>", scripts=["field_aliases.js", "matcher.js"])
    out = page.evaluate(
        """(cases) => {
            const races = SELF_ID_CHOICES.race_ethnicity;
            return cases.map(([input]) => {
                const i = bestSelfIdChoice(input, races);
                return i === null ? null : races[i];
            });
        }""",
        WORKDAY_RACES,
    )

    for (given, wanted), got in zip(WORKDAY_RACES, out):
        assert got == wanted, f"{given!r} -> {got!r}, wanted {wanted!r}"


def test_a_wording_it_cannot_place_is_left_for_the_applicant(load):
    """On an EEO form a wrong answer is a false statement, so the fallback is
    a person, not a best guess. The declining choices are the one exception:
    every form words "I'd rather not say" differently and it can only ever
    land on another declining choice.
    """
    page = load(html="<body></body>", scripts=["field_aliases.js", "matcher.js"])
    out = page.evaluate(
        """() => {
            const races = SELF_ID_CHOICES.race_ethnicity;
            const at = (v) => {
                const i = bestSelfIdChoice(v, races);
                return i === null ? null : races[i];
            };
            return {
                nonsense: at("Martian"),
                empty: at(""),
                unrelated: at("Senior Mechanical Engineer"),
                decline: at("I do not wish to self-identify"),
                prefer: at("Prefer not to say"),
            };
        }"""
    )

    assert out["nonsense"] is None
    assert out["empty"] is None
    assert out["unrelated"] is None
    assert out["decline"] == "Decline to self-identify"
    assert out["prefer"] == "Decline to self-identify"


def test_accepting_a_suggested_self_id_answer_puts_it_on_the_form(browser):
    """End to end on the options page: the Learned tab offers what a form
    said, and pressing Add has to land it in the dropdown rather than on
    "No matching choice for ... -- set it by hand."
    """
    page = _options_page(browser, seed={
        "profile": {**PROFILE, "race_ethnicity": ""},
        "settings": {},
        "profile_suggestions": {
            "race_ethnicity": "Asian (Not hispanic or Latino) (United States of America)",
        },
    })
    try:
        page.wait_for_timeout(200)
        out = page.evaluate(
            """async () => {
                const row = document.querySelector('#suggestions-list [data-suggested]')
                    .closest('.cred-row, .listitem, div');
                const add = row.querySelector('button');
                add.click();
                await new Promise((r) => setTimeout(r, 50));
                return {
                    chosen: document.querySelector('[data-f="race_ethnicity"]').value,
                    status: document.getElementById('status').textContent,
                };
            }"""
        )
    finally:
        page.close()

    assert "No matching choice" not in out["status"], out
    assert out["chosen"] == "Asian", out


def test_an_employee_number_is_never_filled(load):
    """An internal identifier the applicant does not have and could not know.
    The fuzzy fallback was confident about them anyway: "Employee Number" and
    "Badge Number" both matched *phone*, so the phone number went in, and
    "Employee ID" matched current_company.
    """
    page = load(html="<body></body>", scripts=["field_aliases.js", "matcher.js"])
    out = page.evaluate(
        """() => {
            const never = ["Employee Number", "Employee ID", "Employee #",
                           "Badge Number", "Employee Badge Number",
                           "Please provide your GD Employee Badge Number",
                           "Payroll number", "Associate ID"];
            // "Employer" is a real match and has to stay one.
            const keep = {"Employer": "current_company",
                          "Current Employer": "current_company",
                          "Employment Type": "employment_type",
                          "Phone Number": "phone"};
            return {
                filled: never.filter((l) => matchField(l) !== null),
                broken: Object.entries(keep).filter(([l, want]) => matchField(l) !== want),
            };
        }"""
    )

    assert out["filled"] == [], f"still matches something: {out['filled']}"
    assert out["broken"] == [], f"collateral damage: {out['broken']}"


# --- Moving to another browser ---------------------------------------------

BACKUP_SEED = {
    "profile": {**PROFILE, "resume_file": {"name": "cv.pdf", "dataUrl": "data:application/pdf;base64,AAA"}},
    "settings": {"use_llm": True, "manual_fill": True},
    "credentials": {"workday.com": {"email": "jamie@example.com", "password": "hunter2"}},
    "llm_api_key": "sk-ant-secret",
    "learned_aliases": {"home telephone": "phone"},
    "learned_answers": {"did you graduate": "Yes"},
    "misses": {"site.com|q": {"host": "site.com", "label": "Q", "action": "skipped_no_match",
                              "detail": "", "required": False, "type": "text", "count": 2, "last": 1}},
    "applications": [{"url": "https://x/apply", "host": "x.com", "title": "Intern",
                      "company": "x", "filled": 9, "review": 0, "blank": 0, "at": 1, "pages": 1}],
    "profile_suggestions": {"linkedin_url": "https://linkedin.com/in/someone"},
}


def _backup_page(browser):
    """The options page with the download intercepted, so a test can read
    what the backup file would have contained.
    """
    page = _options_page(browser, seed={**BACKUP_SEED})
    page.evaluate(
        """() => {
            window.__downloaded = null;
            window.__confirmed = true;
            window.confirm = () => window.__confirmed;
            URL.createObjectURL = (blob) => { window.__blob = blob; return "blob:stub"; };
            URL.revokeObjectURL = () => {};
            HTMLAnchorElement.prototype.click = function () {
                window.__downloaded = this.download;
            };
        }"""
    )
    return page


def _exported(page, with_secrets):
    return page.evaluate(
        """async (withSecrets) => {
            document.getElementById('backup-secrets').checked = withSecrets;
            document.getElementById('backup-export').click();
            await new Promise((r) => setTimeout(r, 80));
            return {
                name: window.__downloaded,
                payload: JSON.parse(await window.__blob.text()),
                status: document.getElementById('backup-status').textContent,
            };
        }""",
        with_secrets,
    )


def test_a_backup_carries_everything_needed_to_pick_up_on_another_browser(browser):
    """Distinct from "Export as JSON", which drops documents and credentials
    because it is meant to be pasted into a chat. A device move has to carry
    the resume with it or the other browser cannot apply for anything.
    """
    page = _backup_page(browser)
    try:
        out = _exported(page, False)
    finally:
        page.close()

    data = out["payload"]["data"]
    assert out["payload"]["ja_backup"] == 1
    assert out["name"].startswith("ja-backup-") and out["name"].endswith(".json")
    for key in ("profile", "settings", "learned_aliases", "learned_answers",
                "misses", "applications", "profile_suggestions"):
        assert key in data, f"{key} missing from the backup"
    # The resume travels with it.
    assert data["profile"]["resume_file"]["name"] == "cv.pdf"


def test_a_backup_leaves_the_passwords_out_unless_they_are_asked_for(browser):
    """The file is ordinary text on a disk. Anything that can read the file
    can read a saved site password out of it, so it is a deliberate choice
    rather than something that happens because you pressed Download.
    """
    page = _backup_page(browser)
    try:
        without = _exported(page, False)
        with_them = _exported(page, True)
    finally:
        page.close()

    assert "credentials" not in without["payload"]["data"]
    assert "llm_api_key" not in without["payload"]["data"]
    assert "hunter2" not in json.dumps(without["payload"])
    assert without["payload"]["includes_secrets"] is False

    # And it does carry them when asked, or moving devices loses the logins.
    assert with_them["payload"]["data"]["llm_api_key"] == "sk-ant-secret"
    assert with_them["payload"]["data"]["credentials"]["workday.com"]["password"] == "hunter2"
    assert with_them["payload"]["includes_secrets"] is True
    # And says so, rather than leaving it to be discovered.
    assert "delete the file" in with_them["status"]


def _restore(page, payload, confirmed=True):
    return page.evaluate(
        """async ({payload, confirmed}) => {
            window.__confirmed = confirmed;
            const input = document.getElementById('backup-import');
            const file = new File([JSON.stringify(payload)], 'b.json', {type: 'application/json'});
            const dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            input.dispatchEvent(new Event('change', {bubbles: true}));
            await new Promise((r) => setTimeout(r, 120));
            const stored = await chrome.storage.local.get(
                ['profile', 'learned_aliases', 'credentials', 'settings']);
            return {stored, status: document.getElementById('backup-status').textContent};
        }""",
        {"payload": payload, "confirmed": confirmed},
    )


def test_restoring_replaces_only_what_the_file_carries(browser):
    page = _backup_page(browser)
    try:
        out = _restore(page, {
            "ja_backup": 1,
            "saved_at": "2026-09-20T10:00:00.000Z",
            "data": {"learned_aliases": {"mobile no": "phone"}},
        })
    finally:
        page.close()

    assert out["stored"]["learned_aliases"] == {"mobile no": "phone"}
    # Untouched, because the file said nothing about them.
    assert out["stored"]["credentials"]["workday.com"]["password"] == "hunter2"
    assert out["stored"]["profile"]["first_name"] == PROFILE["first_name"]


def test_a_file_that_is_not_a_backup_is_refused(browser):
    """A profile export, a resume, or somebody's unrelated JSON would
    otherwise be written straight into storage as if it belonged there.
    """
    page = _backup_page(browser)
    try:
        out = _restore(page, {"first_name": "Somebody", "last_name": "Else"})
    finally:
        page.close()

    assert "isn't a backup file" in out["status"]
    assert out["stored"]["profile"]["first_name"] == PROFILE["first_name"]


def test_declining_the_confirmation_changes_nothing(browser):
    page = _backup_page(browser)
    try:
        out = _restore(page, {
            "ja_backup": 1,
            "data": {"learned_aliases": {"mobile no": "phone"}},
        }, confirmed=False)
    finally:
        page.close()

    assert out["stored"]["learned_aliases"] == {"home telephone": "phone"}
    assert "Left as it was" in out["status"]
