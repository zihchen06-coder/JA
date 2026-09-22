# Handoff

State of this project as of 2026-09-22, written so a new conversation can
pick it up without re-deriving any of it. Branch:
`claude/new-session-n7suz1`. 180 tests passing.

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
7. **Nothing fails in silence.** One field that throws is that field's own
   result, not the end of the fill (`_handleSimpleField`); a run that throws
   anywhere draws a banner saying so (`run.js`); a section of the Options
   page that throws doesn't take the sections after it (`_section`). Silence
   reads as "the extension did nothing", and what comes next is submitting a
   form the applicant believes was filled.

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
  panel.js          The on-page side panel, in a shadow root.
  options.js/html   The Options page. 11 tabs. Each section renders on its
                    own, so one bad stored value can't blank the page.
  profile_check.js  What a form will do with what's saved: the findings
                    shown above the Save bar. Options page only.
tests/
  conftest.py                  Shared browser fixture + `load` helper.
  test_extension_regression.py Behaviour against saved real forms.
  test_hardening.py            Adversarial input. Most of it found real bugs.
```

**For most changes you only need `filler.js`, `matcher.js` and one test file.**

---

## How it works

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

### Learning (four stores, different rules)

| Store | Holds | Written from |
|---|---|---|
| `learned_answers` | label -> answer text | Questions the profile has no field for |
| `learned_fields` | markup token -> {answer, label, host} | **Learn this page**; survives a reworded question |
| `learned_aliases` | label -> profile field | Claude's declared `profile_field` |
| `profile_suggestions` | profile field -> value | Gaps found on the page; **suggested, never written** |

Sensitive and consent answers go **only** to `profile_suggestions`, never to
`learned_answers` or `learned_fields`. That routing is the safety property —
see rule 5. Both of those stores are consulted before the gate that reads
what a question is asking, so an answer sitting in either is a way straight
past it: a markup match says "this is the same box", which is no reason to
answer a question that has to be answered by hand.

**Learn this page** (the panel button, `learnPageNow` in `filler.js`) reads
the DOM as it stands when it is pressed, which is the point. The watcher set
up after a fill can only watch fields that existed at fill time, so the next
step of a Workday application, anything rendered late, and any page reached
without clicking the icon were all unlearnable — most of what there was to
learn. A markup token comes from `data-automation-id`, `name` or `id` with
generated indices and uuids stripped and generic words ("input", "answer",
"field") dropped: `markupToken` in `matcher.js`. `--phoneNumber` becomes
"phone number"; `input-14` becomes nothing, on purpose.

Capped in `background.js` (`capLearned`, `capMisses` in `llm.js`).

### Backup and restore (Options page)

"Export profile" writes the profile as it is on the page; "Export
everything" adds the settings and the four stores. Neither carries the
saved documents, the site logins or the API key -- too large, too
sensitive, and the file is meant to be pasted into a chat.

The import takes either one, plus the `{fields: ...}` shape a resume parse
returns. Two rules hold whatever the file says: only keys the file actually
carries are written, so a restore never wipes what it doesn't mention, and
`learned_aliases` goes through `sanitizeLearnedAliases` first -- an alias is
consulted before every other check in `matchField`, so an imported one
pointing at a self-ID field would be a way straight past the gate. That
function and `UNLEARNABLE_FIELDS` live in `field_aliases.js` because the
fill and the Options page both need them and share nothing else.

### Settings (all in `chrome.storage.local.settings`)

| Key | Default | What it does |
|---|---|---|
| `use_llm` | off | The AI pass at all. Needs `llm_api_key`. |
| `route_saved_answers` | off | Let Claude route saved answers to sensitive/consent questions |
| `tailor_cover_letter` | off | Draft a letter per job instead of the saved one |
| `auto_fill_known_sites` | off | Fill on page load across 16 ATS domains |
| `watch_and_learn` | **on** | Notice what the user types into blanks |
| `show_panel` | **on** | The side panel |
| `auto_create_accounts` | off | Generate a password per site |

---

## Testing

```bash
export JA_BROWSER_PATH=/opt/pw-browsers/chromium   # only if the default fails
python3 -m pytest tests/ -q
```

One browser for the whole suite, from `conftest.py`. Don't add a second
`sync_playwright()` in a test module: two live at once is an error, and the
one that used to be in `test_extension_regression.py` only worked because
that file sorted before every other browser test.

Tests run the extension's real JS in real headless Chromium. Most bugs here
are DOM-behaviour bugs a mock can't reproduce.

A test needing a binary fixture builds it itself (see `_docx_bytes`). The one
that read a saved `sample_resume.docx` could never pass in a fresh clone: the
`*.docx` line in `.gitignore`, there to keep the applicant's real resume out
of the repo, had silently kept the fixture out of every commit too.

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

- Work on `claude/new-session-n7suz1`. Commit and push when a
  change is complete and tests pass.
- Commit messages explain **why**, including what was wrong before. Several in
  the log are worth reading as documentation — `3721399` (the sensitive-alias
  bug), `d82538f` (seven bugs from hardening), `423eecb` (the options page
  never rendering).
- Comments explain the reason a thing is the way it is, not what the line does.
  The codebase is consistent about this; match it.
- Don't add attribution or model names to anything pushed to the repo beyond
  the existing commit trailers.
