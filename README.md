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

It also **never** guesses on self-identification questions (race, gender,
veteran status, disability, sexual orientation). Those are always flagged
for you to answer by hand, regardless of what's in your profile.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium

cp profile.example.yaml profile.yaml
# edit profile.yaml with your real details
```

`profile.yaml` is gitignored — it's never committed.

If `playwright install` isn't an option, point the tool at a Chrome or
Chromium you already have:

```bash
python apply.py fill --url "..." --browser-path /usr/bin/google-chrome
# or: export JA_BROWSER_PATH=/usr/bin/google-chrome
```

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
  ! Gender  -  Self-identification question: fill in yourself.

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

## Limitations

- Multi-page forms need a manual `r` press per step (see above); the tool
  doesn't click "Next" for you, by design.
- Highly custom React/JS form widgets that don't use real `<input>`/
  `<select>` elements (e.g. custom dropdowns) may not be detected.
- This is a heuristic label matcher, not a guarantee — always check the
  report and the form itself before submitting.

## Responsible use

- Respect each site's terms of service and robots directives.
- Don't use this to blast out large volumes of low-effort/spam applications.
- Review every field — especially free-text answers — before submitting.
