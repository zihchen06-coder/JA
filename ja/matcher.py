"""Heuristic matching from a form field's visible label to a profile field."""

from __future__ import annotations

import difflib
import re
from datetime import datetime

from .field_aliases import (
    COVER_LETTER_KEYWORDS,
    EEO_KEYWORDS,
    FALSE_WORDS,
    FIELD_ALIASES,
    RESUME_KEYWORDS,
    SENSITIVE_GROUPS,
    TRUE_WORDS,
)

__all__ = [
    "normalize", "is_eeo_label", "sensitive_group", "sensitive_reason",
    "is_resume_label", "is_cover_letter_label", "match_field", "best_option",
    "best_choice", "semantic_bool", "normalize_date", "format_month_year",
    "experience_field_for",
]

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


def sensitive_group(label: str) -> str | None:
    """Which sensitive category a label belongs to, or None."""
    norm = normalize(label)
    for group, (_, keywords) in SENSITIVE_GROUPS.items():
        if any(kw in norm for kw in keywords):
            return group
    return None


def sensitive_reason(label: str) -> str | None:
    """Why a label must be left for the applicant, or None if it's fillable."""
    group = sensitive_group(label)
    return SENSITIVE_GROUPS[group][0] if group else None


def best_choice(target: str, choices: list[str], min_ratio: float = 0.45) -> int | None:
    """Index of the choice whose text best matches `target`, or None.

    Used for option lists that are whole sentences -- the veteran and
    disability self-identification questions especially.
    """
    norm_target = normalize(target)
    if not norm_target:
        return None

    best_idx, best_score = None, 0.0
    for i, choice in enumerate(choices):
        text = normalize(choice)
        if not text:
            continue
        if text == norm_target:
            return i
        ratio = difflib.SequenceMatcher(None, text, norm_target).ratio()
        if norm_target in text or text in norm_target:
            ratio += 0.3
        if ratio > best_score:
            best_score, best_idx = ratio, i

    return best_idx if best_score >= min_ratio else None


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

    # Fuzzy matching on a short, generic label (e.g. a bare "Name" or "Date"
    # on a signature line) is how an abbreviation-style alias ends up
    # over-matching -- "name" sits inside "fname" as a literal substring, so
    # difflib scores that pair deceptively high. A label needs enough of its
    # own text before a near-miss is trustworthy.
    if len(norm) < 8:
        return None

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


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y")


def normalize_date(value: str, target_format: str = "%Y-%m-%d") -> str:
    """Convert a human-entered date into whatever format the target field
    actually needs. Native <input type=date> hard-requires YYYY-MM-DD and
    rejects anything else outright (the default here); a plain text field
    driven by a JS datepicker widget (jQuery UI's default, and the most
    common convention on US-facing forms) usually expects MM/DD/YYYY
    instead -- callers pass that as `target_format` when the field looks
    datepicker-flavored rather than being a true native date input.
    Returns `value` unchanged if it doesn't match a recognized format, so a
    value already in some other free-text shape still gets attempted as
    typed rather than dropped.
    """
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime(target_format)
        except ValueError:
            continue
    return value


def format_month_year(value: str, target_format: str = "%m/%Y") -> str:
    """Convert a profile-stored 'YYYY-MM' work-history date (the format used
    by profile.yaml's experience entries) into what a repeater-style
    "Job title / Company / From / To" experience block usually expects.
    Returns `value` unchanged if it isn't in that shape, so a value already
    typed some other way still gets attempted as-is.
    """
    text = (value or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})$", text)
    if not m:
        return value
    year, month = m.group(1), m.group(2)
    return f"{month}/{year}" if target_format == "%m/%Y" else value


# A form's "add another job" repeater block (Workday, and the SmartDreamers/
# Envista platform seen in practice) names its fields generically -- "Job
# title", "Company", "Location", "From"/"To" -- with no employer-specific
# qualifier the way FIELD_ALIASES' current_company/current_title require.
# Those bare words are deliberately NOT in FIELD_ALIASES: "Company" alone is
# too likely to false-match some unrelated field elsewhere on the page. The
# field's own machine name inside the repeater is the safe signal instead --
# "experience[0][company]", "experience_company" -- present only on fields
# that really are part of a work-history entry, so matching on it doesn't
# risk pulling in something else.
_EXPERIENCE_NAME_KEYWORDS = (
    ("current_work", "current_checkbox"),
    ("job_title", "title"),
    ("company", "company"),
    ("location", "location"),
    ("work_start", "start_date"),
    ("work_end", "end_date"),
    ("role", "description"),
)


def experience_field_for(name: str, elem_id: str = "") -> str | None:
    """Which WorkExperience attribute (or the special 'current_checkbox'
    marker) a repeater field's name/id identifies it as, or None.
    """
    combined = f"{elem_id or ''} {name or ''}".lower().replace("-", "_")
    if "experience" not in combined:
        return None
    for keyword, field in _EXPERIENCE_NAME_KEYWORDS:
        if keyword in combined:
            return field
    return None


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
