// Reading a "Job Application Data Bank" document into a profile.
//
// The Data Bank is the applicant's own source of truth: a Google Doc of
// numbered sections ("3. Contact info", "5. Work authorization ...",
// "9. Voluntary self-ID") made of "- Key: value" lines, which the browser
// skills read on every application. Keeping this extension's profile in step
// with it by hand is how the two drifted apart, so this reads the doc's text
// -- copied out of Google Docs, or downloaded as Markdown or plain text --
// into the same shape the Options page's import box already takes.
//
// Only the sections that hold facts are read: contact, education, screening
// answers, self-ID. Experience, skills and saved answers are skipped on
// purpose. The doc itself marks them as out of date, they still carry claims
// the applicant has since said they can't back up, and the resume is the
// source for all three.
//
// Loaded by the Options page only. Needs normalize() (matcher.js) and
// SELF_ID_CHOICES / OPTION_CHOICES (field_aliases.js).
"use strict";

// Google Docs' Markdown export escapes punctuation: "GD\&T", "\[FILL\]",
// "https\://", "1\. Rules".
function _dbUnescape(text) {
  return String(text).replace(/\\([^\w\s])/g, "$1");
}

// "(none, leave blank)", "(blank: decline to answer)", "[FILL: ...]",
// "ALWAYS leave blank" -- all ways of writing "no value".
function _dbIsBlank(value) {
  const v = value.trim();
  return !v || /^\(\s*(none|blank|n\/a)\b/i.test(v) || /\[FILL/i.test(v) || /^always leave blank/i.test(v);
}

function _dbBool(value) {
  if (/^yes\b/i.test(value.trim())) return true;
  if (/^no\b/i.test(value.trim())) return false;
  return null;
}

// key (normalized) -> [profile field, kind]. Kinds: text, bool, selfid, choice.
var _DB_FIELDS = {
  "first name": ["first_name", "text"],
  "last name": ["last_name", "text"],
  "middle name": ["middle_name", "text"],
  "preferred name": ["preferred_name", "text"],
  "email": ["email", "text"],
  "phone": ["phone", "text"],
  "address line 1": ["address_line1", "text"],
  "address line 2": ["address_line2", "text"],
  "city": ["city", "text"],
  "state": ["state", "text"],
  "zip": ["postal_code", "text"],
  "zip code": ["postal_code", "text"],
  "postal code": ["postal_code", "text"],
  "country": ["country", "text"],
  "linkedin": ["linkedin_url", "text"],
  "github": ["github_url", "text"],
  "portfolio": ["portfolio_url", "text"],
  "languages": ["languages", "text"],
  "citizenship": ["citizenship_status", "choice"],
  "authorized to work in u s": ["work_authorized", "bool"],
  "needs sponsorship now or future": ["needs_sponsorship", "bool"],
  "has security clearance": ["security_clearance", "text"],
  "over 18": ["over_18", "bool"],
  "willing to relocate": ["willing_to_relocate", "bool"],
  "willing to travel": ["willing_to_travel", "bool"],
  "driver s license": ["has_drivers_license", "bool"],
  "drivers license": ["has_drivers_license", "bool"],
  "reliable transportation": ["has_reliable_transportation", "bool"],
  "overtime varied schedule ok": ["willing_overtime_varied_schedule", "bool"],
  "can perform essential functions": ["can_perform_essential_functions", "bool"],
  "consent to background check": ["consent_background_check", "bool"],
  "consent to drug test": ["consent_drug_test", "bool"],
  "previously employed by this company default": ["previously_employed_here", "bool"],
  "previously employed by this company": ["previously_employed_here", "bool"],
  "bound by non compete": ["bound_by_noncompete", "bool"],
  "criminal history": ["criminal_history", "bool"],
  "ok to receive texts": ["sms_consent", "bool"],
  "general consent agreements": ["consent_general", "bool"],
  "pay expectation": ["desired_salary", "text"],
  "gender": ["gender", "selfid"],
  "pronouns": ["pronouns", "text"],
  "hispanic latino": ["hispanic_latino", "selfid"],
  "race ethnicity": ["race_ethnicity", "selfid"],
  "veteran status": ["veteran_status", "selfid"],
  "disability status": ["disability_status", "selfid"],
  "sexual orientation": ["sexual_orientation", "selfid"],
  "transgender": ["transgender_status", "selfid"],
};

// Sections read, by the words in their heading. Anything else is skipped.
var _DB_READ_SECTIONS = /contact|education|authori[sz]ation|logistics|screening|self.?id|eeo/i;

function looksLikeDataBank(text) {
  return /data bank/i.test(text) && /contact info/i.test(text);
}

// -> { fields..., education: [...], _databank: {read, skipped} }
function parseDataBank(text) {
  const out = {};
  const read = [];
  const skipped = [];
  let section = "";
  let reading = false;

  const lines = _dbUnescape(text).split(/\r?\n/);
  for (const rawLine of lines) {
    // The export writes each bullet as a quoted list item ("> * First
    // name: ..."), with a trailing two-space line break.
    const line = rawLine.replace(/\*\*/g, "").replace(/^\s*(?:>\s*)+/, "").trim();

    // "## 3. Contact info" from a Markdown export; "3. Contact info" pasted
    // straight out of Google Docs.
    const heading =
      line.match(/^##\s+(?:\d+\.\s*)?(.+)$/) ||
      (!line.includes(":") && line.match(/^\d{1,2}\.\s+([A-Z].*)$/));
    if (heading) {
      section = heading[1].trim();
      reading = _DB_READ_SECTIONS.test(section);
      (reading ? read : skipped).push(section);
      continue;
    }
    if (!reading) continue;

    const bullet = line.match(/^(?:[-*\u2022]\s+)+(.*)$/);
    const item = (bullet ? bullet[1] : line).trim();
    if (!item) continue;

    if (/education/i.test(section)) {
      _dbEducationLine(item, out);
      continue;
    }
    if (/^current\s*:/i.test(item)) {
      _dbCurrentLine(item, out);
      continue;
    }

    const kv = item.match(/^([^:]{1,80}):\s*(.*)$/);
    if (!kv) continue;
    const key = normalize(kv[1]);
    const spec = _DB_FIELDS[key];
    if (!spec) continue;
    const [field, kind] = spec;
    const value = kv[2].trim();

    if (_dbIsBlank(value)) {
      if (kind === "text") out[field] = "";
      continue;
    }
    if (kind === "bool") {
      const b = _dbBool(value);
      if (b !== null) out[field] = b;
    } else if (kind === "selfid") {
      const choices = SELF_ID_CHOICES[field] || [];
      const at = bestSelfIdChoice(value, choices);
      if (at !== null) out[field] = choices[at];
    } else if (kind === "choice") {
      const choices = OPTION_CHOICES[field] || [];
      const at = /citizen/i.test(value) && !/non.?citizen/i.test(value)
        ? choices.indexOf("U.S. Citizen")
        : -1;
      if (at >= 0) out[field] = choices[at];
    } else {
      // A trailing note in parentheses is guidance for whoever reads the
      // doc, not part of the answer.
      out[field] = value.replace(/\s*\([^)]*\)\s*$/, "").trim();
    }
  }

  out._databank = { read, skipped };
  return out;
}

// "The Pennsylvania State University, B.S. Mechanical Engineering, expected May 2028"
// "Start: 2024 | GPA: 3.56 / 4.00 | Degree status: in progress"
function _dbEducationLine(item, out) {
  const gpa = item.match(/\bGPA:\s*([0-9.]+)/i);
  if (gpa) out.gpa = gpa[1];

  if (item.includes(":")) return;
  const parts = item.split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.length < 2 || !/universit|college|institute|school/i.test(parts[0])) return;
  const degreeMatch = parts[1].match(/^((?:B|M|Ph)\.?\s?[A-Z]?\.?[A-Z]?\.?|Bachelor'?s|Master'?s|Associate'?s)\s+(?:of\s+|in\s+)?(.*)$/i);
  const year = (parts.slice(2).join(" ").match(/\b(19|20)\d{2}\b/) || [""])[0];
  out.education = out.education || [];
  out.education.push({
    school: parts[0],
    degree: degreeMatch ? degreeMatch[1].trim() : parts[1],
    field_of_study: degreeMatch ? degreeMatch[2].trim() : "",
    graduation_year: year,
  });
}

// "Current: Manufacturing Engineering Co-op, Harley-Davidson | Years experience: 1"
function _dbCurrentLine(item, out) {
  const [current, ...rest] = item.replace(/^current\s*:\s*/i, "").split("|");
  const comma = current.lastIndexOf(",");
  if (comma > 0) {
    out.current_title = current.slice(0, comma).trim();
    out.current_company = current.slice(comma + 1).trim();
  }
  for (const part of rest) {
    const years = part.match(/years? experience:\s*([0-9.]+)/i);
    if (years) out.years_experience = years[1];
  }
}
