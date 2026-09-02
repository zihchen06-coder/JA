// Core fill logic: read extracted form fields, decide what to fill from the
// profile, and apply it to the real DOM -- never touching submit controls,
// never guessing on self-ID/criminal/salary questions. Ported from
// ja/filler.py -- keep the two in sync (the file-upload handling below is
// the one deliberate divergence: this version can attach a saved resume/
// cover-letter file directly, which Playwright's set_input_files already
// does natively on the Python side).
"use strict";

var MARK_FILLED = "#22c55e";
var MARK_REVIEW = "#f59e0b";
var MARK_BLANK = "#ef4444";

function _sel(jaId) {
  return `[data-ja-id="${jaId}"]`;
}

function _el(jaId) {
  return document.querySelector(_sel(jaId));
}

// An iCIMS <select> is display:none behind its own widget, so an outline
// drawn on it would be invisible -- the anchor the applicant actually looks
// at is what has to be highlighted.
function _displayEl(el) {
  if (el && el.tagName === "SELECT" && el.id) {
    const anchor = document.getElementById(el.id + "_icimsDropdown");
    if (anchor) return anchor;
  }
  return el;
}

function _mark(jaId, color) {
  const el = _displayEl(_el(jaId));
  if (!el) return;
  el.style.outline = `2px solid ${color}`;
  el.style.outlineOffset = "1px";
  el.style.borderRadius = getComputedStyle(el).borderRadius || "3px";
}

function _markAll(options, color) {
  for (const opt of options) _mark(opt.ja_id, color);
}

