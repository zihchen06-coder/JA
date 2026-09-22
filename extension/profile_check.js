// Checks on a saved profile, run on the Options page.
//
// Every check here is something a real form was seen to reject or answer
// wrongly, not a style opinion. A profile is the applicant's to write, so
// nothing is blocked and nothing is corrected behind their back: each
// finding says what a form will do with the value, and carries a `fix` only
// where there is exactly one right correction to offer them.
"use strict";

// Country boxes on real applications are dropdowns listing full names, and
// an option match is by text -- "US" matches nothing in a list of "United
// States". These are what people type instead.
var _COUNTRY_ABBREVIATIONS = {
  us: "United States",
  usa: "United States",
  "u.s.": "United States",
  "u.s.a.": "United States",
  "united states of america": "United States",
  uk: "United Kingdom",
  ca: "Canada",
};

var _URL_FIELDS = {
  linkedin_url: "LinkedIn URL",
  github_url: "GitHub URL",
  portfolio_url: "Portfolio URL",
};

function _text(value) {
  return typeof value === "string" ? value.trim() : value === null || value === undefined ? "" : String(value);
}

function _looksNumeric(value) {
  return /^\s*\$?\s*[\d,]+(\.\d+)?\s*(k|K)?\s*$/.test(value);
}

// A profile value and what a form will do with it. Returns a list of
// {field, level, message, fix}: "error" is a value a form will reject or
// silently drop, "warn" is one that fills but answers wrongly somewhere,
// "info" is a gap that will be flagged on every application until it's
// filled in. `fix`, when present, is the exact value to replace it with.
function profileWarnings(profile) {
  const p = profile || {};
  const out = [];
  const add = (field, level, message, fix) => out.push({ field, level, message, fix });

  for (const [field, name] of Object.entries(_URL_FIELDS)) {
    const value = _text(p[field]);
    if (!value) continue;
    if (!/^https?:\/\//i.test(value)) {
      // The box is usually <input type="url">, whose validation rejects a
      // bare host -- the fill looks fine and the form refuses to submit.
      add(field, "error",
        `${name} has no https:// in front of it. A URL box on a form rejects it on submit.`,
        `https://${value.replace(/^\/+/, "")}`);
    }
  }

  const country = _text(p.country);
  const expanded = _COUNTRY_ABBREVIATIONS[country.toLowerCase()];
  if (expanded && expanded.toLowerCase() !== country.toLowerCase()) {
    add("country", "error",
      `Country dropdowns list "${expanded}", and an option is matched by its text -- ` +
        `"${country}" matches nothing, so the field is left blank.`,
      expanded);
  }

  const email = _text(p.email);
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    add("email", "error", "That email address doesn't look complete -- a form will reject it.");
  }

  const phone = _text(p.phone);
  if (phone && (phone.match(/\d/g) || []).length < 10) {
    add("phone", "error", "That phone number has fewer than 10 digits.");
  }

  const salary = _text(p.desired_salary);
  if (salary && !_looksNumeric(salary)) {
    // Not a mistake -- refusing to name a number is a position. But a
    // number box drops anything that isn't one, so it's worth knowing the
    // answer only lands where the form asks in words.
    add("desired_salary", "info",
      "Your salary answer isn't a number, so a numeric salary box will drop it and flag " +
        "the field for you. It still fills a plain text box.");
  }

  const gpa = _text(p.gpa);
  if (gpa && !(Number(gpa) >= 0 && Number(gpa) <= 5)) {
    add("gpa", "warn", `"${gpa}" doesn't read as a GPA. Most forms expect something like 3.56.`);
  }

  if (p.previously_employed_here === true || p.previously_employed_here === false) {
    const company = _text(p.current_company);
    // One saved answer is reused at every employer, and this question is
    // about the one reading the form.
    add("previously_employed_here", "warn",
      '"Previously employed here" is asked by each company about itself, so one saved answer ' +
        `is wrong wherever it doesn't apply${company ? ` -- starting with ${company}` : ""}. ` +
        "Leaving it unset flags it for you on each form instead.");
  }

  for (const [i, entry] of (Array.isArray(p.education) ? p.education : []).entries()) {
    const year = _text(entry && entry.graduation_year);
    if (year && !/^\d{4}$/.test(year)) {
      add(`education[${i}].graduation_year`, "warn",
        `Graduation year "${year}" isn't a four-digit year, which is what a year box expects.`);
    }
  }

  for (const [i, entry] of (Array.isArray(p.experience) ? p.experience : []).entries()) {
    for (const key of ["start_date", "end_date"]) {
      const value = _text(entry && entry[key]);
      if (!value) continue;
      if (/^present$/i.test(value) || /^\d{4}-\d{2}$/.test(value)) continue;
      add(`experience[${i}].${key}`, "warn",
        `"${value}" isn't in YYYY-MM form, which is what the month and year boxes in a ` +
          "work-history block are filled from.");
    }
  }

  const answers = p.custom_answers && typeof p.custom_answers === "object" ? p.custom_answers : {};
  const blank = Object.keys(answers).filter((k) => !_text(answers[k]));
  if (blank.length) {
    add("custom_answers", "info",
      `${blank.length} question(s) in Answers have no answer yet (${blank.slice(0, 3).join(", ")}` +
        `${blank.length > 3 ? ", ..." : ""}). Those get flagged on every form until you write one.`);
  }

  return out;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { profileWarnings };
}
