# Handoff

State of this project as of 2026-09-17, written so a new conversation can
pick it up without re-deriving any of it. Branch:
`claude/happy-volta-yjo3xc`. 179 tests passing, the whole suite green.

If you are Claude and someone has just pointed you here: read this file, then
`README.md` for the user-facing description. Don't re-read the whole codebase
first — the map below tells you which three files matter for most changes.

---

## What this is

A browser extension that fills in job applications for one person (Zi Hung
Chen, a mechanical engineering student applying to 2027 internships). It is
**not** an auto-applier. Its whole posture is: fill what it can, mark
everything it did, stop.

### The rules that don't get relaxed

These have survived every round of "make it do more", and each is enforced in
code with a test, not by prompting:

1. **Never submits.** No code path clicks a submit control.
2. **Never guesses on self-identification, criminal history or salary
   history.** These fill only from an answer the user set themselves under
   Options. Unset means flagged, on every form, forever.
3. **Never consents on their behalf.** Same rule: only from a saved answer.
4. **Nothing is inferred from their name or resume.** The AI pass may *route*
   a saved answer to an oddly-worded question; it may never decide one. An
   answer that doesn't trace back to something they saved is dropped in
   `filler.js` before it reaches the page.
5. **A learned label mapping may never point at a sensitive field.** Learned
   aliases are consulted before every other check, so one pointing at
   `hispanic_latino` would bypass the sensitive gate entirely. This was a real
   bug (commit `3721399`) — read that commit before touching learning.
6. **No real personal data in the repo.** Test fixtures use a fake identity
   (`tests/fixtures/profile.json`, "Jamie Rivera"). Real forms captured as
   fixtures have had emails and OAuth state scrubbed.

---

## Map

Two parallel implementations exist. **The extension is the live one.** The
Python CLI (`ja/*.py`) is older, still passing its tests, and deliberately
behind — custom-widget dropdowns and everything AI-related are extension-only.
Don't spend effort syncing them unless asked.

```
extension/
  manifest.json     MV3. host_permissions covers api.anthropic.com + 16 ATS domains.
  background.js     Service worker. Injects on click and on ATS page load.
                    Owns all chrome.storage writes. Routes API calls to llm.js.
  run.js            Entry point injected into every frame. Orchestrates the
                    whole sequence. Read this first to understand the flow.
  extractor.js      DOM -> field descriptors. Labels, options, sections.
  matcher.js        Label -> canonical profile field. Aliases, fuzzy, learned.
  field_aliases.js  The alias table + the sensitive/consent group definitions.
  filler.js         ~1700 lines. The fill itself, all the guards, all learning.
  llm.js            Claude API. Runs in the service worker only (API key).
  panel.js          The on-page side panel, in a shadow root. Draggable by its
                    header; position kept in chrome.storage under `panel_pos`,
                    never the page's own localStorage.
  options.js/html   The Options page. 11 tabs. Loads matcher.js too, for
                    bestSelfIdChoice.
tests/
  conftest.py                  Shared browser fixture + `load` helper.
  test_extension_regression.py Behaviour against saved real forms.
  test_hardening.py            Adversarial input. Most of it found real bugs.
```

**For most changes you only need `filler.js`, `matcher.js` and one test file.**

---

## How it works

### Two buttons, not one automatic fill

`run.js` wraps the whole fill in `doFill()`, wired to the panel's **Autofill**
button and called on arrival unless `manual_fill` is set. The reason is
coexistence: another autofill extension on the same page (Simplify) listens
for the same change events this fires, both write to the same fields, and
they overwrite each other — on Blue Origin every core field came back
cleared. Manual mode makes it a choice per form: **Autofill** when this is
the tool doing the filling, **Learn this form** when the other one already
did it and its answers are worth keeping.

`report` is null until a fill has run, so everything downstream of it
(watch-and-learn, the chat) is guarded. run.js is not loaded by the browser
fixtures — `test_the_fill_is_a_function_the_button_can_call...` checks that
shape statically, so it is the thing to update if this is restructured.

### The fill, in order (`run.js`)

