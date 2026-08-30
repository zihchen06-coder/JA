"""Scans the current page's DOM for fillable fields and tags each one so it
can be reliably re-selected from Python via a Playwright locator.
"""

from __future__ import annotations

from typing import Any

# Marks every fillable, visible, enabled element with data-ja-id="ja-<n>" and
# returns a description of each: tag, type, best-guess label, whether it's
# required, and (for selects/radio groups) the available choices.
_EXTRACT_JS = r"""
() => {
  function cleanText(s) {
    return (s || '').replace(/\s+/g, ' ').trim();
  }
  function isVisible(el) {
    if (el.disabled) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
  function labelForById(id) {
    if (!id) return '';
    try {
      const el = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      return el ? cleanText(el.innerText) : '';
    } catch (e) { return ''; }
  }
  function ariaLabelledBy(el) {
    const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    if (!ids.length) return '';
    return cleanText(ids.map(id => {
      const t = document.getElementById(id);
      return t ? t.innerText : '';
    }).join(' '));
  }
  function closestLabelWrap(el) {
    const l = el.closest('label');
    if (!l) return '';
    const clone = l.cloneNode(true);
    clone.querySelectorAll('input,select,textarea').forEach(n => n.remove());
    return cleanText(clone.innerText);
  }
  function automationIdWords(el) {
    const id = el.getAttribute('data-automation-id') || '';
    if (!id) return '';
    return cleanText(id.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[-_]/g, ' '));
  }
  function hasControl(node) {
    return ['INPUT', 'SELECT', 'TEXTAREA'].includes(node.tagName) ||
           !!node.querySelector('input, select, textarea');
  }

  function nearestPrecedingText(el) {
    let node = el.previousElementSibling;
    let hops = 0;
    while (node && hops < 4) {
      // A sibling that IS or CONTAINS a form control is another question
      // (or the same one), not descriptive heading text -- a <select>'s
      // own rendered innerText is its option list, and a radio group's
      // wrapper is its own answer choices. Neither is a caption worth
      // reading, so skip over it entirely rather than mistaking it for one.
      if (!hasControl(node)) {
        const t = cleanText(node.innerText || '');
        if (t && t.length < 200) return t;
      }
      node = node.previousElementSibling;
      hops++;
    }
    return '';
  }
  function labelFor(el) {
    return (
      cleanText(el.getAttribute('aria-label')) ||
      labelForById(el.id) ||
      ariaLabelledBy(el) ||
      closestLabelWrap(el) ||
      cleanText(el.getAttribute('placeholder')) ||
      automationIdWords(el) ||
      nearestPrecedingText(el)
    );
  }
  // The text of a container with the option controls (and their own
  // "Yes"/"No" labels) stripped out -- i.e. the question those options
  // answer. Many forms wrap a question and its radios in a plain <div>
  // with no <fieldset>, so this is the only way to recover the question.
  function isOptionWord(t) {
    return /^(yes|no|y|n|n\/a|true|false|other)$/i.test((t || '').trim());
  }

  function containerQuestion(node, ownLabel) {
    if (!node || node.tagName === 'LABEL') return '';
    if (!node.querySelector('input, select, textarea')) return '';
    const clone = node.cloneNode(true);
    clone.querySelectorAll('input, select, textarea').forEach(n => {
      const wrap = n.closest('label');
      (wrap || n).remove();
    });
    clone.querySelectorAll('label[for]').forEach(l => l.remove());
    const t = cleanText(clone.textContent || '');
    if (t.length < 3 || t.length > 300) return '';
    // The control's own "Yes"/"No" text is not the question it answers.
    if (ownLabel && t.toLowerCase() === ownLabel.toLowerCase()) return '';
    return t;
  }

  // How many distinct question-controls a node contains -- selects count
  // individually, radios are grouped by name (three same-name radios are
  // one question), checkboxes and text-ish inputs count individually. Used
  // to tell "still inside this one question's wrapper" apart from "climbed
  // into a sibling question (or the whole form)".
  function controlCount(node) {
    const radioNames = new Set();
    node.querySelectorAll('input[type="radio"]').forEach(r => radioNames.add(r.name || Math.random()));
    const other = node.querySelectorAll(
      'select, input:not([type="radio"]):not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="image"]):not([type="reset"]), textarea'
    ).length;
    return radioNames.size + other;
  }

  // A much wider net than groupLabelFor/containerQuestion, used only as a
  // fallback for detecting EEO/self-identification questions. The federal
  // CC-305 disability form and similar boilerplate can run to thousands of
  // characters between the section heading and the actual radio buttons --
  // the 300-char cap that keeps groupLabelFor's short display label sane
  // means that heading is often out of reach entirely. This climbs further
  // and keeps whatever it finds, since it is only ever substring-matched
  // against known keywords, never shown to the user or used as a display
  // label -- but climbing is bounded by CONTENT, not just depth: many real
  // forms put every field as a flat sibling with no per-question wrapper,
  // so the very first ancestor can already be the whole form. Widening
  // stops the moment an ancestor holds more controls than the field
  // started with, since that means it has crossed into unrelated
  // questions rather than found a wrapper around just this one.
  function wideContext(el) {
    // Many ATS platforms give the element itself a telling id/name even
    // when its visible label is distant or absent -- JazzHR names every
    // EEO field "resumator-eeo_race-value", "resumator-eeo_disability-
    // value", and so on, consistently, across every company on the
    // platform. This is safe to always include: unlike climbing ancestors,
    // an element's own id/name can never accidentally pull in a
    // *different* question's text.
    const idWords = cleanText(
      ((el.id || '') + ' ' + (el.getAttribute('name') || ''))
        .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
        .replace(/[-_]/g, ' ')
    );

    let node = el.closest('fieldset') || el.parentElement;
    if (!node) return idWords;
    const ownCount = controlCount(node);
    if (ownCount > 2) return idWords; // already broader than a single question
    for (let depth = 0; depth < 6; depth++) {
      const parent = node.parentElement;
      if (!parent || parent.tagName === 'FORM' || parent.tagName === 'BODY') break;
      if (controlCount(parent) > ownCount) break;
      node = parent;
    }
    const clone = node.cloneNode(true);
    clone.querySelectorAll('input, select, textarea').forEach(n => {
      const wrap = n.closest('label');
      (wrap || n).remove();
    });
    clone.querySelectorAll('label[for]').forEach(l => l.remove());
    const climbed = cleanText(clone.textContent || '');
    return (idWords + ' ' + climbed).trim().slice(0, 4000);
  }

  function groupLabelFor(el, ownLabel) {
    const fieldset = el.closest('fieldset');
    if (fieldset) {
      const legend = fieldset.querySelector('legend');
      if (legend) return cleanText(legend.innerText);
    }
    const groupRoot = el.closest('[role="radiogroup"], [role="group"]');
    if (groupRoot) {
      const aria = cleanText(groupRoot.getAttribute('aria-label'));
      if (aria) return aria;
      const heading = groupRoot.querySelector('legend, [class*="label" i], [class*="question" i]');
      if (heading && !heading.contains(el)) return cleanText(heading.innerText);
    }
    // Widen out from the control until a wrapper carries question text.
    // A <label> is never the question -- it is one option's own text -- and
    // text preceding one is a sibling option ("Yes" before "No"), not the
    // question either, so keep climbing past both.
    let node = el.parentElement;
    for (let depth = 0; node && depth < 5; depth++, node = node.parentElement) {
      const own = containerQuestion(node, ownLabel);
      if (own) return own;
      if (node.tagName === 'LABEL') continue;
      const prev = nearestPrecedingText(node);
      if (prev && !isOptionWord(prev) && prev.toLowerCase() !== (ownLabel || '').toLowerCase()) {
        return prev;
      }
    }
    return '';
  }

  // Clear ids from any previous scan. Elements that have since become
  // hidden would otherwise keep a stale id and collide with a freshly
  // assigned one, making the Python-side locator ambiguous.
  document.querySelectorAll('[data-ja-id]').forEach(el => el.removeAttribute('data-ja-id'));

  const SKIP_TYPES = new Set(['hidden', 'submit', 'button', 'image', 'reset']);
  const nodes = Array.from(document.querySelectorAll('input, select, textarea'));
  const results = [];
  let idx = 0;

  for (const el of nodes) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || (tag === 'select' ? 'select' : 'text')).toLowerCase();
    if (tag === 'input' && SKIP_TYPES.has(type)) continue;
    if (!isVisible(el)) continue;

    const jaId = 'ja-' + (idx++);
    el.setAttribute('data-ja-id', jaId);

    const item = {
      ja_id: jaId,
      tag,
      type,
      name: el.getAttribute('name') || '',
      required: !!(el.required || el.getAttribute('aria-required') === 'true'),
    };

    if (type === 'radio' || type === 'checkbox') {
      item.label = labelFor(el);
      item.group_label = groupLabelFor(el, item.label);
      item.context = wideContext(el);
      item.checked = !!el.checked;
    } else if (tag === 'select') {
      item.label = labelFor(el);
      item.context = wideContext(el);
      item.options = Array.from(el.options).map(o => ({ value: o.value, text: cleanText(o.text) }));
      // A <select> with no explicit value="" on its first <option> defaults
      // el.value to that option's own TEXT ("-- No answer --", "Select...")
      // -- so !!el.value is true before the user ever touches it. The first
      // option being a not-yet-chosen placeholder is close to universal
      // convention, so selectedIndex > 0 is what actually means "answered".
      item.has_value = el.selectedIndex > 0;
    } else if (type === 'file') {
      item.label = labelFor(el);
      item.has_value = !!(el.files && el.files.length);
    } else {
      item.label = labelFor(el);
      item.has_value = !!el.value;
    }

    results.push(item);
  }

  return results;
}
"""


def extract_fields(page: Any) -> list[dict]:
    """Run the DOM scan on the given Playwright page and return field descriptors."""
    return page.evaluate(_EXTRACT_JS)
