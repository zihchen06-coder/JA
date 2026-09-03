// Heuristic matching from a form field's visible label to a profile field.
// Ported from ja/matcher.py -- keep the two in sync. The fuzzy-ratio
// function below reimplements difflib.SequenceMatcher(None, a, b).ratio()
// (longest-matching-block recursion, no junk heuristics) so the same
// min_ratio thresholds tuned against the Python version still apply here.
"use strict";

var _PUNCT_RE = /[^a-z0-9\s]/g;
var _WS_RE = /\s+/g;

function normalize(text) {
  text = (text || "").toLowerCase();
  text = text.replace(_PUNCT_RE, " ");
  text = text.replace(_WS_RE, " ").trim();
  return text;
}

function _longestMatch(a, b, alo, ahi, blo, bhi) {
  let besti = alo, bestj = blo, bestsize = 0;
  let j2len = {};
  for (let i = alo; i < ahi; i++) {
    const newj2len = {};
    for (let j = blo; j < bhi; j++) {
      if (a[i] === b[j]) {
        const k = (j2len[j - 1] || 0) + 1;
        newj2len[j] = k;
        if (k > bestsize) {
          besti = i - k + 1;
          bestj = j - k + 1;
          bestsize = k;
        }
      }
    }
    j2len = newj2len;
  }
  return [besti, bestj, bestsize];
}

function _matchingBlocks(a, b) {
  const blocks = [];
  const queue = [[0, a.length, 0, b.length]];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = _longestMatch(a, b, alo, ahi, blo, bhi);
    if (k) {
      blocks.push(k);
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return blocks;
}

function fuzzyRatio(a, b) {
  if (!a.length && !b.length) return 1.0;
  const matches = _matchingBlocks(a, b).reduce((sum, k) => sum + k, 0);
  return (2.0 * matches) / (a.length + b.length);
}

function isEeoLabel(label) {
  const norm = normalize(label);
  return EEO_KEYWORDS.some((kw) => norm.includes(kw));
}

function sensitiveGroup(label) {
  const norm = normalize(label);
  for (const [group, [, keywords]] of Object.entries(SENSITIVE_GROUPS)) {
    if (keywords.some((kw) => norm.includes(kw))) return group;
  }
  return null;
}

function sensitiveReason(label) {
  const group = sensitiveGroup(label);
  return group ? SENSITIVE_GROUPS[group][0] : null;
}

function bestChoice(target, choices, minRatio = 0.45) {
  const normTarget = normalize(target);
  if (!normTarget) return null;

  let bestIdx = null, bestScore = 0.0;
  choices.forEach((choice, i) => {
    const text = normalize(choice);
    if (!text) return;
    if (text === normTarget) {
      bestIdx = i;
      bestScore = Infinity;
      return;
    }
    let ratio = fuzzyRatio(text, normTarget);
    if (normTarget.includes(text) || text.includes(normTarget)) ratio += 0.3;
    if (ratio > bestScore) {
      bestScore = ratio;
      bestIdx = i;
    }
  });

  return bestScore >= minRatio ? bestIdx : null;
}

function isResumeLabel(label) {
  const norm = normalize(label);
  return RESUME_KEYWORDS.some((kw) => norm.includes(kw)) && !isCoverLetterLabel(label);
}

function isCoverLetterLabel(label) {
  const norm = normalize(label);
  return COVER_LETTER_KEYWORDS.some((kw) => norm.includes(kw));
}

function _containsWhole(alias, norm) {
  const re = new RegExp(`(?<!\\w)${alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?!\\w)`);
  return re.test(norm);
}

// "Other School", "Other Phone", "Other Name" are escape hatches for the
// field they name -- they're meant to hold what the main one couldn't, so
// filling them with the same value fills in the wrong thing twice.
var _ESCAPE_HATCH_RE = /^other\b/;

function isEscapeHatchLabel(label) {
  return _ESCAPE_HATCH_RE.test(normalize(label));
}

// Label phrasings worked out on a previous application and remembered, so
// the same odd wording resolves instantly and for free the next time it is
// seen. Set from storage before a fill; see filler.js's learnFromAnswers for
// where entries come from and options.js for where they can be deleted.
var LEARNED_ALIASES = {};

function setLearnedAliases(map) {
  LEARNED_ALIASES = map || {};
}

// Short factual answers to questions the profile has no field for at all --
// "Phone type: Mobile", "Did you graduate? Yes", "Which shift? Either".
// These recur across applications far more than odd labels for known fields
// do, and remembering one is the difference between paying to work it out
// every time and never being asked again. Answers only, never prose.
var LEARNED_ANSWERS = {};

function setLearnedAnswers(map) {
  LEARNED_ANSWERS = map || {};
}

function learnedAnswerFor(label) {
  const norm = normalize(label);
  if (!norm) return null;
  return Object.prototype.hasOwnProperty.call(LEARNED_ANSWERS, norm)
    ? LEARNED_ANSWERS[norm]
    : null;
}

function matchField(label, minRatio = 0.72) {
  const norm = normalize(label);
  if (!norm) return null;
  if (_ESCAPE_HATCH_RE.test(norm)) return null;

  // An exact match on the whole label, learned from a fill that actually
  // worked -- more specific evidence than any substring alias below.
  if (Object.prototype.hasOwnProperty.call(LEARNED_ALIASES, norm)) {
    return LEARNED_ALIASES[norm];
  }

  let bestField = null;
  let bestKey = [-1, -1];
  for (const [canonical, aliases] of Object.entries(FIELD_ALIASES)) {
    for (const alias of aliases) {
      if (alias === norm) return canonical;
      if (_containsWhole(alias, norm)) {
        const key = [alias.split(" ").length, alias.length];
        if (key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) {
          bestKey = key;
          bestField = canonical;
        }
      }
    }
  }
  if (bestField) return bestField;

  // A label needs enough of its own text before a near-miss is trustworthy
  // -- see ja/matcher.py's match_field for why the 8-char floor exists.
  if (norm.length < 8) return null;

  let bestScore = 0.0;
  for (const [canonical, aliases] of Object.entries(FIELD_ALIASES)) {
    for (const alias of aliases) {
      const ratio = fuzzyRatio(alias, norm);
      if (ratio > bestScore) {
        bestScore = ratio;
        bestField = canonical;
      }
    }
  }

  return bestScore >= minRatio ? bestField : null;
}

// Some forms label a field with a word that means nothing on its own -- an
// iCIMS phone row labels its boxes just "Type" and "Number" -- while naming
// it perfectly well in machine terms ("PersonProfileFields.PhoneNumber").
// Only consulted once the visible label has matched nothing, and only trusted
// for a whole-word alias hit (minRatio above 1 rules out the fuzzy fallback),
// since a machine name is not written for a human to read.
function matchFieldByName(name, elemId = "") {
  const words = `${elemId || ""} ${name || ""}`
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[-_.]/g, " ");
  return matchField(words, 1.1);
}