1. Bail immediately if the frame has no form controls (runs in every frame).
2. Load profile, settings, learned stores from `chrome.storage.local`.
3. Draw the panel (top frame only).
4. `fillForm()` — the deterministic pass. Alias matching, per-widget filling.
5. **AI pass** (if on): `llmFieldsFor(report)` builds the offered set locally,
   sends it to Claude via the service worker, applies answers through
   `applyLlmAnswers()` which re-checks every guard.
6. `verifyFilled()` — re-read every filled field ~350ms later, re-apply once,
   downgrade to `needs_review` if the page cleared it.
7. Learn: from Claude's answers, from what was already on the page, and
   (ongoing) from what the user types afterwards.
8. Record misses and the application row. Render results in the panel.

### Custom widgets (the hard-won part)

- **Workday** asks questions with `<button aria-haspopup="listbox">` — no
  `<select>`, no options in the DOM until clicked. Driven off the ARIA
  contract, not Workday's class names. `_openListbox()` in `filler.js`.
- **iCIMS** hides the real `<select>` (`display:none`, one empty option) behind
  its own widget, with choices in a sibling `<ul>` of `<li role="option">`.
  Long lists are paged and fetched through its search box. `icimsWidget()` in
  `extractor.js`, `_setIcimsValue()`/`_icimsSearch()` in `filler.js`.
- Both have frozen fixtures: `workday_questions.html`, `icims_profile.html`.

### Learning (three stores, different rules)

| Store | Holds | Written from |
|---|---|---|
| `learned_answers` | label -> answer text | Questions the profile has no field for |
| `learned_aliases` | label -> profile field | Claude's declared `profile_field` |
| `profile_suggestions` | profile field -> value | Gaps found on the page; **suggested, never written** |

Sensitive and consent answers go **only** to `profile_suggestions`, never to
`learned_answers`. That routing is the safety property — see rule 5.

**Learn this form** (the panel button, `learnFromPage` in `filler.js`) reads
a form the applicant filled in by hand and stores every answer in it,
setting nothing on the page. It builds a report in which nothing was filled
and hands it to `learnFromPrefilled`, so it inherits that same routing
rather than carrying a second copy of the gate. Wired in `run.js` via
`panel.onLearn`.

Capped in `background.js` (`capLearned`, `capMisses` in `llm.js`).

### Settings (all in `chrome.storage.local.settings`)

| Key | Default | What it does |
|---|---|---|
| `use_llm` | off, on once a key is saved | The AI pass at all. Needs `llm_api_key`. |
| `route_saved_answers` | **on** | Let Claude route saved answers to sensitive/consent questions (no effect unless `use_llm`) |
| `tailor_cover_letter` | off | Draft a letter per job instead of the saved one |
| `auto_fill_known_sites` | **on** | Inject and fill on page load across 16 ATS domains |
| `manual_fill` | off | Open the panel but fill nothing until **Autofill** is pressed |
| `watch_and_learn` | **on** | Notice what the user types into blanks |
| `show_panel` | **on** | The side panel |
| `auto_create_accounts` | off | Generate a password per site |

A changed default only reaches an install that has never opened Options:
saving there writes every key explicitly. `applyDefaultsOnce()` in
`background.js` carries an existing install over on update, once, recorded
under `migrations` so a setting turned off afterwards stays off. Add a new
key there rather than only changing a default, or the change reaches nobody
who already has this installed.

---

## Testing

```bash
export JA_BROWSER_PATH=/opt/pw-browsers/chromium   # only if the default fails
python3 -m pytest tests/ -q
```

Tests run the extension's real JS in real headless Chromium. Most bugs here
are DOM-behaviour bugs a mock can't reproduce.

**Two lessons learned the hard way, both worth keeping:**

1. **Verify a new test actually fails without the fix.** Twice in this project
   a test passed for the wrong reason — once because it took a browser fixture
   it didn't need and silently skipped, once because the fixture offered
   nothing so the assertion was vacuous. Break the code, watch it fail, then
   restore.
2. **Assert non-emptiness before asserting absence.** `assert "felony" not in
   offered` passes trivially when `offered == []`.

---

## Known limitations

