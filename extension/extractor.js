// Scans the current page's DOM for fillable fields and tags each one so it
// can be reliably re-selected. Ported from the Playwright-injected script in
// ja/extractor.py -- keep the two in sync, except for the custom-widget
// dropdown handling below (iCIMS/Workday), which is browser-extension only:
// driving those needs click-and-wait interaction the Python side's
// one-shot extract-then-fill pipeline has no place for.
"use strict";

function extractFields() {
  function cleanText(s) {
    return (s || "").replace(/\s+/g, " ").trim();
  }
  function isVisible(el) {
    if (el.disabled) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
  function stripControlsText(node) {
    const clone = node.cloneNode(true);
    clone.querySelectorAll("input, select, textarea").forEach((n) => n.remove());
    return cleanText(clone.innerText || clone.textContent || "");
  }

  function labelForById(id) {
    if (!id) return "";
    try {
      const el = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      return el ? stripControlsText(el) : "";
    } catch (e) {
      return "";
    }
  }
  function ariaLabelledBy(el) {
    const ids = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean);
    if (!ids.length) return "";
    return cleanText(
      ids
        .map((id) => {
          const t = document.getElementById(id);
          return t ? t.innerText : "";
        })
        .join(" ")
    );
  }
  function closestLabelWrap(el) {
    const l = el.closest("label");
    return l ? stripControlsText(l) : "";
  }
  function automationIdWords(el) {
    const id = el.getAttribute("data-automation-id") || "";
    if (!id) return "";
    return cleanText(id.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[-_]/g, " "));
  }
  function hasControl(node) {
    return (
      ["INPUT", "SELECT", "TEXTAREA"].includes(node.tagName) ||
      !!node.querySelector("input, select, textarea")
    );
  }

  function nearestPrecedingText(el) {
    let node = el.previousElementSibling;
    let hops = 0;
    while (node && hops < 4) {
      if (!hasControl(node)) {
        const t = cleanText(node.innerText || "");
        if (t && t.length < 200) return t;
      }
      node = node.previousElementSibling;
      hops++;
    }
    return "";
  }
  function labelFor(el) {
    return (
      cleanText(el.getAttribute("aria-label")) ||
      labelForById(el.id) ||
      ariaLabelledBy(el) ||
      closestLabelWrap(el) ||
      cleanText(el.getAttribute("placeholder")) ||
      automationIdWords(el) ||
      nearestPrecedingText(el)
    );
  }
  function isOptionWord(t) {
    return /^(yes|no|y|n|n\/a|true|false|other)$/i.test((t || "").trim());
  }

  function stripOptionControls(clone) {
    const ids = new Set();
    clone
      .querySelectorAll(
        'select, textarea, input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="image"]):not([type="reset"])'
      )
      .forEach((n) => {
        if (n.id) ids.add(n.id);
        const wrap = n.closest("label");
        (wrap || n).remove();
      });
    clone.querySelectorAll("label[for]").forEach((l) => {
      if (ids.has(l.getAttribute("for"))) l.remove();
    });
    return clone;
  }

  function containerQuestion(node, ownLabel) {
    if (!node || node.tagName === "LABEL") return "";
    if (!node.querySelector("input, select, textarea")) return "";
    const clone = stripOptionControls(node.cloneNode(true));
    const t = cleanText(clone.textContent || "");
    if (t.length < 3 || t.length > 300) return "";
    if (ownLabel && t.toLowerCase() === ownLabel.toLowerCase()) return "";
    return t;
  }

  function controlCount(node) {
    const radioNames = new Set();
    node.querySelectorAll('input[type="radio"]').forEach((r) => radioNames.add(r.name || Math.random()));
    const other = node.querySelectorAll(
      'select, input:not([type="radio"]):not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="image"]):not([type="reset"]), textarea'
    ).length;
    return radioNames.size + other;
  }

  function wideContext(el) {
    const idWords = cleanText(
      ((el.id || "") + " " + (el.getAttribute("name") || ""))
        .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
        .replace(/[-_]/g, " ")
    );

    let node = el.closest("fieldset") || el.parentElement;
    if (!node) return idWords;
    const ownCount = controlCount(node);
    if (ownCount > 2) return idWords;
    for (let depth = 0; depth < 6; depth++) {
      const parent = node.parentElement;
      if (!parent || parent.tagName === "FORM" || parent.tagName === "BODY") break;
      if (controlCount(parent) > ownCount) break;
      node = parent;
    }
    const clone = stripOptionControls(node.cloneNode(true));
    const climbed = cleanText(clone.textContent || "");
    return (idWords + " " + climbed).trim().slice(0, 4000);
  }

  function groupLabelFor(el, ownLabel) {
    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      if (legend) return cleanText(legend.innerText);
    }
    const groupRoot = el.closest('[role="radiogroup"], [role="group"]');
    if (groupRoot) {
      const aria = cleanText(groupRoot.getAttribute("aria-label"));
      if (aria) return aria;
      const heading = groupRoot.querySelector('legend, [class*="label" i], [class*="question" i]');
      if (heading && !heading.contains(el)) return cleanText(heading.innerText);
    }
    let node = el.parentElement;
    for (let depth = 0; node && depth < 5; depth++, node = node.parentElement) {
      const own = containerQuestion(node, ownLabel);
      if (own) return own;
      if (node.tagName === "LABEL") continue;
      const prev = nearestPrecedingText(node);
      if (prev && !isOptionWord(prev) && prev.toLowerCase() !== (ownLabel || "").toLowerCase()) {
        return prev;
      }
    }
    return "";
  }

  // The nearest enclosing fieldset's <legend>. iCIMS wraps a whole
  // work-history or education block in one <fieldset> whose <legend>
  // ("Professional Experience (1)") is the only place that phrase appears --
  // the fields inside it carry opaque machine names (rcf3212, rcf3213) and
  // bare labels ("Employer", "Title", "City"), so the section is the only
  // signal that "City" means the employer's city and not the applicant's.
  function sectionLabel(el) {
    const fs = el.closest("fieldset");
    if (!fs) return "";
    const legend = fs.querySelector("legend");
    return legend ? cleanText(legend.innerText || legend.textContent) : "";
  }

  // iCIMS hides the real <select> (class dropdown-hide, holding nothing but
  // an empty placeholder <option>) and paints its own widget in its place:
  // an <a class="dropdown-select"> showing the current choice, and a
  // <ul class="dropdown-results"> of <li role="option"> holding the real
  // options. So the choices are never <option> elements, and the <select>
  // itself is display:none -- without this the field isn't even seen, and
  // there'd be nothing to match a value against if it were. Its own click
  // handler on the <li> is what writes the answer back, so the widget is
  // what has to be driven, not the <select>.
  function icimsWidget(el) {
    if (!el.id || el.getAttribute("icimsdropdown-enabled") !== "1") return null;
    const list = document.getElementById(el.id + "_dropdown-results");
    const anchor = document.getElementById(el.id + "_icimsDropdown");
    if (!list || !anchor) return null;
    const items = Array.from(list.querySelectorAll('[role="option"]'));
    if (!items.length) return null;
    return { anchor, items };
  }

  function icimsHasValue(el) {
    const fake = document.getElementById(el.id + "_fakeSelected_icimsDropdown");
    if (!fake) return false;
    // Its placeholder state is a <span class="dropdown-placeholder">
    // reading "- Make a Selection -", which is text like any other.
    if (fake.querySelector(".dropdown-placeholder")) return false;
    return !!cleanText(fake.textContent);
  }

  // aria-haspopup="listbox" is a contract: activating the control renders a
  // [role="listbox"] whose [role="option"] children are the choices.
  // Workday's questionnaire dropdowns are built that way -- a <button> with
  // no <select> anywhere and no options in the DOM at all until it's
  // clicked -- so they can only be read by opening them (see filler.js).
  function listboxButtonLabel(el) {
    const group = groupLabelFor(el, "");
    if (group) return group;
    const aria = cleanText(el.getAttribute("aria-label"));
    // Workday's own aria-label on these is the placeholder text
    // (" Select One Required"), which says nothing about the question.
    return /^select one\b/i.test(aria) ? "" : aria;
  }

  function listboxButtonHasValue(el) {
    const text = cleanText(el.textContent);
    if (!text || /^select( one|\.\.\.)?$/i.test(text)) return false;
    return true;
  }

  function listboxButtonRequired(el) {
    if (el.getAttribute("aria-required") === "true") return true;
    if (/\brequired\b/i.test(el.getAttribute("aria-label") || "")) return true;
    const fs = el.closest("fieldset");
    return !!(fs && fs.querySelector('abbr[title="required"], .requiredAsterisk'));
  }

  // Clear ids AND the colored outline from any previous run -- a field
  // that's now already_filled is never revisited to redraw its outline,
  // so last run's red/amber/green ring would otherwise persist even after
  // the field is fine (e.g. you answered it yourself, or a later refill on
  // a multi-step form just doesn't touch it again).
  document.querySelectorAll("[data-ja-id]").forEach((el) => {
    el.removeAttribute("data-ja-id");
    el.style.outline = "";
    el.style.outlineOffset = "";
  });

  const SKIP_TYPES = new Set(["hidden", "submit", "button", "image", "reset"]);
  const nodes = Array.from(
    document.querySelectorAll('input, select, textarea, button[aria-haspopup="listbox"]')
  );
  const results = [];
  let idx = 0;

  for (const el of nodes) {
    const tag = el.tagName.toLowerCase();

    if (tag === "button") {
      if (!isVisible(el)) continue;
      const jaId = "ja-" + idx++;
      el.setAttribute("data-ja-id", jaId);
      results.push({
        ja_id: jaId,
        // Reported as a select because that is what it is to the applicant
        // and to every downstream decision -- pick one of a list of
        // options -- with `widget` saying how it has to be driven.
        tag: "select",
        type: "select",
        widget: "listbox_button",
        name: el.getAttribute("name") || "",
        id: el.id || "",
        required: listboxButtonRequired(el),
        label: listboxButtonLabel(el),
        section: sectionLabel(el),
        context: wideContext(el),
        // Genuinely unknown until the popup is opened.
        options: [],
        has_value: listboxButtonHasValue(el),
      });
      continue;
    }

    const type = (el.getAttribute("type") || (tag === "select" ? "select" : "text")).toLowerCase();
    if (tag === "input" && SKIP_TYPES.has(type)) continue;
    // Workday pairs each listbox button with a bare sibling text input used
    // as its typeahead proxy. It has no label of its own, so it would match
    // on the button's placeholder text and add a phantom field to the
    // report for every question on the page.
    if (
      tag === "input" &&
      el.previousElementSibling &&
      el.previousElementSibling.matches('button[aria-haspopup="listbox"]')
    ) {
      continue;
    }

    const widget = tag === "select" ? icimsWidget(el) : null;
    // The real <select> behind an iCIMS widget is display:none by design;
    // what the applicant sees and clicks is the widget's own anchor.
    if (!isVisible(el) && !(widget && isVisible(widget.anchor))) continue;

    const jaId = "ja-" + idx++;
    el.setAttribute("data-ja-id", jaId);

    const item = {
      ja_id: jaId,
      tag,
      type,
      name: el.getAttribute("name") || "",
      id: el.id || "",
      // i_required is iCIMS's own flag; its forms set nothing else, so
      // without it every required field there reads as optional and none of
      // the ones left blank get the red outline that asks to be looked at.
      required: !!(
        el.required ||
        el.getAttribute("aria-required") === "true" ||
        el.getAttribute("i_required") === "true"
      ),
      section: sectionLabel(el),
    };

    if (type === "radio" || type === "checkbox") {
      item.label = labelFor(el);
      item.group_label = groupLabelFor(el, item.label);
      item.context = wideContext(el);
      item.checked = !!el.checked;
    } else if (tag === "select" && widget) {
      item.widget = "icims";
      item.label = labelFor(el);
      item.aria_label = ariaLabelledBy(el);
      item.context = wideContext(el);
      // The widget's own first <li> is a "- Make a Selection -" placeholder,
      // so this list lines up with a plain <select>'s options including its
      // leading placeholder <option>. The id is the handle to click.
      item.options = widget.items.map((li) => ({
        value: li.id,
        text: cleanText(li.getAttribute("title") || li.textContent),
      }));
      item.has_value = icimsHasValue(el);
    } else if (tag === "select") {
      item.label = labelFor(el);
      item.aria_label = ariaLabelledBy(el);
      item.context = wideContext(el);
      item.options = Array.from(el.options).map((o) => ({ value: o.value, text: cleanText(o.text) }));
      // See ja/extractor.py's matching comment: some templated forms
      // duplicate the leading placeholder option, which can leave
      // selectedIndex resolving to 1 instead of 0 even though nothing was
      // ever really chosen -- el.value still correctly reads "" for an
      // explicit value="" attribute, so requiring both catches that case.
      item.has_value = el.selectedIndex > 0 && el.value !== "";
    } else if (type === "file") {
      item.label = labelFor(el);
      item.has_value = !!(el.files && el.files.length);
    } else {
      item.label = labelFor(el);
      // A split date control labels each box "Month"/"Day"/"Year" via
      // <label for>, and names the question it belongs to only in
      // aria-labelledby -- so both halves are needed to place the box.
      item.aria_label = ariaLabelledBy(el);
      // How much room the box gives is the clearest signal of how long an
      // answer it wants.
      item.max_length = el.maxLength > 0 ? el.maxLength : null;
      item.context = wideContext(el);
      item.is_datepicker = /datepicker/i.test(el.className || "");
      item.has_value = !!el.value;
    }

    results.push(item);
  }

  return results;
}