function bestOption(targetValue, options, minRatio = 0.5) {
  const normTarget = normalize(String(targetValue));
  if (!normTarget) return null;

  let bestValue = null, bestScore = 0.0;
  for (const opt of options) {
    const text = normalize(opt.text || "");
    if (!text) continue;
    if (text === normTarget) return opt.value;
    let ratio = fuzzyRatio(text, normTarget);
    if (normTarget.includes(text) || text.includes(normTarget)) ratio += 0.25;
    if (ratio > bestScore) {
      bestScore = ratio;
      bestValue = opt.value;
    }
  }

  return bestScore >= minRatio ? bestValue : null;
}

var _MONTHS = {
  january: 1, jan: 1, february: 2, feb: 2, march: 3, mar: 3, april: 4, apr: 4,
  may: 5, june: 6, jun: 6, july: 7, jul: 7, august: 8, aug: 8, september: 9,
  sep: 9, sept: 9, october: 10, oct: 10, november: 11, nov: 11, december: 12, dec: 12,
};

function _pad(n, width = 2) {
  return String(n).padStart(width, "0");
}

function _parseDate(text) {
  let m = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return { y: +m[1], mo: +m[2], d: +m[3] };

  m = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return { y: +m[3], mo: +m[1], d: +m[2] };

  m = text.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (m) return { y: +m[3], mo: +m[1], d: +m[2] };

  m = text.match(/^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$/);
  if (m) {
    const mo = _MONTHS[m[1].toLowerCase()];
    if (mo) return { y: +m[3], mo, d: +m[2] };
  }

  return null;
}

function normalizeDate(value, targetFormat = "%Y-%m-%d") {
  const text = (value || "").trim();
  const parsed = _parseDate(text);
  if (!parsed) return value;
  const { y, mo, d } = parsed;
  if (targetFormat === "%Y-%m-%d") return `${y}-${_pad(mo)}-${_pad(d)}`;
  if (targetFormat === "%m/%d/%Y") return `${_pad(mo)}/${_pad(d)}/${y}`;
  return value;
}

function formatMonthYear(value, targetFormat = "%m/%Y") {
  const text = (value || "").trim();
  const m = text.match(/^(\d{4})-(\d{2})$/);
  if (!m) return value;
  const [, year, month] = m;
  return targetFormat === "%m/%Y" ? `${month}/${year}` : value;
}

