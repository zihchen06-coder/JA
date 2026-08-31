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

function _mark(jaId, color) {
  const el = _el(jaId);
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

function _selfIdAnswer(profile, label, group) {
  if (group !== "demographic") return null;
  const canonical = matchField(label);
  if (!canonical || !SELF_ID_FIELDS.has(canonical)) return null;
  const value = profile[canonical];
  return value || null;
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
function fillForm(profile, creds) {
  const report = makeReport(detectPlatform(location.href));
  const fieldsData = extractFields();

  const simpleFields = fieldsData.filter((f) => f.type !== "radio");
  const radios = fieldsData.filter((f) => f.type === "radio");

  for (const f of simpleFields) {
    _handleSimpleField(profile, report, f, creds);
  }

  const byName = new Map();
  for (const f of radios) {
    if (!byName.has(f.name)) byName.set(f.name, []);
    byName.get(f.name).push(f);
  }
  for (const group of byName.values()) {
    _handleRadioGroup(profile, report, group);
  }

  return report;
}

function _handleSimpleField(profile, report, f, creds) {
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
    const answer = _selfIdAnswer(profile, wideText, group);
    if (!answer) {
      const guess = matchField(wideText);
      _mark(f.ja_id, MARK_REVIEW);
      addResult(report, _displayLabel(label, guess), null, "needs_review", sensitiveReason(wideText), required);
      return;
    }
    canonical = matchField(wideText);
    label = _displayLabel(label, canonical);
    value = answer;
  } else {
    if (ftype === "checkbox") {
      _handleCheckbox(profile, report, f);
      return;
    }

    canonical = matchField(label);
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
      const options = f.options || [];
      let optionValue, detail;
      if (BOOLEAN_FIELDS.has(canonical) && typeof value === "boolean") {
        const match = options.find((o) => semanticBool(o.text || "") === value);
        optionValue = match ? match.value : null;
        detail = match ? match.text || "" : "";
      } else {
        const realOptions = options.length > 1 ? options.slice(1) : options;
        const allBoolShaped = realOptions.length > 0 && realOptions.every((o) => semanticBool(o.text || "") !== null);
        if (allBoolShaped) {
          if (required) _mark(f.ja_id, MARK_BLANK);
          addResult(
            report, label, canonical, "skipped_no_match",
            "This looks like a yes/no question with no matching saved answer.", required
          );
          return;
        }
        optionValue = bestOption(String(value), options);
        detail = String(value);
      }
      if (optionValue === null || optionValue === undefined) {
        if (required) _mark(f.ja_id, MARK_BLANK);
        addResult(report, label, canonical, "skipped_no_match", `No option matched '${value}'.`, required);
        return;
      }
      _setSelectValue(el, optionValue);
      _mark(f.ja_id, MARK_FILLED);
      addResult(report, label, canonical, "filled", detail, required);
    } else {
      let fillValue;
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

function _handleCheckbox(profile, report, f) {
  const label = f.label || "";
  const groupLabel = f.group_label || "";
  const required = f.required || false;
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
    const answer = _selfIdAnswer(profile, wideText, sgroup);
    if (!answer) {
      const guess = matchField(wideText);
      _markAll(options, MARK_REVIEW);
      addResult(report, _displayLabel(groupLabel, guess), null, "needs_review", sensitiveReason(wideText), required);
      return;
    }
    const canonical = matchField(wideText);
    const display = _displayLabel(groupLabel, canonical);
    const idx = bestChoice(answer, options.map((o) => o.label || ""));
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
