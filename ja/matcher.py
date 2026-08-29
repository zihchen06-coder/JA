"""Heuristic matching from a form field's visible label to a profile field."""

from __future__ import annotations

import difflib
import re

from .field_aliases import (
    COVER_LETTER_KEYWORDS,
    EEO_KEYWORDS,
    FALSE_WORDS,
    FIELD_ALIASES,
    RESUME_KEYWORDS,
    TRUE_WORDS,
)

_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = (text or "").lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def is_eeo_label(label: str) -> bool:
    norm = normalize(label)
    return any(kw in norm for kw in EEO_KEYWORDS)


def is_resume_label(label: str) -> bool:
    norm = normalize(label)
    return any(kw in norm for kw in RESUME_KEYWORDS) and not is_cover_letter_label(label)


def is_cover_letter_label(label: str) -> bool:
    norm = normalize(label)
    return any(kw in norm for kw in COVER_LETTER_KEYWORDS)


def _contains_whole(alias: str, norm: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", norm) is not None


def match_field(label: str, min_ratio: float = 0.72) -> str | None:
    """Return the canonical profile field name a form label most likely refers to.

    Whole-word substring matches are tried first, since they're unambiguous;
    among those, the most specific alias wins (more words, then more
    characters) so a generic word like "address" doesn't beat a more
    specific phrase like "e mail" just because it happens to be longer.
    Fuzzy (typo-tolerant) matching is only used when nothing contains a
    known alias outright.
    """
    norm = normalize(label)
    if not norm:
        return None

    best_field = None
    best_key = (-1, -1)
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias == norm:
                return canonical
            if _contains_whole(alias, norm):
                key = (alias.count(" ") + 1, len(alias))
                if key > best_key:
                    best_key, best_field = key, canonical
    if best_field:
        return best_field

    best_score = 0.0
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            ratio = difflib.SequenceMatcher(None, alias, norm).ratio()
            if ratio > best_score:
                best_score, best_field = ratio, canonical

    return best_field if best_score >= min_ratio else None


def best_option(target_value: str, options: list[dict], min_ratio: float = 0.5) -> str | None:
    """Given a free-text profile value, find the closest matching <select> option value."""
    norm_target = normalize(str(target_value))
    if not norm_target:
        return None

    best_value, best_score = None, 0.0
    for opt in options:
        text = normalize(opt.get("text", ""))
        if not text:
            continue
        if text == norm_target:
            return opt.get("value")
        ratio = difflib.SequenceMatcher(None, text, norm_target).ratio()
        if norm_target in text or text in norm_target:
            ratio += 0.25
        if ratio > best_score:
            best_score, best_value = ratio, opt.get("value")

    return best_value if best_score >= min_ratio else None


def semantic_bool(choice_text: str) -> bool | None:
    """Interpret a radio/checkbox option's own label (e.g. "Yes") as True/False."""
    norm = normalize(choice_text)
    if not norm:
        return None
    if norm in TRUE_WORDS or any(norm.startswith(w) for w in TRUE_WORDS if len(w) > 2):
        return True
    if norm in FALSE_WORDS or any(norm.startswith(w) for w in FALSE_WORDS if len(w) > 2):
        return False
    return None