// See ja/matcher.py's experience_field_for for the rationale: bare "Company"/
// "Job title"/"From"/"To" labels inside a work-history repeater block
// (Workday, and the SmartDreamers/Envista platform seen in practice) aren't
// in FIELD_ALIASES since they're too generic to match safely by label alone
// -- the field's own machine name inside the repeater ("experience[0]
// [company]", "experience_company") is the safe signal instead.
const _EXPERIENCE_NAME_KEYWORDS = [
  ["current_work", "current_checkbox"],
  ["job_title", "title"],
  ["company", "company"],
  ["location", "location"],
  ["work_start", "start_date"],
  ["work_end", "end_date"],
  ["role", "description"],
];

// The mirror image of the case above, seen on iCIMS: the fields inside a
// work-history block are labelled in plain English ("Employer", "Title",
// "City") but named opaquely ("rcf3212", "rcf3213"), so there the section
// heading is the safe signal and the label carries the meaning. Matching on
// these labels is only ever done inside a section whose <legend> names it as
// work history -- "City" or "Title" on their own are far too generic.
var _EXPERIENCE_SECTION_KEYWORDS = [
  "professional experience", "work experience", "employment history",
  "work history", "employment experience", "previous employment",
];

var _EXPERIENCE_LABEL_KEYWORDS = [
  ["is this your current job", "current_checkbox"],
  ["currently work here", "current_checkbox"],
  ["current job", "current_checkbox"],
  ["start date", "start_date"],
  ["end date", "end_date"],
  ["employer", "company"],
  ["company", "company"],
  ["job title", "title"],
  ["title", "title"],
  ["city", "location"],
  ["location", "location"],
  ["description", "description"],
  ["responsibilities", "description"],
];

function isExperienceSection(section) {
  const norm = normalize(section);
  return !!norm && _EXPERIENCE_SECTION_KEYWORDS.some((kw) => norm.includes(kw));
}

function experienceFieldFor(name, elemId = "", section = "", label = "") {
  const combined = `${elemId || ""} ${name || ""}`.toLowerCase().replace(/-/g, "_");
  if (combined.includes("experience")) {
    for (const [keyword, field] of _EXPERIENCE_NAME_KEYWORDS) {
      if (combined.includes(keyword)) return field;
    }
    return null;
  }

  if (!isExperienceSection(section)) return null;
  const normLabel = normalize(label);
  if (!normLabel) return null;
  for (const [keyword, field] of _EXPERIENCE_LABEL_KEYWORDS) {
    if (normLabel.includes(keyword)) return field;
  }
  return null;
}

// A split date control ("Start Date" broken into Month / Day / Year boxes)
// needs just its own piece of the saved date, not the whole thing. Matched
// on the box's own label only, and only as the entire label -- anything
// looser would read "Graduation Date" as a bare day box.
function datePartFor(label) {
  const norm = normalize(label);
  if (norm === "month" || norm === "mm") return "month";
  if (norm === "year" || norm === "yyyy" || norm === "yy") return "year";
  if (norm === "day" || norm === "dd") return "day";
  return null;
}

var _MONTH_NAMES = [
  ["01", "Jan", "January"], ["02", "Feb", "February"], ["03", "Mar", "March"],
  ["04", "Apr", "April"], ["05", "May", "May"], ["06", "Jun", "June"],
  ["07", "Jul", "July"], ["08", "Aug", "August"], ["09", "Sep", "September"],
  ["10", "Oct", "October"], ["11", "Nov", "November"], ["12", "Dec", "December"],
];

// Returns the candidate spellings for one piece of a "YYYY-MM" (or
// "YYYY-MM-DD") saved date, most specific first, so a Month box can be set
// whether its options read "06", "6", "Jun" or "June". Empty when that piece
// isn't in the saved value at all -- profiles store month precision, so a
// Day box gets nothing rather than a made-up 1st of the month.
function datePartCandidates(value, part) {
  const m = (value || "").trim().match(/^(\d{4})-(\d{2})(?:-(\d{2}))?$/);
  if (!m) return [];
  const [, year, month, day] = m;
  if (part === "year") return [year];
  if (part === "day") return day ? [day, String(Number(day))] : [];
  if (part === "month") {
    const names = _MONTH_NAMES[Number(month) - 1] || [];
    return [month, String(Number(month)), ...names.slice(1)];
  }
  return [];
}

function semanticBool(choiceText) {
  const norm = normalize(choiceText);
  if (!norm) return null;
  if (TRUE_WORDS.has(norm) || [...TRUE_WORDS].some((w) => w.length > 2 && norm.startsWith(w))) return true;
  if (FALSE_WORDS.has(norm) || [...FALSE_WORDS].some((w) => w.length > 2 && norm.startsWith(w))) return false;
  return null;
}
