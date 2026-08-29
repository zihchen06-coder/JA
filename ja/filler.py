"""Core logic: read extracted form fields, decide what to fill from the
profile, and apply it via Playwright -- never touching submit controls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import Any

from . import matcher
from .extractor import extract_fields
from .field_aliases import BOOLEAN_FIELDS
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


def _sel(ja_id: str) -> str:
    return f'[data-ja-id="{ja_id}"]'


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

    if matcher.is_eeo_label(label):
        report.add(label, None, "needs_review", "Self-identification question: fill in yourself.", required)
        return

    if ftype == "checkbox":
        _handle_checkbox(page, profile, report, f)
        return

    canonical = matcher.match_field(label)
    if canonical is None:
        custom_answer = _match_custom_answer(label, profile)
        if custom_answer is not None and ftype != "select":
            try:
                page.locator(_sel(f["ja_id"])).fill(custom_answer)
                report.add(label, "custom_answers", "filled", custom_answer, required)
            except Exception as exc:  # noqa: BLE001
                report.add(label, "custom_answers", "error", str(exc), required)
            return
        report.add(label or f["name"] or f["ja_id"], None, "skipped_no_match", "", required)
        return

    value = getattr(profile, canonical, None)
    if value in (None, ""):
        report.add(label, canonical, "skipped_no_data", "Profile has no value for this field.", required)
        return

    try:
        loc = page.locator(_sel(f["ja_id"]))
        if f["tag"] == "select":
            option_value = matcher.best_option(str(value), f.get("options", []))
            if option_value is None:
                report.add(label, canonical, "skipped_no_match", f"No option matched '{value}'.", required)
                return
            loc.select_option(value=option_value)
        else:
            loc.fill(str(value))
        report.add(label, canonical, "filled", str(value), required)
    except Exception as exc:  # noqa: BLE001 - report and move on, never crash the run
        report.add(label, canonical, "error", str(exc), required)


def _handle_checkbox(page: Any, profile: Profile, report: FillReport, f: dict) -> None:
    label = f.get("label", "")
    required = f.get("required", False)
    canonical = matcher.match_field(label)

    if canonical not in BOOLEAN_FIELDS:
        report.add(label or f["name"], canonical, "skipped_no_match", "", required)
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
        report.add(label, canonical, "filled", path, required)
    except Exception as exc:  # noqa: BLE001
        report.add(label, canonical, "error", str(exc), required)


def _handle_radio_group(page: Any, profile: Profile, report: FillReport, options: list[dict]) -> None:
    group_label = next((o.get("group_label") for o in options if o.get("group_label")), "")
    required = any(o.get("required") for o in options)

    if any(o.get("checked") for o in options):
        report.add(group_label, None, "already_filled", "Left as-is.", required)
        return

    if matcher.is_eeo_label(group_label):
        report.add(group_label, None, "needs_review", "Self-identification question: fill in yourself.", required)
        return

    canonical = matcher.match_field(group_label)
    if canonical not in BOOLEAN_FIELDS:
        report.add(group_label or options[0].get("name", ""), canonical, "skipped_no_match", "", required)
        return

    target = getattr(profile, canonical, None)
    if target is None:
        report.add(group_label, canonical, "skipped_no_data", "", required)
        return

    for opt in options:
        choice_bool = matcher.semantic_bool(opt.get("label", ""))
        if choice_bool is target:
            try:
                page.locator(_sel(opt["ja_id"])).check()
                report.add(group_label, canonical, "filled", opt.get("label", ""), required)
                return
            except Exception as exc:  # noqa: BLE001
                report.add(group_label, canonical, "error", str(exc), required)
                return

    report.add(group_label, canonical, "skipped_no_match", "No matching Yes/No option found.", required)
