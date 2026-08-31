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

function matchField(label, minRatio = 0.72) {
  const norm = normalize(label);
  if (!norm) return null;

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

function semanticBool(choiceText) {
  const norm = normalize(choiceText);
  if (!norm) return null;
  if (TRUE_WORDS.has(norm) || [...TRUE_WORDS].some((w) => w.length > 2 && norm.startsWith(w))) return true;
  if (FALSE_WORDS.has(norm) || [...FALSE_WORDS].some((w) => w.length > 2 && norm.startsWith(w))) return false;
  return null;
}
