// Scans the current page's DOM for fillable fields and tags each one so it
// can be reliably re-selected. Ported verbatim from the Playwright-injected
// script in ja/extractor.py -- keep the two in sync.
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
  const nodes = Array.from(document.querySelectorAll("input, select, textarea"));
  const results = [];
  let idx = 0;

  for (const el of nodes) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || (tag === "select" ? "select" : "text")).toLowerCase();
    if (tag === "input" && SKIP_TYPES.has(type)) continue;
    if (!isVisible(el)) continue;

    const jaId = "ja-" + idx++;
    el.setAttribute("data-ja-id", jaId);

    const item = {
      ja_id: jaId,
      tag,
      type,
      name: el.getAttribute("name") || "",
      required: !!(el.required || el.getAttribute("aria-required") === "true"),
    };

    if (type === "radio" || type === "checkbox") {
      item.label = labelFor(el);
      item.group_label = groupLabelFor(el, item.label);
      item.context = wideContext(el);
      item.checked = !!el.checked;
    } else if (tag === "select") {
      item.label = labelFor(el);
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
      item.context = wideContext(el);
      item.is_datepicker = /datepicker/i.test(el.className || "");
      item.has_value = !!el.value;
    }

    results.push(item);
  }

  return results;
}
