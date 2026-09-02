# JA — Job Application Autofill

A CLI that opens a real browser to a job posting, autofills the application
form from your profile, and then **stops and hands control back to you** to
review and submit. It never clicks submit for you.

## Why autofill-only, not auto-submit

Many application platforms (Workday, Greenhouse, Lever, LinkedIn) prohibit
automated/unattended submission in their terms of service, and a bad field
match going out uncorrected is worse than a few minutes of manual review.
This tool optimizes the tedious part (retyping your name, address, work
history, links, resume upload on every single form) and leaves the judgment
calls — and the final click — to you.

It never *guesses* on self-identification questions either. The EEO
questions (gender, race, veteran and disability status) fill only from
answers you set yourself under Self-identification — nothing is inferred
from your name or resume, and anything you leave blank stays flagged for
you to answer by hand.

## Two ways to run this

- **The `extension/` folder** — a Chrome extension you load once, then click
  its toolbar icon on any job application page in your own everyday browser
  (already signed into whatever you're signed into). No Python, no separate
  browser window, no local server. See "Browser extension" below.
- **The Python CLI / web UI** (`apply.py`) — drives its own dedicated
  browser window via Playwright. More setup, but everything runs locally
  from a `profile.yaml` file rather than browser storage.

Both read the same rules (never auto-submit, never guess on self-ID/
criminal-history/salary-history questions) but keep entirely separate
profiles and local storage — filling in one does not fill in the other.

## Browser extension

Everyday use: load it once, then click its icon on any application page.

1. Open `chrome://extensions`, turn on **Developer mode** (top right).
2. Click **Load unpacked** and select the `extension/` folder in this repo.
3. Right-click the new toolbar icon → **Options**, and fill in your profile
   (first/last name, email, and phone are required; everything else is
   optional). Click **Save**.
4. On any job application page, click the toolbar icon. It fills what it
   can, outlines each field (green = filled, amber = flagged for you,
   red = required and left blank), and shows a summary in the corner.
   **Nothing is ever submitted for you.**

It injects into every frame on the page, not just the top one — plenty of
companies host the job posting on their own site and embed the actual
Greenhouse/Lever/iCIMS application in an iframe, and a top-frame-only
extension does nothing at all on those.

Your profile, settings, saved documents, and any saved site logins live in
this browser's own local extension storage — never synced to a Google
account, never sent anywhere except the job site being filled. The one
exception is the optional **AI assist** below, which is off until you turn
it on.

### Learned labels

Whenever Claude resolves a label to something already in your profile, that
mapping is remembered: *"Home Telephone" → phone*. The next form using that
wording matches for free and instantly, with no API call, so the tool gets
cheaper and faster the more you apply — without you teaching it anything.

Only mappings are learned, never written prose. A cover letter or an essay
answer belongs to the job it was written for, and reusing one at the next
company is exactly the failure worth avoiding.

Every mapping is listed on the **Learned** tab with a Forget button, plus a
"Forget everything" button. A mapping you delete is simply worked out again
the next time it comes up, so deleting one is never destructive.

### AI assist (optional, off by default)

The rule-based matcher knows the field phrasings in `field_aliases`. That
covers the common ones and costs nothing, but it is a fixed list, and forms
phrase things in endless ways. Turn on **Options → AI assist** and paste an
[Anthropic API key](https://console.anthropic.com/settings/keys): after the
normal fill, whatever is left unrecognised is sent to Claude along with your
profile, and its answers are filled in. That covers arbitrary phrasings and
the open-ended essay questions in one step. A typical application costs a
few cents, billed to your own account.

Your profile is what it works from — not general knowledge, and not a guess.
Rule one of the prompt is that every answer must be supported by something
in your profile, and that a field the profile can't answer comes back blank
with a reason rather than invented.

This is the one part of the tool that leaves your machine. What goes to the
API: the labels of the unfilled fields on the page, and your Contact,
Background, Eligibility, Education & Work tabs. Your written Answers go too,
but only when the page actually asks an open-ended question. What does not
go: your resume and cover-letter files, your saved site logins, your API
key, and your Self-ID and criminal-history answers — Claude is never asked
one of those questions, so no request could need them.

It is told what job this is — the role title, the company, and the posting
text if the page still shows it — so an answer to "why do you want this
role?" is about *this* role rather than being generically about you. Two
optional extras build on that:

- **Write a cover letter for each job** drafts one per application from the
  posting and your profile, instead of pasting the single saved letter from
  the Background tab into every form.
- **Fill automatically on known job sites** fills each page as it loads on
  Workday, iCIMS, Greenhouse, Lever, Ashby, SmartRecruiters and the rest, so
  a six-page Workday application is one pass instead of six clicks. Off until
  you turn it on, since it spends API credit without a click. Still never
  submits.

The guarantees don't change, and they are enforced in `filler.js` on the way
back in rather than merely asked of the model:

- The set of fields offered to Claude is built locally. Self-identification,
  criminal-history, salary-history and consent questions are never in it,
  however they are phrased and whether they are text boxes, dropdowns or
  radio buttons. Checkboxes are never in it at all — a single tick box is
  how forms ask you to agree to something.
- A radio answer must be one of that group's own choices; anything else
  selects nothing.
- An answer for a field that wasn't offered is dropped, not applied.
- A dropdown answer must match one of its options exactly; the near miss is
  left blank instead, because picking the wrong item out of a list is worse
  than leaving it for you.
- Everything it fills is outlined green and listed in the summary as
  answered by Claude, so you know what to read before submitting.
- Nothing is submitted, same as ever.

The API key is stored separately from your profile, so it is never part of
an export, an import, or the profile sent to the API.

**Resume and cover letter**: upload them once under Options → Documents.
When a job form has a resume/cover-letter upload field, the saved file is
attached automatically (green outline) instead of being flagged. Under the
hood this constructs a real `File` object from the bytes you uploaded and
assigns it to the field via the browser's `DataTransfer` API — the same
mechanism testing tools use to simulate a real file pick — which is
different from (and, unlike setting `.value` on a file input directly,
allowed for) ordinary extension JavaScript.

**Importing education/work history from a resume**: paste your resume's
text to Claude and ask for a JSON snippet shaped like
`{"education": [...], "experience": [...]}` (matching the fields on the
Education & Work tab), then paste that into the Documents tab's import box.
There's no in-browser resume parser — this reuses Claude's own reading of
your resume rather than a fragile heuristic parser, so it's worth a quick
review of the imported rows before saving.

**Open-ended questions**: the Answers tab's "+ Add top 50 common questions"
button adds ~50 rows for the recurring essay-style prompts job forms ask
("Why do you want to work here?", "Tell us about yourself", "Describe a
challenge you overcame", ...) with the keyword already filled in and the
answer left blank for you to write yourself. Nothing here is ever answered
on your behalf — this only saves you the setup of typing each keyword, not
the actual answer, since only you know what you'd honestly say.

## Setup

Requires Python 3.10+. On macOS, run `python3 --version` first; if it's
missing, `xcode-select --install` provides it.

Use a virtual environment — on macOS and most Linux distros a bare
`pip install` either isn't on PATH or is refused with
"externally-managed-environment":

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Inside the venv, `pip`, `playwright`, and `python` all work as written
above. **Each new terminal session needs `source .venv/bin/activate`
again** before running `apply.py`, otherwise you'll get
`ModuleNotFoundError: No module named 'playwright'`.

Then set up your profile:

```bash
cp profile.example.yaml profile.yaml
mkdir documents                    # put resume.pdf / cover_letter.pdf here
# edit profile.yaml with your real details, then:
python apply.py validate
```

`profile.yaml` and `documents/` are gitignored — your personal data and
files are never committed.

Note that `validate` fails if `resume_path` or `cover_letter_path` points
at a file that doesn't exist; either add the file or blank the path out.

If `playwright install` isn't an option, point the tool at a Chrome or
Chromium you already have:

```bash
python apply.py fill --url "..." --browser-path /usr/bin/google-chrome
# or: export JA_BROWSER_PATH=/usr/bin/google-chrome
```

## The easy way: double-click, no terminal

**Double-click `JobApply.command`** in Finder. It sets everything up the
first time (a few minutes), then opens a local page in your browser where
you can:

- edit your whole profile in a form — no YAML, no text editor
- paste a job URL and click **Fill this application**
- see what filled, what needs your answer, and what's still blank
- click **Re-fill this page** after clicking Next on a multi-page form

The page runs on `127.0.0.1` only. Nothing is sent anywhere.

macOS may warn the first time because the file came from the internet:
right-click it → **Open** → **Open** to allow it once.

To start it from a terminal instead: `python apply.py ui`

## Usage

```bash
python apply.py fill --url "https://boards.greenhouse.io/example/jobs/12345"
```

A browser window opens, navigates to the URL, and fills in every field it
can confidently match. A report prints to the terminal:

```
Detected platform: greenhouse

Filled (8):
  ✓ First Name  ->  first_name  [Jane]
  ✓ Email  ->  email  [jane.doe@example.com]
  ✓ Resume  ->  resume_path  [documents/resume.pdf]
  ...

Needs your review (1):
  ! Gender  -  Self-identification question: set your answer under
                Self-identification in your profile, or answer it here.

Required fields left blank (1):
  ✗ Why do you want to work here?  -  no matching profile field
```

The browser stays open and the terminal offers:

```
[r] re-fill this page (use after clicking Next on a multi-page form)
[n] done with this application
[q] quit
```

Review everything, answer the flagged questions, fix anything mismatched,
and click submit yourself.

### Multi-page forms (Workday)

Workday and similar platforms reveal fields a page at a time. Click **Next**
in the browser, then press **`r`** in the terminal to re-scan and fill the
newly revealed fields. Repeat per step.

Re-filling never overwrites a field that already has a value — anything you
corrected by hand stays as you left it, and those fields are reported as
"already filled, left untouched".

Some resume-upload widgets (JazzHR's "Attach resume" / "Paste resume"
toggle is one) keep the actual file input hidden until you click a link
to reveal it — click that link once in the browser, then hit "Re-fill this
page" (or `r`) so the tool can see and use the now-visible field.

### Dates

Store `notice_period` in your profile in whatever format is easiest —
`2027-05-11`, `05/11/2027`, and `May 11, 2027` are all understood. At fill
time it's converted to whatever the actual field needs: `YYYY-MM-DD` for a
native date picker, `MM/DD/YYYY` (the standard US convention) for a plain
text field driven by a JS datepicker widget.

### Disability/veteran self-ID signature blocks

The federal CC-305 disability form (and the standard veteran
self-identification section) ends with a plain "Name" and "Date" pair —
your signature on that specific self-certification. These are filled with
your full name and today's date, but **only** when "Name"/"Date" sit next
to a disability, veteran, or signature question specifically — an
unrelated "Name" or "Date" field elsewhere on a form (a reference's name, a
document date) is never touched by this.

### Using your own Chrome

By default the tool drives the Chromium that `playwright install` downloads,
with no logins or history. To use the Google Chrome already on your machine:

```bash
python apply.py fill --url "..." --chrome
```

To keep logins between runs (useful for Workday sites that make you create
an account per company), give it a profile folder of its own:

```bash
python apply.py fill --url "..." --chrome --user-data-dir ~/.ja-chrome-profile
```

The first run signs you in; later runs remember. Use a dedicated folder like
this rather than your real Chrome profile — Chrome permits only one process
per profile directory, so pointing at your everyday profile means quitting
Chrome entirely (Cmd+Q) before every run.

### Seeing what it missed

```bash
python apply.py fill --url "..." --verbose
```

Adds a list of every optional field left blank, with the exact label wording
the page used. That's what you need to extend `ja/field_aliases.py` (for
fields it should recognize) or add a `custom_answers` entry (for open-ended
questions).

### Batch mode

Work through a list of postings in one browser session:

```bash
python apply.py batch --urls urls.txt
```

`urls.txt` is one application URL per line; blank lines and `#` comments
are ignored. Each posting is filled and then waits for you — press `n` to
move to the next one, `q` to stop. A URL that fails to load is reported and
the batch continues.

Validate your profile file without opening a browser:

```bash
python apply.py validate --profile profile.yaml
```

## Supported platforms

Field matching works by reading each input's visible label (or, for
Workday's `data-automation-id`-based forms, deriving one from that
attribute) and comparing it against a table of known phrasings — so it
works the same way across ATS platforms:

- **Greenhouse** (`boards.greenhouse.io`)
- **Lever** (`jobs.lever.co`)
- **Workday** (`*.myworkdayjobs.com`)
- **Generic** — any other HTML form, best-effort

Run `python apply.py fill` on an unrecognized site and it still tries; you
just get more "no matching profile field" entries to fill in by hand.

## What it can answer

**Identity & contact** — first/middle/last name, preferred name, email,
phone, full address, LinkedIn, GitHub, portfolio.

**Education** — school, degree, field of study, graduation year, GPA (taken
from the first `education` entry, for forms that ask for one flat school).

**Employment** — current/most-recent employer and title, years of
experience, desired salary, earliest start date, preferred location,
employment type, security clearance, how you heard about the role.

**Yes/no screening questions** — the set nearly every application asks:

| Question | Profile field |
|---|---|
| Legally authorized to work? | `work_authorized` |
| Need visa sponsorship? | `needs_sponsorship` |
| Willing to relocate? | `willing_to_relocate` |
| At least 18 years old? | `over_18` |
| Valid driver's license? | `has_drivers_license` |
| Willing to travel? | `willing_to_travel` |
| Consent to a background check? | `consent_background_check` |
| Consent to a drug screening? | `consent_drug_test` |
| Can perform essential functions? | `can_perform_essential_functions` |
| Previously employed here? | `previously_employed_here` |

Each works against Yes/No radio groups and single checkboxes. Any field left
unset is skipped and reported — never guessed.

Leave `previously_employed_here` unset: it's company-specific, so one saved
answer is wrong at any employer you actually have worked for.

**Open-ended questions** go in `custom_answers`, matched by keyword against
the question text — `"why do you want to work here"` catches most phrasings.

### Self-identification (EEO)

The voluntary demographic questions almost every application asks: gender,
pronouns, Hispanic/Latino, race/ethnicity, protected veteran status,
disability status, sexual orientation, transgender status.

These fill **only** from an answer you set yourself under
Self-identification, using the standard option wordings that Greenhouse,
Lever, Workday and JazzHR use. Nothing here is ever inferred from your name,
your resume, or anything else, and any field left blank keeps its question
flagged for you to answer by hand — which stays the default.

### Questions you answer once, yourself

Self-identification, criminal history and SMS consent are never *guessed* —
but they are filled from an answer you set by hand, so you don't retype the
same thing on every application:

- **Self-ID** (race, gender, veteran, disability, pronouns, ...) — the
  Self-ID tab. Left "Not set", the question stays flagged on every form.
- **Criminal history** — Eligibility tab, "Has a criminal conviction to
  disclose". Left unset, flagged every time. Note that these questions are
  scoped differently from form to form (felony vs. misdemeanour, last seven
  years, sealed/expunged records, state ban-the-box rules), so a single
  saved yes/no won't be right for every phrasing — it is outlined like
  everything else, and worth reading before you submit.
- **SMS consent** — Eligibility tab.

Each gate only opens for a profile field belonging to that same group: a
criminal-history answer can never be used for a demographic question, or the
other way round. The AI-assist pass never sees any of these fields, so
nothing here is ever inferred from your name, your resume, or the page — it
is only ever what you wrote down.

### Never auto-filled

Always flagged, whatever the profile says:

- **Criminal history** — what employers may lawfully ask varies by state and
  city, and the consequences of a wrong stored answer are serious
- **Salary history** — illegal for employers to ask in many states

### Browser and sign-in

On the My Profile tab:

- **Use my Google Chrome** — drive the Chrome installed on your machine
  rather than the bundled Chromium.
- **Stay signed in between applications** — keep cookies in a browser
  profile of the tool's own (`~/.ja-browser-profile`), so sites you sign
  into once stay signed in. Useful for Workday, which wants an account per
  company. You sign in inside the window that opens; no password is stored
  by this tool or sent anywhere.

A dedicated profile folder is used rather than your everyday Chrome profile
because Chrome permits only one process per profile directory — pointing at
your real one would mean fully quitting Chrome before every run. If you'd
rather use your actual everyday Chrome profile anyway, the CLI supports it
via `--chrome --user-data-dir ~/path/to/your/profile` (fully quit Chrome
first); the web UI always uses the dedicated profile.

- **Automatically create accounts** — some ATS platforms (iCIMS
  especially) put a "create a candidate account" gate — a Login and
  Password field — in front of the real application form. When this is
  on, the tool generates a strong random password the first time it sees
  a site, fills the Login field with your email, fills every password
  field on the page with the generated password, and saves the pair so
  the same site reuses it next time instead of creating a new account
  each visit. Saved logins are stored in `credentials.json` next to your
  profile (gitignored, plaintext, never transmitted anywhere but the site
  itself) and keyed by the exact site hostname, since several unrelated
  companies can share the same underlying ATS domain (e.g. many different
  employers each run their own careers site on `*.icims.com`) but keep
  separate candidate databases. `credentials.json` is a convenience store
  for your own machine, not a hardened password manager — if you want
  extra protection, keep it on an encrypted disk (FileVault on macOS is
  on by default on modern Macs). View or forget saved site logins under
  Browser & Sign-in in the web UI.

## Profile fields

See `profile.example.yaml` for the full list with comments. Highlights:

- Contact info, address, links (LinkedIn/GitHub/portfolio)
- `resume_path` / `cover_letter_path` — used for file-upload fields whose
  label mentions "resume"/"CV" or "cover letter"
- `work_authorized` / `needs_sponsorship` / `willing_to_relocate` — yes/no
  fields, matched against both single checkboxes and Yes/No radio groups
- `custom_answers` — a map of `{keyword: answer}` for recurring open-ended
  questions (e.g. "why do you want to work here"); matched by substring
  against the question label

## Extending field matching

If a field on a specific site isn't being recognized, add its phrasing to
`ja/field_aliases.py` under the relevant canonical field name — no other
code changes needed. `tests/test_matcher.py` has examples of the matching
behavior.

## Testing

`pytest tests/` runs the whole suite. Most of it (`test_matcher.py`,
`test_filler.py`, `test_profile.py`, `test_credentials.py`) drives the
Python matching/filling logic against hand-built field data, no browser
needed. `test_extension_regression.py` is different: it runs the
**browser extension's** JS logic — including the AI-assist guardrails,
against a stubbed `fetch` so no key and no network are needed — against
saved copies of real job application forms (`tests/fixtures/*.html`, personal data scrubbed) in a
real headless Chromium via Playwright, since bugs there tend to be DOM
behavior quirks (a `<select>`'s `selectedIndex`, computed-style visibility)
that hand-built field data can't reproduce. It needs
`playwright install chromium` first, same as the CLI, and skips cleanly
with a clear message if Chromium isn't available rather than failing.

If you hit a new real-site bug, the fix belongs in **both**
`ja/extractor.py`/`ja/matcher.py`/`ja/filler.py` (the Python/Playwright
side) **and** their `extension/*.js` ports — the two are kept in sync by
hand, not shared code. The one standing exception is custom-widget dropdown
support (below), which is extension-only: driving those needs
click-open-and-wait interaction that the Python side's one-shot
extract-then-fill pipeline has no place for. Add (or extend) a fixture under `tests/fixtures/`
and an assertion in `test_extension_regression.py` so the fix stays fixed;
these are frozen snapshots of forms at a point in time, not a live check
against the real site, so a company changing their form later won't be
caught by a still-green test — the safety net only knows what it's shown.

## Limitations

- Multi-page forms need a manual `r` press per step (see above); the tool
  doesn't click "Next" for you, by design.
- Salary-history questions are still always flagged and have no profile
  field to set, since most states now bar employers from asking.
- Fields go to the optional AI assist only if the deterministic matcher
  couldn't place them; with it off, an unrecognised field is simply reported
  as unfilled. It can't fill checkboxes or radios by design (see above), so
  an unusually-phrased Yes/No radio question still needs you.
- Custom dropdown widgets are handled in the **extension only**, and only
  the two patterns that have actually turned up:
  - **Workday** asks its questionnaire with `<button aria-haspopup="listbox">`
    — no `<select>`, and no options anywhere in the DOM until the button is
    clicked. The extension opens each one, reads the popup it renders, picks,
    and closes anything it didn't answer. Driven off the ARIA contract, not
    Workday's class names, so it should hold for other `aria-haspopup`
    dropdowns too.
  - **iCIMS** keeps a real `<select>` that is `display:none` and empty, and
    puts the real choices in a sibling `<ul>` of `<li role="option">`. Long
    lists (schools, countries) ship only their first page and fetch the rest
    through the widget's own search box, which the extension types into when
    nothing on the loaded page matches exactly.

  Any other custom widget that doesn't use real `<input>`/`<select>` elements
  is still invisible to both sides.
- Inside a work-history block the fields are matched by section and label
  ("Employer", "City", "Start Date"), and anything in there that isn't
  recognised is deliberately left alone rather than filled from your personal
  details — the Address/City/State boxes in that block are the employer's.
- This is a heuristic label matcher, not a guarantee — always check the
  report and the form itself before submitting.

## Responsible use

- Respect each site's terms of service and robots directives.
- Don't use this to blast out large volumes of low-effort/spam applications.
- Review every field — especially free-text answers — before submitting.