// Setting `.value` directly on a React/Vue-controlled input doesn't notify
// the framework -- it tracks changes through the native property setter,
// which direct assignment bypasses. Calling the setter explicitly first
// (the same trick used by testing-library and Cypress) makes the
// framework's own change handlers fire correctly.
function _setNativeValue(el, value) {
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  if (desc && desc.set) {
    desc.set.call(el, value);
  } else {
    el.value = value;
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function _setSelectValue(el, value) {
  el.value = value;
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

// A real .click() toggles checked state and fires click/input/change the
// same way an actual user interaction would (isTrusted is false, but
// bubbling and default handling are otherwise identical) -- more reliable
// across frameworks than manually mutating .checked and hand-firing events,
// and it naturally deselects the rest of a radio group for us.
function _setChecked(el, checked) {
  if (el.checked === checked) return;
  el.click();
}

function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function _waitFor(fn, timeout = 1500, step = 50) {
  const deadline = Date.now() + timeout;
  for (;;) {
    const value = fn();
    if (value) return value;
    if (Date.now() >= deadline) return null;
    await _sleep(step);
  }
}

function _isShown(el) {
  if (!el) return false;
  const style = getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function _listboxOptions(listbox) {
  return Array.from(listbox.querySelectorAll('[role="option"]')).filter(_isShown);
}

// aria-haspopup="listbox" promises that activating the control renders a
// [role="listbox"] whose [role="option"] children are the real choices.
// Workday's questionnaire dropdowns are built exactly that way -- a plain
// <button>, no <select>, and nothing in the DOM naming the choices until the
// popup exists -- so opening it is the only way to see what can be picked.
// Written against that ARIA contract rather than any one vendor's markup:
// prefer whatever the button says it owns, else whatever listbox appeared
// that wasn't on the page a moment ago.
async function _openListbox(button) {
  const before = new Set(Array.from(document.querySelectorAll('[role="listbox"]')).filter(_isShown));

  const owned = () => {
    const id = button.getAttribute("aria-controls") || button.getAttribute("aria-owns");
    const el = id ? document.getElementById(id) : null;
    return el && _isShown(el) && _listboxOptions(el).length ? el : null;
  };
  const appeared = () =>
    Array.from(document.querySelectorAll('[role="listbox"]')).find(
      (l) => !before.has(l) && _isShown(l) && _listboxOptions(l).length
    ) || null;

  button.click();
  const listbox = await _waitFor(() => owned() || appeared());
  if (!listbox) return null;
  const optionEls = _listboxOptions(listbox);
  return {
    listbox,
    optionEls,
    // Indexes into optionEls, so the same option-choosing logic a real
    // <select> goes through applies unchanged.
    options: optionEls.map((el, i) => ({
      value: String(i),
      text: (el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim(),
    })),
  };
}

function _closeListbox(button, opened) {
  const esc = () =>
    new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true });
  opened.listbox.dispatchEvent(esc());
  button.dispatchEvent(esc());
  if (_isShown(opened.listbox)) button.click();
}

function _clickListboxOption(button, opened, index) {
  const before = (button.textContent || "").trim();
  opened.optionEls[index].click();
  // The button is the widget's own display of its value; if the page's
  // handler never ran, it still reads "Select One" and nothing was set.
  return (button.textContent || "").trim() !== before || !!button.value;
}

function _icimsOptions(select) {
  const list = document.getElementById(select.id + "_dropdown-results");
  if (!list) return [];
  return Array.from(list.querySelectorAll('[role="option"]')).map((li) => ({
    value: li.id,
    text: (li.getAttribute("title") || li.textContent || "").replace(/\s+/g, " ").trim(),
  }));
}

// Long iCIMS lists (schools, countries) are paged: the widget ships with
// only the first couple of dozen entries and fetches the rest as you type
// into its search box. Best-effort, and only ever a fallback after matching
// what's already loaded has failed -- if their search doesn't respond the
// way this expects, the options simply don't change and the field ends up
// reported for review rather than filled with the wrong thing.
async function _icimsSearch(select, text) {
  const container = document.getElementById(select.id + "_icimsDropdown_ctnr");
  const search = container && container.querySelector("input.dropdown-search");
  if (!search) return null;

  const before = _icimsOptions(select).map((o) => o.text).join("|");
  _setNativeValue(search, text);
  search.dispatchEvent(new KeyboardEvent("keyup", { key: text.slice(-1), bubbles: true }));
  const changed = await _waitFor(() => {
    const now = _icimsOptions(select);
    return now.map((o) => o.text).join("|") !== before ? now : null;
  }, 1200);
  return changed;
}

// iCIMS binds its handler to the <li>, and only while the dropdown is open,
// so this opens the widget the way a click would before picking. Whether it
// took is checked rather than assumed: if their script isn't what we think,
// the field is reported for review instead of being called filled.
function _openIcims(select) {
  const anchor = document.getElementById(select.id + "_icimsDropdown");
  if (anchor) anchor.click();
  return anchor;
}

function _setIcimsValue(select, optionId, optionText) {
  const li = document.getElementById(optionId);
  if (!li) return false;
  const before = select.value;
  li.click();

  if (select.value && select.value !== before) return true;
  const fake = document.getElementById(select.id + "_fakeSelected_icimsDropdown");
  if (!fake || fake.querySelector(".dropdown-placeholder")) return false;
  return normalize(fake.textContent) === normalize(optionText);
}

function makeReport(platform) {
  return { platform, results: [] };
}

function addResult(report, label, canonical, action, detail = "", required = false) {
  report.results.push({ label, canonical, action, detail, required });
}

function detectPlatform(url) {
  const host = (() => {
    try {
      return new URL(url).host.toLowerCase();
    } catch (e) {
      return "";
    }
  })();
  if (host.includes("greenhouse.io")) return "greenhouse";
  if (host.includes("lever.co")) return "lever";
  if (host.includes("myworkdayjobs.com") || host.includes("workday.com")) return "workday";
  return "generic";
}

function _profileValue(profile, canonical) {
  if (EDUCATION_FIELDS.has(canonical)) {
    if (!profile.education || !profile.education.length) return null;
    return profile.education[0][canonical] ?? null;
  }
  return profile[canonical] ?? null;
}

function _displayLabel(label, canonical) {
  if (canonical && SELF_ID_DISPLAY_NAMES[canonical]) return SELF_ID_DISPLAY_NAMES[canonical];
  return label.trim() || canonical || label;
}

var _SIGNATURE_CONTEXT_KEYWORDS = ["disability", "veteran", "signature"];

function _isSignatureContext(wideText) {
  const norm = normalize(wideText);
  return _SIGNATURE_CONTEXT_KEYWORDS.some((kw) => norm.includes(kw));
}

function _fillText(report, f, canonical, value, required) {
  const label = f.label || "";
  const el = _el(f.ja_id);
  if (!el) {
    addResult(report, label, canonical, "error", "Field disappeared from the page.", required);
    return;
  }
  _setNativeValue(el, value);
  _mark(f.ja_id, MARK_FILLED);
  addResult(report, label, canonical, "filled", value, required);
}

// The answer to a sensitive question, but only ever the one the applicant
// wrote down for that exact question themselves, under a profile field that
// belongs to this question's own group. Nothing here is inferred -- not from
// their name, not from their resume, and not by the AI-assist pass, which
// never sees these fields at all. Unset means unset: the question is flagged
// and left for them, on every form, forever.
function _savedSensitiveAnswer(profile, label, group) {
  const allowed = SENSITIVE_ANSWER_FIELDS[group];
  if (!allowed) return null;
  const canonical = matchField(label);
  if (!canonical || !allowed.has(canonical)) return null;
  const value = profile[canonical];
  // false is a real answer to "have you ever been convicted"; "" and
  // undefined are not answers at all.
  if (value === null || value === undefined || value === "") return null;
  return value;
}

function _isAnswered(value) {
  return value !== null && value !== undefined && value !== "";
}

function _matchCustomAnswer(label, profile) {
  const normLabel = normalize(label);
  if (!normLabel) return null;
  for (const [keyword, answer] of Object.entries(profile.custom_answers || {})) {
    if (normLabel.includes(normalize(keyword))) return answer;
  }
  return null;
}

// profile: plain object shaped like ja/profile.py's Profile dataclass.
// creds: [login, password] tuple already resolved for this hostname, or
// null when account auto-creation is off or this page has no password field.
//
// Async because a custom-widget dropdown (Workday's listbox buttons) only
// reveals its options once opened, which means clicking and then waiting for
// the page's own script to render them.
async function fillForm(profile, creds, opts) {
  const report = makeReport(detectPlatform(location.href));
  report.opts = opts || {};
  const fieldsData = extractFields();

  const simpleFields = fieldsData.filter((f) => f.type !== "radio");
  const radios = fieldsData.filter((f) => f.type === "radio");

  report.fields = fieldsData;
  for (const f of simpleFields) {
    await _handleSimpleField(profile, report, f, creds);
  }

  const byName = new Map();
  for (const f of radios) {
    if (!byName.has(f.name)) byName.set(f.name, []);
    byName.get(f.name).push(f);
  }
  for (const group of byName.values()) {
    const before = report.results.length;
    _handleRadioGroup(profile, report, group);
    // A radio group's result belongs to the whole group; the first option's
    // id stands for it, the same handle llmFieldsFor offers it under.
    for (let i = before; i < report.results.length; i++) {
      report.results[i].ja_id = group[0].ja_id;
    }
  }

  return report;
}

// Stamps every result a field produced with that field's id, without
// threading it through the thirty-odd addResult call sites below.
async function _handleSimpleField(profile, report, f, creds) {
  const before = report.results.length;
  await _handleSimpleFieldInner(profile, report, f, creds);
  for (let i = before; i < report.results.length; i++) {
    report.results[i].ja_id = f.ja_id;
  }
}

async function _handleSimpleFieldInner(profile, report, f, creds) {
  let label = f.label || "";
  const required = f.required || false;
  const ftype = f.type;

  if (f.has_value) {
    addResult(report, label, null, "already_filled", "Left as-is.", required);
    return;
  }

  if (ftype === "file") {
    _handleFileField(profile, report, f);
    return;
  }

  if (creds) {
    if (ftype === "password") {
      _fillText(report, f, "account_password", creds[1], required);
      return;
    }
    if (["login", "username"].includes(normalize(label))) {
      _fillText(report, f, "account_login", creds[0], required);
      return;
    }
  }

  // Both halves of the label matter inside a work-history block: a split
  // date control names each box "Month"/"Day"/"Year" via <label for> and
  // names the question it belongs to only in aria-labelledby.
  const expLabel = [label, f.aria_label || ""].filter(Boolean).join(" ");
  const expField = experienceFieldFor(f.name || "", f.id || "", f.section || "", expLabel);
  if (expField === "current_checkbox") {
    _fillCurrentJobSelect(profile, report, f, required);
    return;
  }
  if (expField) {
    _fillExperienceField(profile, report, f, expField, required);
    return;
  }
  if (isExperienceSection(f.section || "")) {
    // The Address/City/State/Country boxes in a work-history block are the
    // employer's, not the applicant's -- matching them against the personal
    // profile would confidently fill in the wrong thing.
    addResult(report, label || f.name || f.ja_id, null, "skipped_no_match",
      "Inside a work-history block -- not filled from your personal details.", required);
    return;
  }

  const context = f.context || "";
  const wideText = context ? `${label} ${context}`.trim() : label;

  if (_isSignatureContext(wideText)) {
    const normLabel = normalize(label);
    if (normLabel === "name" && profile.full_name) {
      _fillText(report, f, "full_name", profile.full_name, required);
      return;
    }
    if (normLabel === "date") {
      const now = new Date();
      const y = now.getFullYear();
      const mo = String(now.getMonth() + 1).padStart(2, "0");
      const d = String(now.getDate()).padStart(2, "0");
      const today = ftype === "date" ? `${y}-${mo}-${d}` : `${mo}/${d}/${y}`;
      _fillText(report, f, "signature_date", today, required);
      return;
    }
  }

  const group = sensitiveGroup(wideText);
  let canonical, value;
  if (group) {
    const answer = _savedSensitiveAnswer(profile, wideText, group);
    if (!_isAnswered(answer)) {
      const guess = matchField(wideText);
      _mark(f.ja_id, MARK_REVIEW);
      addResult(report, _displayLabel(label, guess), null, "needs_review", sensitiveReason(wideText), required);
      return;
    }
    canonical = matchField(wideText);
    label = _displayLabel(label, canonical);
    value = answer;
    if (ftype === "checkbox") {
      _sensitiveCheckbox(report, f, canonical, label, value, required);
      return;
    }
  } else {
    if (ftype === "checkbox") {
      _handleCheckbox(profile, report, f);
      return;
    }

    canonical = matchField(label);
    if (canonical === "cover_letter_text" && report.opts.tailorCoverLetter) {
      // One saved cover letter pasted into every application reads worse
      // than none. Left for the second pass, which knows what job this is.
      addResult(report, label, canonical, "skipped_no_data",
        "Left for Claude to write for this job.", required);
      return;
    }
    // The machine-name fallback must not undo an escape-hatch label:
    // "Other School" is named OtherSchool, which reads as a plain school.
    if (canonical === null && !isEscapeHatchLabel(label)) {
      canonical = matchFieldByName(f.name || "", f.id || "");
    }
    if (canonical === null) {
      const customAnswer = _matchCustomAnswer(label, profile);
      if (customAnswer !== null && ftype !== "select") {
        const el = _el(f.ja_id);
        if (el) {
          _setNativeValue(el, customAnswer);
          _mark(f.ja_id, MARK_FILLED);
          addResult(report, label, "custom_answers", "filled", customAnswer, required);
        } else {
          addResult(report, label, "custom_answers", "error", "Field disappeared from the page.", required);
        }
        return;
      }
      if (required) _mark(f.ja_id, MARK_BLANK);
      addResult(report, label || f.name || f.ja_id, null, "skipped_no_match", "", required);
      return;
    }
    value = _profileValue(profile, canonical);
  }

  if (value === null || value === undefined || value === "") {
    if (required) _mark(f.ja_id, MARK_BLANK);
    addResult(report, label, canonical, "skipped_no_data", "Profile has no value for this field.", required);
    return;
  }

  const el = _el(f.ja_id);
  if (!el) {
    addResult(report, label, canonical, "error", "Field disappeared from the page.", required);
    return;
  }

  try {
    if (f.tag === "select") {
      await _fillSelectLike(profile, report, f, el, canonical, value, label, required);
    } else {
      let fillValue;
      // A yes/no answer landing in a free-text box: "Yes" is what a person
      // would write there, "true" is what a bug looks like.
      if (typeof value === "boolean") {
        fillValue = value ? "Yes" : "No";
        _fillText(report, f, canonical, fillValue, required);
        return;
      }
      if (ftype === "date") {
        fillValue = normalizeDate(String(value), "%Y-%m-%d");
      } else if (f.is_datepicker || canonical === "notice_period") {
        fillValue = normalizeDate(String(value), "%m/%d/%Y");
      } else {
        fillValue = String(value);
      }
      _setNativeValue(el, fillValue);
      _mark(f.ja_id, MARK_FILLED);
      addResult(report, label, canonical, "filled", fillValue, required);
    }
  } catch (exc) {
    addResult(report, label, canonical, "error", String(exc), required);
  }
}

// Picks an option for a select-shaped field. `options` is [{value, text}]
// whichever widget it came from -- a real <select>'s <option>s, an iCIMS
// widget's <li>s, or the popup a Workday listbox button just rendered --
// so the decision is made the same way for all three.
function _optionText(options, optionValue) {
  const match = options.find((o) => o.value === optionValue);
  return match ? match.text || "" : "";
}

function _isExactChoice(decision, options, value) {
  if (decision.skip) return false;
  return normalize(_optionText(options, decision.value)) === normalize(String(value));
}

function _chooseOption(profile, canonical, value, options) {
  if (BOOLEAN_FIELDS.has(canonical) && typeof value === "boolean") {
    const match = options.find((o) => semanticBool(o.text || "") === value);
    if (!match) return { skip: `No option matched '${value}'.` };
    return { value: match.value, detail: match.text || "" };
  }

  const realOptions = options.length > 1 ? options.slice(1) : options;
  const allBoolShaped = realOptions.length > 0 && realOptions.every((o) => semanticBool(o.text || "") !== null);
  if (allBoolShaped) {
    return { skip: "This looks like a yes/no question with no matching saved answer." };
  }

  let optionValue = bestOption(String(value), options);
  // A "Degree" dropdown almost always lists coarse categories ("Bachelors
  // Degree", "Masters Degree"), not the applicant's own abbreviation for
  // their degree ("B.S.") -- education_level is shaped for exactly this and
  // is worth trying before giving up.
  if ((optionValue === null || optionValue === undefined) && canonical === "degree" && profile.education_level) {
    optionValue = bestOption(profile.education_level, options);
  }
  if (optionValue === null || optionValue === undefined) {
    return { skip: `No option matched '${value}'.` };
  }
  return { value: optionValue, detail: _optionText(options, optionValue) || String(value) };
}

async function _fillSelectLike(profile, report, f, el, canonical, value, label, required) {
  let options = f.options || [];
  let opened = null;

  if (f.widget === "listbox_button") {
    opened = await _openListbox(el);
    if (!opened) {
      _mark(f.ja_id, MARK_REVIEW);
      addResult(report, label, canonical, "needs_review",
        "Could not open this dropdown automatically -- pick an answer here yourself.", required);
      return;
    }
    options = opened.options;
    f.options = options;
  } else if (f.widget === "icims") {
    _openIcims(el);
  }

  let decision = _chooseOption(profile, canonical, value, options);
  // On a paged list the right answer is often not on the first page at all,
  // and a so-so fuzzy match against the page that did load would quietly win
  // over it -- "Aalto University" is a 0.6 match for "State University".
  // Anything short of an exact hit is worth searching for first.
  if (
    f.widget === "icims" &&
    typeof value !== "boolean" &&
    !_isExactChoice(decision, options, value)
  ) {
    const refreshed = await _icimsSearch(el, String(value));
    if (refreshed && refreshed.length) {
      options = refreshed;
      decision = _chooseOption(profile, canonical, value, options);
    }
  }
  if (decision.skip) {
    if (opened) _closeListbox(el, opened);
    if (required) _mark(f.ja_id, MARK_BLANK);
    addResult(report, label, canonical, "skipped_no_match", decision.skip, required);
    return;
  }

  let applied;
  if (opened) {
    applied = _clickListboxOption(el, opened, Number(decision.value));
  } else if (f.widget === "icims") {
    applied = _setIcimsValue(el, decision.value, _optionText(options, decision.value));
  } else {
    _setSelectValue(el, decision.value);
    applied = true;
  }

  if (!applied) {
    _mark(f.ja_id, MARK_REVIEW);
    addResult(report, label, canonical, "needs_review",
      "This dropdown is a custom widget that did not take the answer -- set it here yourself.", required);
    return;
  }
  _mark(f.ja_id, MARK_FILLED);
  addResult(report, label, canonical, "filled", decision.detail, required);
}

const EXPERIENCE_ATTR = {
  title: "title", company: "company", location: "location",
  start_date: "start_date", end_date: "end_date", description: "description",
};

function _fillExperienceField(profile, report, f, expField, required) {
  const label = f.label || f.name || "";
  const canonical = `experience_${expField}`;

  if (!profile.experience || !profile.experience.length) {
    if (required) _mark(f.ja_id, MARK_BLANK);
    addResult(report, label, canonical, "skipped_no_data", "No work experience saved in your profile.", required);
    return;
  }

  const value = profile.experience[0][EXPERIENCE_ATTR[expField]] || "";

  if (expField === "end_date" && ["present", "current", "ongoing"].includes(value.trim().toLowerCase())) {
    addResult(report, label, canonical, "filled",
      "Left blank -- this job is marked as your current one.", required);
    return;
  }

  if (!value) {
    if (required) _mark(f.ja_id, MARK_BLANK);
    addResult(report, label, canonical, "skipped_no_data", "No value saved for this field.", required);
    return;
  }

  const datePart = ["start_date", "end_date"].includes(expField) ? datePartFor(label) : null;
  if (datePart) {
    _fillDatePart(report, f, canonical, value, datePart, required);
    return;
  }

  // "Milwaukee, WI" is the right answer for a "Location" box and the wrong
  // one for a "City" box sitting next to its own State box.
  let fillValue = String(value);
  if (expField === "location" && /\bcity\b/.test(normalize(label))) {
    fillValue = fillValue.split(",")[0].trim();
  } else if (["start_date", "end_date"].includes(expField)) {
    fillValue = formatMonthYear(fillValue, "%m/%Y");
  }
  _fillText(report, f, canonical, fillValue, required);
}

// One box of a split Month / Day / Year date control.
function _fillDatePart(report, f, canonical, value, part, required) {
  const label = f.label || f.name || "";
  const candidates = datePartCandidates(String(value), part);
  if (!candidates.length) {
    addResult(report, label, canonical, "skipped_no_data",
      "Only the month and year are saved for this job.", required);
    return;
  }

  const el = _el(f.ja_id);
  if (!el) {
    addResult(report, label, canonical, "error", "Field disappeared from the page.", required);
    return;
  }

  if (f.tag !== "select") {
    _setNativeValue(el, candidates[0]);
    _mark(f.ja_id, MARK_FILLED);
    addResult(report, label, canonical, "filled", candidates[0], required);
    return;
  }

  // Month boxes spell themselves "06", "6", "Jun" or "June" depending on the
  // form, so try each spelling against both the option values and their text
  // before giving up.
  const options = f.options || [];
  for (const candidate of candidates) {
    const norm = normalize(candidate);
    const match = options.find(
      (o) => o.value === candidate || (o.text && normalize(o.text) === norm)
    );
    if (!match) continue;
    _setSelectValue(el, match.value);
    _mark(f.ja_id, MARK_FILLED);
    addResult(report, label, canonical, "filled", match.text || match.value, required);
    return;
  }

  if (required) _mark(f.ja_id, MARK_BLANK);
  addResult(report, label, canonical, "skipped_no_match",
    `No option matched '${candidates[0]}'.`, required);
}

// Some forms ask "Is this your current job?" as a Yes/No dropdown rather
// than the checkbox _handleCurrentWorkCheckbox covers.
function _fillCurrentJobSelect(profile, report, f, required) {
  const label = f.label || f.name || "";
  const canonical = "experience_end_date";

  if (f.tag !== "select") {
    _handleCurrentWorkCheckbox(profile, report, f);
    return;
  }
  if (!profile.experience || !profile.experience.length) {
    addResult(report, label, canonical, "skipped_no_data", "No work experience saved in your profile.", required);
    return;
  }

  const isCurrent = ["present", "current", "ongoing"].includes(
    (profile.experience[0].end_date || "").trim().toLowerCase()
  );
  const match = (f.options || []).find((o) => semanticBool(o.text || "") === isCurrent);
  if (!match) {
    if (required) _mark(f.ja_id, MARK_BLANK);
    addResult(report, label, canonical, "skipped_no_match", "No Yes/No option found.", required);
    return;
  }

  const el = _el(f.ja_id);
  if (!el) {
    addResult(report, label, canonical, "error", "Field disappeared from the page.", required);
    return;
  }
  let applied;
  if (f.widget === "icims") {
    _openIcims(el);
    applied = _setIcimsValue(el, match.value, match.text);
  } else {
    _setSelectValue(el, match.value);
    applied = true;
  }
  if (!applied) {
    _mark(f.ja_id, MARK_REVIEW);
    addResult(report, label, canonical, "needs_review",
      "This dropdown is a custom widget that did not take the answer -- set it here yourself.", required);
    return;
  }
  _mark(f.ja_id, MARK_FILLED);
  addResult(report, label, canonical, "filled", match.text || "", required);
}

function _handleCurrentWorkCheckbox(profile, report, f) {
  const label = f.label || "I currently work here";
  const required = f.required || false;
  const canonical = "experience_end_date";

  if (!profile.experience || !profile.experience.length) {
    addResult(report, label, canonical, "skipped_no_data", "No work experience saved in your profile.", required);
    return;
  }

  const wantChecked = ["present", "current", "ongoing"].includes(
    (profile.experience[0].end_date || "").trim().toLowerCase()
  );
  if (f.checked === wantChecked) {
    if (wantChecked) addResult(report, label, canonical, "already_filled", "Left as-is.", required);
    return;
  }

  const el = _el(f.ja_id);
  if (!el) {
    addResult(report, label, canonical, "error", "Field disappeared from the page.", required);
    return;
  }
  _setChecked(el, wantChecked);
  if (wantChecked) {
    _mark(f.ja_id, MARK_FILLED);
    addResult(report, label, canonical, "filled", "checked", required);
  }
}

function _handleCheckbox(profile, report, f) {
  const label = f.label || "";
  const groupLabel = f.group_label || "";
  const required = f.required || false;

  if (experienceFieldFor(f.name || "", f.id || "", f.section || "", label) === "current_checkbox") {
    _handleCurrentWorkCheckbox(profile, report, f);
    return;
  }

  const canonical = matchField(label);

  const optionBool = semanticBool(label);
  if (!BOOLEAN_FIELDS.has(canonical) && optionBool !== null) {
    const groupCanonical = matchField(groupLabel);
    if (BOOLEAN_FIELDS.has(groupCanonical)) {
      const target = profile[groupCanonical];
      if (target === null || target === undefined) {
        addResult(report, groupLabel, groupCanonical, "skipped_no_data", "", required);
        return;
      }
      const wantChecked = optionBool === target;
      if (f.checked === wantChecked) {
        if (wantChecked) addResult(report, groupLabel, groupCanonical, "already_filled", "Left as-is.", required);
        return;
      }
      const el = _el(f.ja_id);
      if (!el) {
        addResult(report, groupLabel, groupCanonical, "error", "Field disappeared from the page.", required);
        return;
      }
      _setChecked(el, wantChecked);
      if (wantChecked) {
        _mark(f.ja_id, MARK_FILLED);
        addResult(report, groupLabel, groupCanonical, "filled", label, required);
      }
      return;
    }
  }

  if (!BOOLEAN_FIELDS.has(canonical)) {
    addResult(report, label || groupLabel || f.name, canonical, "skipped_no_match", "", required);
    return;
  }

  const value = profile[canonical];
  if (value === null || value === undefined) {
    addResult(report, label, canonical, "skipped_no_data", "", required);
    return;
  }

  if (f.checked === value) {
    addResult(report, label, canonical, "already_filled", "Left as-is.", required);
    return;
  }

  const el = _el(f.ja_id);
  if (!el) {
    addResult(report, label, canonical, "error", "Field disappeared from the page.", required);
    return;
  }
  _setChecked(el, value);
  _mark(f.ja_id, MARK_FILLED);
  addResult(report, label, canonical, "filled", value ? "checked" : "unchecked", required);
}

// A data: URL's base64 payload can be decoded synchronously with atob(),
// unlike fetch(dataUrl) which returns a Promise -- staying synchronous here
// keeps the whole fill pipeline synchronous rather than needing every
// caller up the chain to become async for this one field type.
function _dataUrlToFile(dataUrl, filename) {
  const commaIdx = dataUrl.indexOf(",");
  const meta = dataUrl.slice(5, commaIdx); // strip leading "data:"
  const mime = (meta.split(";")[0] || "application/octet-stream") || "application/octet-stream";
  const binary = atob(dataUrl.slice(commaIdx + 1));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new File([bytes], filename, { type: mime });
}

// Setting a file input's .value is always blocked (browsers refuse to let
// script spoof a local file path), but assigning a FileList built from a
// script-constructed File via DataTransfer is not -- this is the same
// technique testing-library's userEvent.upload() uses, and it fires a real
// 'change' event the page's own upload handler will see.
function _attachFile(el, file) {
  const dt = new DataTransfer();
  dt.items.add(file);
  el.files = dt.files;
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function _handleFileField(profile, report, f) {
  const label = f.label || "";
  const required = f.required || false;

  let canonical, fileInfo, kind;
  if (isResumeLabel(label)) {
    canonical = "resume_file";
    fileInfo = profile.resume_file;
    kind = "resume";
  } else if (isCoverLetterLabel(label)) {
    canonical = "cover_letter_file";
    fileInfo = profile.cover_letter_file;
    kind = "cover letter";
  } else {
    addResult(report, label || "file upload", null, "skipped_no_match", "", required);
    return;
  }

  if (!fileInfo || !fileInfo.dataUrl) {
    _mark(f.ja_id, MARK_REVIEW);
    addResult(
      report, label, canonical, "needs_review",
      `No ${kind} saved -- add one under the extension's Options → Documents tab, or attach it here yourself.`,
      required
    );
    return;
  }

  const el = _el(f.ja_id);
  if (!el) {
    addResult(report, label, canonical, "error", "Field disappeared from the page.", required);
    return;
  }

  try {
    _attachFile(el, _dataUrlToFile(fileInfo.dataUrl, fileInfo.name));
    _mark(f.ja_id, MARK_FILLED);
    addResult(report, label, canonical, "filled", fileInfo.name, required);
  } catch (exc) {
    _mark(f.ja_id, MARK_REVIEW);
    addResult(report, label, canonical, "needs_review", `Could not attach automatically (${exc}) -- attach it here yourself.`, required);
  }
}

function _handleRadioGroup(profile, report, options) {
  const groupLabel = options.find((o) => o.group_label)?.group_label || "";
  const required = options.some((o) => o.required);

  if (options.some((o) => o.checked)) {
    addResult(report, groupLabel, null, "already_filled", "Left as-is.", required);
    return;
  }

  const context = options.find((o) => o.context)?.context || "";
  const wideText = context ? `${groupLabel} ${context}`.trim() : groupLabel;

  const sgroup = sensitiveGroup(wideText);
  if (sgroup) {
    const answer = _savedSensitiveAnswer(profile, wideText, sgroup);
    if (!_isAnswered(answer)) {
      const guess = matchField(wideText);
      _markAll(options, MARK_REVIEW);
      addResult(report, _displayLabel(groupLabel, guess), null, "needs_review", sensitiveReason(wideText), required);
      return;
    }
    const canonical = matchField(wideText);
    const display = _displayLabel(groupLabel, canonical);
    // A yes/no answer ("have you ever been convicted") picks the option that
    // means that; a self-ID answer is the text of the choice itself.
    let idx;
    if (typeof answer === "boolean") {
      idx = options.findIndex((o) => semanticBool(o.label || "") === answer);
      if (idx < 0) idx = null;
    } else {
      idx = bestChoice(answer, options.map((o) => o.label || ""));
    }
    if (idx === null) {
      if (required) _markAll(options, MARK_BLANK);
      addResult(report, display, canonical, "skipped_no_match", `No option matched '${answer}'.`, required);
      return;
    }
    const el = _el(options[idx].ja_id);
    if (!el) {
      addResult(report, display, canonical, "error", "Field disappeared from the page.", required);
      return;
    }
    _setChecked(el, true);
    _mark(options[idx].ja_id, MARK_FILLED);
    addResult(report, display, canonical, "filled", options[idx].label || "", required);
    return;
  }

  const canonical = matchField(groupLabel);
  if (!BOOLEAN_FIELDS.has(canonical)) {
    if (required) _markAll(options, MARK_BLANK);
    addResult(report, groupLabel || options[0].name || "", canonical, "skipped_no_match", "", required);
    return;
  }

  const target = profile[canonical];
  if (target === null || target === undefined) {
    if (required) _markAll(options, MARK_BLANK);
    addResult(report, groupLabel, canonical, "skipped_no_data", "", required);
    return;
  }

  for (const opt of options) {
    const choiceBool = semanticBool(opt.label || "");
    if (choiceBool === target) {
      const el = _el(opt.ja_id);
      if (!el) {
        addResult(report, groupLabel, canonical, "error", "Field disappeared from the page.", required);
        return;
      }
      _setChecked(el, true);
      _mark(opt.ja_id, MARK_FILLED);
      addResult(report, groupLabel, canonical, "filled", opt.label || "", required);
      return;
    }
  }

  if (required) _markAll(options, MARK_BLANK);
  addResult(report, groupLabel, canonical, "skipped_no_match", "No matching Yes/No option found.", required);
}

// ---------------------------------------------------------------------------
// Second pass: apply answers that came back from Claude (see llm.js).
//
// Everything below treats those answers as a suggestion from outside this
// extension, not as instructions. The rules that make this tool safe to point
// at a real application are enforced here, in code, on the way in -- the
// prompt asks for the same behaviour, but a prompt is not a guarantee and
// these are the things that must not go wrong.
// ---------------------------------------------------------------------------

// A dropdown, a text box or a textarea. Deliberately not checkboxes or
// radios: those are how forms ask for consent, and nothing here is going to
// tick a consent box on the applicant's behalf. Not files or passwords
// either -- neither is a question.
var LLM_FILLABLE_TYPES = new Set(["text", "textarea", "select", "email", "tel", "url", "number", "search"]);

var _CONSENT_RE =
  /\b(consent|agree|agreement|authoriz|authoris|certify|acknowledg|e-?sign|signature|opt in|terms and conditions)\b/i;

function _isConsentLike(text) {
  return _CONSENT_RE.test(text || "");
}

// Every field this side is willing to have Claude answer, with both the
// descriptor sent to the API and the local handles needed to apply what
// comes back. Built here and recomputed on the way in, so an answer for
// anything not on this list can be dropped rather than trusted.
function _llmCandidates(report) {
  const fields = report.fields || [];
  const answered = new Set(
    report.results
      .filter((r) => r.action !== "skipped_no_match" && r.action !== "skipped_no_data")
      .map((r) => r.ja_id)
  );

  const offer = (f, descriptor, jaIds) => ({ field: f, descriptor, jaIds });
  const out = [];

  // Radio groups are offered as one question with its options, the way a
  // person reads them -- but only ever as a question. A consent or self-ID
  // group is filtered out below like any other, and applying an answer can
  // only ever select one of the group's own options.
  const radioGroups = new Map();
  for (const f of fields) {
    if (f.type !== "radio") continue;
    const key = f.name || f.ja_id;
    if (!radioGroups.has(key)) radioGroups.set(key, []);
    radioGroups.get(key).push(f);
  }

  const blocked = (label, groupLabel, context) => {
    const wide = context ? `${label || ""} ${context}` : label || "";
    if (sensitiveGroup(wide)) return true;
    if (_isConsentLike(label) || _isConsentLike(groupLabel)) return true;
    if (isEscapeHatchLabel(label)) return true;
    return false;
  };

  for (const f of fields) {
    if (f.type === "radio" || f.type === "checkbox") continue;
    if (answered.has(f.ja_id)) continue;
    if (f.has_value) continue;
    if (!LLM_FILLABLE_TYPES.has(f.type) && f.tag !== "select") continue;
    if (blocked(f.label, f.group_label, f.context)) continue;
    if (!f.label && !f.group_label && !f.section) continue;
    out.push(
      offer(f, {
        ja_id: f.ja_id,
        label: f.label || "",
        group_label: f.group_label || "",
        section: f.section || "",
        // A textarea has no type attribute of its own, and "this is a
        // paragraph box, not a one-liner" is exactly what shapes the answer.
        type: f.tag === "select" ? "select" : f.tag === "textarea" ? "textarea" : f.type,
        required: !!f.required,
        max_length: f.max_length || null,
        options: (f.options || []).map((o) => o.text).filter(Boolean),
      }, [f.ja_id])
    );
  }

  for (const group of radioGroups.values()) {
    const head = group[0];
    if (answered.has(head.ja_id)) continue;
    if (group.some((o) => o.checked)) continue;
    const question = group.find((o) => o.group_label)?.group_label || "";
    const context = group.find((o) => o.context)?.context || "";
    if (blocked(question, question, context)) continue;
    if (group.some((o) => _isConsentLike(o.label))) continue;
    if (!question) continue;
    out.push(
      offer(head, {
        ja_id: head.ja_id,
        label: question,
        group_label: "",
        section: head.section || "",
        type: "radio",
        required: group.some((o) => o.required),
        max_length: null,
        options: group.map((o) => o.label || "").filter(Boolean),
      }, group.map((o) => o.ja_id))
    );
  }

  return out;
}

function llmFieldsFor(report) {
  return _llmCandidates(report).map((c) => c.descriptor);
}

async function _applyLlmSelect(f, el, value) {
  let options = f.options || [];
  let opened = null;
  if (f.widget === "listbox_button") {
    opened = await _openListbox(el);
    if (!opened) return false;
    options = opened.options;
  } else if (f.widget === "icims") {
    _openIcims(el);
  }

  // An exact option string was asked for; anything less is the model
  // approximating, and picking the wrong item out of a dropdown is worse
  // than leaving it for the applicant.
  const wanted = normalize(value);
  const match = options.find((o) => normalize(o.text) === wanted);
  if (!match) {
    if (opened) _closeListbox(el, opened);
    return false;
  }

  if (opened) return _clickListboxOption(el, opened, options.indexOf(match));
  if (f.widget === "icims") return _setIcimsValue(el, match.value, match.text);
  _setSelectValue(el, match.value);
  return true;
}

function _applyLlmRadio(byId, candidate, value) {
  const wanted = normalize(value);
  // Only ever one of this group's own options -- the model returns text, and
  // text that isn't one of the choices selects nothing.
  const chosen = candidate.jaIds
    .map((id) => byId.get(id))
    .find((f) => f && normalize(f.label || "") === wanted);
  if (!chosen) return false;
  const el = _el(chosen.ja_id);
  if (!el) return false;
  _setChecked(el, true);
  _mark(chosen.ja_id, MARK_FILLED);
  return true;
}

// A label Claude resolved to something already in the profile is a label
// worth remembering: next time it matches for free, instantly, with no API
// call. Only mappings are learned, never the prose -- a cover letter or an
// essay answer written for one job has no business being reused at another.
function learnFromAnswers(report, answers, profile) {
  const byId = new Map((report.fields || []).map((f) => [f.ja_id, f]));
  const learned = {};
  for (const [jaId, value] of Object.entries(answers || {})) {
    const f = byId.get(jaId);
    const label = normalize(f && f.label);
    if (!label || !value) continue;
    // Already known by name; nothing to learn.
    if (matchField(f.label)) continue;
    for (const [key, saved] of Object.entries(profile || {})) {
      if (typeof saved !== "string" && typeof saved !== "number") continue;
      if (String(saved) && String(saved) === String(value)) {
        learned[label] = key;
        break;
      }
    }
  }
  return learned;
}

async function applyLlmAnswers(report, answers, skipped) {
  const byId = new Map((report.fields || []).map((f) => [f.ja_id, f]));
  const candidates = new Map(_llmCandidates(report).map((c) => [c.descriptor.ja_id, c]));
  let filled = 0;

  for (const [jaId, value] of Object.entries(answers || {})) {
    // Only fields this side offered up in the first place. An answer for
    // anything else -- a consent box, a self-ID question, a field that was
    // already filled -- is dropped without being applied.
    const candidate = candidates.get(jaId);
    if (!candidate || !value) continue;
    const f = candidate.field;

    let applied;
    try {
      if (candidate.descriptor.type === "radio") {
        applied = _applyLlmRadio(byId, candidate, value);
      } else {
        const el = _el(jaId);
        if (!el) continue;
        if (f.tag === "select") {
          applied = await _applyLlmSelect(f, el, value);
        } else {
          _setNativeValue(el, value);
          _mark(jaId, MARK_FILLED);
          applied = true;
        }
      }
    } catch (exc) {
      applied = false;
    }
    if (!applied) continue;

    if (f.tag === "select") _mark(jaId, MARK_FILLED);
    filled += 1;
    const result = report.results.find((r) => r.ja_id === jaId);
    if (result) {
      result.action = "filled";
      result.canonical = "claude";
      result.detail = value;
    } else {
      addResult(report, f.label || "", "claude", "filled", value, !!f.required);
    }
  }

  // Say why, on the field itself, when Claude declined one -- otherwise a
  // sensitive question it correctly refused looks identical to one it never
  // saw.
  for (const [jaId, reason] of Object.entries(skipped || {})) {
    const result = report.results.find((r) => r.ja_id === jaId);
    if (result && result.action === "skipped_no_match" && reason) {
      result.detail = reason === "sensitive" ? "Left for you to answer." : reason;
    }
  }

  return filled;
}
