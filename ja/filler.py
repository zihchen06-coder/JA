"""Core logic: read extracted form fields, decide what to fill from the
profile, and apply it via Playwright -- never touching submit controls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import Any

from . import matcher
from .extractor import extract_fields
from .field_aliases import BOOLEAN_FIELDS, EDUCATION_FIELDS, SELF_ID_DISPLAY_NAMES, SELF_ID_FIELDS
from .platform_detect import detect_platform
from .profile import Profile


@dataclass
class FieldResult:
    label: str
    canonical: str | None
    action: str  # filled | needs_review | skipped_no_data | skipped_no_match | error
    detail: str = ""
    required: bool = False


@dataclass
class FillReport:
    platform: str
    results: list[FieldResult] = field(default_factory=list)

    def add(self, *args, **kwargs) -> None:
        self.results.append(FieldResult(*args, **kwargs))

    @property
    def filled(self) -> list[FieldResult]:
        return [r for r in self.results if r.action == "filled"]

    @property
    def needs_review(self) -> list[FieldResult]:
        return [r for r in self.results if r.action == "needs_review"]

    @property
    def unmatched_required(self) -> list[FieldResult]:
        return [
            r for r in self.results
            if r.required and r.action in ("skipped_no_match", "skipped_no_data")
        ]

    @property
    def unmatched(self) -> list[FieldResult]:
        """Every field left blank, required or not -- what --verbose reports.

        These labels are the raw material for extending FIELD_ALIASES or
        adding a custom_answers entry.
        """
        return [
            r for r in self.results
            if r.action in ("skipped_no_match", "skipped_no_data")
        ]


def _sel(ja_id: str) -> str:
    return f'[data-ja-id="{ja_id}"]'


# Outlines drawn directly on the real page after each fill -- the same
# at-a-glance "see it on the actual form" pattern used by autofill browser
# extensions like Simplify and LazyApply, rather than only a separate report.
_MARK_FILLED = "#22c55e"
_MARK_REVIEW = "#f59e0b"
_MARK_BLANK = "#ef4444"

_MARK_JS = """(el, color) => {
    el.style.outline = `2px solid ${color}`;
    el.style.outlineOffset = '1px';
    el.style.borderRadius = getComputedStyle(el).borderRadius || '3px';
}"""


def _mark(page: Any, ja_id: str, color: str) -> None:
    if not ja_id:
        return
    try:
        page.locator(_sel(ja_id)).evaluate(_MARK_JS, color)
    except Exception:  # noqa: BLE001 - cosmetic only, never fail a fill over it
        pass


def _mark_all(page: Any, options: list[dict], color: str) -> None:
    for opt in options:
        _mark(page, opt.get("ja_id", ""), color)


def _profile_value(profile: Profile, canonical: str) -> Any:
    """Resolve a canonical field name to its value on the profile.

    Education fields live on the first `education` entry rather than on the
    profile itself, since forms usually ask for one flat school/degree.
    """
    if canonical in EDUCATION_FIELDS:
        if not profile.education:
            return None
        return getattr(profile.education[0], canonical, None)
    return getattr(profile, canonical, None)


def _display_label(label: str, canonical: str | None) -> str:
    """Fall back to a friendly self-ID name when the real label is empty."""
    if label.strip():
        return label
    return SELF_ID_DISPLAY_NAMES.get(canonical or "", label)


def _self_id_answer(profile: Profile, label: str, group: str | None) -> str | None:
    """The applicant's own answer to a self-identification question, if set.

    Only the "demographic" group is ever answerable this way, and only from a
    value the applicant entered under self-identification -- nothing is
    inferred. Criminal- and salary-history questions are never fillable.
    """
    if group != "demographic":
        return None
    canonical = matcher.match_field(label)
    if canonical not in SELF_ID_FIELDS:
        return None
    value = getattr(profile, canonical, "")
    return value or None


def _match_custom_answer(label: str, profile: Profile) -> str | None:
    norm_label = matcher.normalize(label)
    if not norm_label:
        return None
    for keyword, answer in profile.custom_answers.items():
        if matcher.normalize(keyword) in norm_label:
            return answer
    return None


def fill_form(page: Any, profile: Profile) -> FillReport:
    report = FillReport(platform=detect_platform(page.url))
    fields_data = extract_fields(page)

    simple_fields = [f for f in fields_data if f["type"] not in ("radio",)]
    radios = [f for f in fields_data if f["type"] == "radio"]

    for f in simple_fields:
        _handle_simple_field(page, profile, report, f)

    radios_sorted = sorted(radios, key=lambda f: f["name"])
    for name, group_iter in groupby(radios_sorted, key=lambda f: f["name"]):
        _handle_radio_group(page, profile, report, list(group_iter))

    return report


def _handle_simple_field(page: Any, profile: Profile, report: FillReport, f: dict) -> None:
    label = f.get("label", "")
    required = f.get("required", False)
    ftype = f["type"]

    if f.get("has_value"):
        report.add(label, None, "already_filled", "Left as-is.", required)
        return

    if ftype == "file":
        _handle_file_field(page, profile, report, f)
        return

    # Long EEO boilerplate (the federal CC-305 disability form especially)
    # can put thousands of characters between a section's real heading and
    # its control, well past reach of the short display label -- wide_text
    # is a superset that still finds it. It's only ever used for detecting
    # and resolving a sensitive question, never for ordinary field matching
    # or for what's shown in the report.
    context = f.get("context", "")
    wide_text = f"{label} {context}".strip() if context else label

    group = matcher.sensitive_group(wide_text)
    if group:
        answer = _self_id_answer(profile, wide_text, group)
        if not answer:
            guess = matcher.match_field(wide_text)
            _mark(page, f["ja_id"], _MARK_REVIEW)
            report.add(_display_label(label, guess), None, "needs_review",
                       matcher.sensitive_reason(wide_text), required)
            return
        canonical = matcher.match_field(wide_text)
        label = _display_label(label, canonical)
        value = answer
    else:
        if ftype == "checkbox":
            _handle_checkbox(page, profile, report, f)
            return

        canonical = matcher.match_field(label)
        if canonical is None:
            custom_answer = _match_custom_answer(label, profile)
            if custom_answer is not None and ftype != "select":
                try:
                    page.locator(_sel(f["ja_id"])).fill(custom_answer)
                    _mark(page, f["ja_id"], _MARK_FILLED)
                    report.add(label, "custom_answers", "filled", custom_answer, required)
                except Exception as exc:  # noqa: BLE001
                    report.add(label, "custom_answers", "error", str(exc), required)
                return
            if required:
                _mark(page, f["ja_id"], _MARK_BLANK)
            report.add(label or f["name"] or f["ja_id"], None, "skipped_no_match", "", required)
            return
        value = _profile_value(profile, canonical)

    if value in (None, ""):
        if required:
            _mark(page, f["ja_id"], _MARK_BLANK)
        report.add(label, canonical, "skipped_no_data", "Profile has no value for this field.", required)
        return

    try:
        loc = page.locator(_sel(f["ja_id"]))
        if f["tag"] == "select":
            options = f.get("options", [])
            # A yes/no field rendered as a dropdown (e.g. "Yes" / "No" /
            # "No answer") needs its Yes/No option located semantically --
            # matching the literal string "True"/"False" against option text
            # never finds anything.
            if canonical in BOOLEAN_FIELDS and isinstance(value, bool):
                match = next((o for o in options if matcher.semantic_bool(o.get("text", "")) is value), None)
                option_value = match.get("value") if match else None
                detail = match.get("text", "") if match else ""
            elif (real_options := options[1:] if len(options) > 1 else options) and all(
                matcher.semantic_bool(o.get("text", "")) is not None for o in real_options
            ):
                # Option 0 is conventionally an unanswered placeholder
                # ("-- No answer --", "Select...") and isn't itself a yes/no
                # choice, so it's excluded rather than breaking this check.
                # A label can textually contain a real alias (e.g. a
                # company-specific "...years of experience..." question
                # matching the generic years_experience field) while the
                # control itself is really a Yes/No question about something
                # else entirely. If every option is Yes/No-shaped but the
                # matched field isn't a boolean one, the match is spurious --
                # refuse it rather than writing free text into a Yes/No box.
                if required:
                    _mark(page, f["ja_id"], _MARK_BLANK)
                report.add(label, canonical, "skipped_no_match",
                           "This looks like a yes/no question with no matching saved answer.", required)
                return
            else:
                option_value = matcher.best_option(str(value), options)
                detail = str(value)
            if option_value is None:
                if required:
                    _mark(page, f["ja_id"], _MARK_BLANK)
                report.add(label, canonical, "skipped_no_match", f"No option matched '{value}'.", required)
                return
            loc.select_option(value=option_value)
            _mark(page, f["ja_id"], _MARK_FILLED)
            report.add(label, canonical, "filled", detail, required)
        else:
            # Native <input type=date> rejects anything but YYYY-MM-DD --
            # a value typed as "05/11/2027" or "May 11, 2027" would
            # silently fail to set.
            fill_value = matcher.normalize_date(str(value)) if ftype == "date" else str(value)
            loc.fill(fill_value)
            _mark(page, f["ja_id"], _MARK_FILLED)
            report.add(label, canonical, "filled", fill_value, required)
    except Exception as exc:  # noqa: BLE001 - report and move on, never crash the run
        report.add(label, canonical, "error", str(exc), required)


def _handle_checkbox(page: Any, profile: Profile, report: FillReport, f: dict) -> None:
    label = f.get("label", "")
    group_label = f.get("group_label", "")
    required = f.get("required", False)
    canonical = matcher.match_field(label)

    # Some forms present a yes/no question as a pair of checkboxes labelled
    # only "Yes" and "No". The question itself is the group label, and the
    # checkbox's own label says which answer it represents.
    option_bool = matcher.semantic_bool(label)
    if canonical not in BOOLEAN_FIELDS and option_bool is not None:
        group_canonical = matcher.match_field(group_label)
        if group_canonical in BOOLEAN_FIELDS:
            target = getattr(profile, group_canonical, None)
            if target is None:
                report.add(group_label, group_canonical, "skipped_no_data", "", required)
                return
            want_checked = (option_bool is target)
            if f.get("checked") is want_checked:
                # The affirmative box carries the answer in the report; an
                # already-correct negative box is nothing worth mentioning.
                if want_checked:
                    report.add(group_label, group_canonical, "already_filled", "Left as-is.", required)
                return
            try:
                loc = page.locator(_sel(f["ja_id"]))
                loc.check() if want_checked else loc.uncheck()
                if want_checked:
                    _mark(page, f["ja_id"], _MARK_FILLED)
                    report.add(group_label, group_canonical, "filled", label, required)
            except Exception as exc:  # noqa: BLE001
                report.add(group_label, group_canonical, "error", str(exc), required)
            return

    if canonical not in BOOLEAN_FIELDS:
        report.add(label or group_label or f["name"], canonical, "skipped_no_match", "", required)
        return

    value = getattr(profile, canonical, None)
    if value is None:
        report.add(label, canonical, "skipped_no_data", "", required)
        return

    if f.get("checked") is value:
        report.add(label, canonical, "already_filled", "Left as-is.", required)
        return

    try:
        loc = page.locator(_sel(f["ja_id"]))
        if value:
            loc.check()
        else:
            loc.uncheck()
        _mark(page, f["ja_id"], _MARK_FILLED)
        report.add(label, canonical, "filled", "checked" if value else "unchecked", required)
    except Exception as exc:  # noqa: BLE001
        report.add(label, canonical, "error", str(exc), required)


def _handle_file_field(page: Any, profile: Profile, report: FillReport, f: dict) -> None:
    label = f.get("label", "")
    required = f.get("required", False)

    if matcher.is_resume_label(label):
        canonical, path = "resume_path", profile.resume_path
    elif matcher.is_cover_letter_label(label):
        canonical, path = "cover_letter_path", profile.cover_letter_path
    else:
        report.add(label or "file upload", None, "skipped_no_match", "", required)
        return

    if not path:
        report.add(label, canonical, "skipped_no_data", "No file path set in profile.", required)
        return

    try:
        page.locator(_sel(f["ja_id"])).set_input_files(path)
        _mark(page, f["ja_id"], _MARK_FILLED)
        report.add(label, canonical, "filled", path, required)
    except Exception as exc:  # noqa: BLE001
        report.add(label, canonical, "error", str(exc), required)


def _handle_radio_group(page: Any, profile: Profile, report: FillReport, options: list[dict]) -> None:
    group_label = next((o.get("group_label") for o in options if o.get("group_label")), "")
    required = any(o.get("required") for o in options)

    if any(o.get("checked") for o in options):
        report.add(group_label, None, "already_filled", "Left as-is.", required)
        return

    # Same rationale as in _handle_simple_field: long EEO boilerplate can
    # separate a section's real heading from its radios by more than
    # group_label's short-range search reaches. wide_text only ever
    # widens detection of a sensitive question -- never used for the
    # ordinary boolean-question matching below, and never shown to the user.
    context = next((o.get("context") for o in options if o.get("context")), "")
    wide_text = f"{group_label} {context}".strip() if context else group_label

    sgroup = matcher.sensitive_group(wide_text)
    if sgroup:
        answer = _self_id_answer(profile, wide_text, sgroup)
        if not answer:
            guess = matcher.match_field(wide_text)
            _mark_all(page, options, _MARK_REVIEW)
            report.add(_display_label(group_label, guess), None, "needs_review",
                       matcher.sensitive_reason(wide_text), required)
            return
        canonical = matcher.match_field(wide_text)
        display = _display_label(group_label, canonical)
        idx = matcher.best_choice(answer, [o.get("label", "") for o in options])
        if idx is None:
            if required:
                _mark_all(page, options, _MARK_BLANK)
            report.add(display, canonical, "skipped_no_match",
                       f"No option matched '{answer}'.", required)
            return
        try:
            page.locator(_sel(options[idx]["ja_id"])).check()
            _mark(page, options[idx]["ja_id"], _MARK_FILLED)
            report.add(display, canonical, "filled", options[idx].get("label", ""), required)
        except Exception as exc:  # noqa: BLE001
            report.add(display, canonical, "error", str(exc), required)
        return

    canonical = matcher.match_field(group_label)
    if canonical not in BOOLEAN_FIELDS:
        if required:
            _mark_all(page, options, _MARK_BLANK)
        report.add(group_label or options[0].get("name", ""), canonical, "skipped_no_match", "", required)
        return

    target = getattr(profile, canonical, None)
    if target is None:
        if required:
            _mark_all(page, options, _MARK_BLANK)
        report.add(group_label, canonical, "skipped_no_data", "", required)
        return

    for opt in options:
        choice_bool = matcher.semantic_bool(opt.get("label", ""))
        if choice_bool is target:
            try:
                page.locator(_sel(opt["ja_id"])).check()
                _mark(page, opt["ja_id"], _MARK_FILLED)
                report.add(group_label, canonical, "filled", opt.get("label", ""), required)
                return
            except Exception as exc:  # noqa: BLE001
                report.add(group_label, canonical, "error", str(exc), required)
                return

    if required:
        _mark_all(page, options, _MARK_BLANK)
    report.add(group_label, canonical, "skipped_no_match", "No matching Yes/No option found.", required)