// What job this page is for. Without it, an answer to "why do you want this
// role?" can only be generic -- it is the difference between a paragraph
// about the applicant and a paragraph about the applicant and this job.
// Best effort and capped: an application page often doesn't restate the
// posting, and page text is the one input here that has no natural size.
function extractJobContext() {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const meta = (key) => {
    const el = document.querySelector(`meta[property="${key}"], meta[name="${key}"]`);
    return clean(el && el.getAttribute("content"));
  };

  const title =
    clean(document.querySelector('[data-automation-id="jobPostingHeader"]')?.textContent) ||
    meta("og:title") ||
    clean(document.querySelector("h1")?.textContent) ||
    clean(document.title);

  const company = meta("og:site_name") || location.hostname.replace(/^www\./, "");

  // The posting body, if this page still shows it. Headers, navigation and
  // the form itself are noise; a description is the longest run of prose.
  let description = "";
  const candidates = document.querySelectorAll(
    '[data-automation-id="jobPostingDescription"], [class*="description" i], ' +
      '[class*="job-detail" i], [id*="description" i], article, main'
  );
  for (const node of candidates) {
    if (node.querySelector("input, select, textarea")) continue;
    const text = clean(node.innerText || node.textContent);
    if (text.length > description.length) description = text;
  }

  return {
    title: title.slice(0, 200),
    company: company.slice(0, 120),
    description: description.slice(0, 1500),
    url: location.href.slice(0, 300),
  };
}
