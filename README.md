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

The browser stays open. Review everything, answer the flagged questions,
fix anything mismatched, and click submit yourself. Press Enter in the
terminal when you're done to close the browser.

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

- Multi-page forms (common on Workday) need `fill` re-run (or the page
  re-scanned) per page/step, since new fields only appear after navigating.
- Highly custom React/JS form widgets that don't use real `<input>`/
  `<select>` elements (e.g. custom dropdowns) may not be detected.
- This is a heuristic label matcher, not a guarantee — always check the
  report and the form itself before submitting.

## Responsible use

- Respect each site's terms of service and robots directives.
- Don't use this to blast out large volumes of low-effort/spam applications.
- Review every field — especially free-text answers — before submitting.
