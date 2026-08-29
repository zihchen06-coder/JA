"""Renders a FillReport as readable terminal output."""

from __future__ import annotations

from .filler import FillReport

RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"


def _color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def print_report(report: FillReport) -> None:
    print(f"\nDetected platform: {report.platform}\n")

    if report.filled:
        print(_color(f"Filled ({len(report.filled)}):", GREEN))
        for r in report.filled:
            print(f"  ✓ {r.label}  ->  {r.canonical}  [{r.detail}]")
        print()

    if report.needs_review:
        print(_color(f"Needs your review ({len(report.needs_review)}):", YELLOW))
        for r in report.needs_review:
            print(f"  ! {r.label}  -  {r.detail}")
        print()

    unmatched_required = report.unmatched_required
    if unmatched_required:
        print(_color(f"Required fields left blank ({len(unmatched_required)}):", RED))
        for r in unmatched_required:
            reason = r.detail or "no matching profile field"
            print(f"  ✗ {r.label}  -  {reason}")
        print()

    errors = [r for r in report.results if r.action == "error"]
    if errors:
        print(_color(f"Errors while filling ({len(errors)}):", RED))
        for r in errors:
            print(f"  ✗ {r.label}  -  {r.detail}")
        print()

    print(_color(
        "Nothing was submitted. Review every field above in the browser, "
        "answer any flagged questions yourself, then submit manually.",
        DIM,
    ))