- **Coverage is empirical and narrow.** Tuned against ~6 real forms the user
  pasted. Simplify has telemetry from millions. This is the structural gap and
  it does not close by cleverness.
- **Fixtures are frozen snapshots.** A green test does not mean the real site
  still looks like that.
- **The Claude API path has never run live.** No key available in the dev
  environment. Request shape, headers, retry and error handling are tested
  against a stubbed `fetch`; the actual round trip is unverified.
- **SPA re-renders drop watch-and-learn listeners** when elements are replaced.
- **Corrections are still not learned automatically.** `watchForCorrections`
  skips every field the fill touched (`filler.js`, the `filled.has(...)`
  guards), so a wrong fill the applicant fixes by hand teaches nothing on
  its own. **Learn this form** is the manual answer to that and covers the
  case in practice; doing it without the button press is still open.
- **Context bleed mislabels questions.** `wideContext()` keeps up to 4000
  characters of surrounding text and the sensitive gate reads it, so an
  iCIMS search box was flagged as a self-identification question 7 times
  and a terms-and-conditions tick box as criminal-history 3 times.
  Narrowing the gate to label + group label was tried and reverted: an LDG
  legend had swallowed "Veteran status" from a neighbouring block, which
  made an SMS consent box demographic. `ldg_form.html`'s baseline caught
  it. Needs those two forms as fixtures before trying again.
- **Blue Origin clears every core field after it is filled** — 13
  occurrences across first/last name, address, city, postal code, phone.
  `verifyFilled` re-applies once and still loses. What the report proves is
  narrower than it looks: the re-read after the second write is synchronous,
  so the value is gone *as it is set*, not on a later re-render — the site's
  own change handler is rejecting it. `_setNativeValue` already does the
  native-setter-plus-events dance, so it is not the usual React-controlled-
  input problem. Needs a saved copy of that page to go further.
- `NOT_APPLICABLE_FIELDS` in `field_aliases.js` holds the fields this
  applicant hasn't got (middle name, address line 2). Blank is the answer
  for those, so they are neither typed into nor counted as gaps. Add to it
  rather than teaching the matcher to miss them.
- **A hidden control needs something visible standing in for it** before the
  extractor will surface it — an iCIMS `<select>` behind its widget anchor,
  a `display:none` file input behind an "Upload Resume" button
  (`uploadProxy` in `extractor.js`). The file-input rule is deliberately
  narrow: no id, no name, no aria-label, and a visible control beside it
  whose text says what it is for. A labelled hidden file input is still
  skipped; widen it from a real form, not from a guess.
- **The panel only draws in the top frame**, so a form inside an iframe fills
  correctly but reports through the badge only.
- `ja/*.py` lacks all widget and AI support. Intentional.

---

## Where to pick up

The user has been told, correctly, to **stop building and go apply**. Don't
propose new features unprompted. The intended next loop is data-driven:

1. They apply to things, using this alongside Simplify (either order — it
   learns from already-filled fields now).
2. **Options -> Gaps** accumulates every question it couldn't answer, counted
   across applications, exportable as CSV.
3. They hand that CSV over. The top of it — a label unfilled thirty times — is
   what to work on. A label seen once is not.

That converts "paste me some HTML and hope" into a ranked worklist. It is the
only thing that meaningfully narrows the coverage gap.

If they report a bug instead: reproduce it in a fixture first. Every real fix
in this project came from a faithful local reproduction, never from reasoning
about what the site probably does.

### Open threads, none urgent

- Multiple profiles for different role types.
- Cross-frame panel aggregation (form in an iframe reports through the badge
  only).
- `misses` could feed alias suggestions automatically rather than via CSV.

---

## Conventions

- Work on `claude/job-application-automation-tp32l1`. Commit and push when a
  change is complete and tests pass.
- Commit messages explain **why**, including what was wrong before. Several in
  the log are worth reading as documentation — `3721399` (the sensitive-alias
  bug), `d82538f` (seven bugs from hardening), `423eecb` (the options page
  never rendering).
- Comments explain the reason a thing is the way it is, not what the line does.
  The codebase is consistent about this; match it.
- Don't add attribution or model names to anything pushed to the repo beyond
  the existing commit trailers.
