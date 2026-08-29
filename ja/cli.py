from __future__ import annotations

import argparse
import sys

from .filler import fill_form
from .profile import ProfileError, load_profile
from .report import print_report


def _cmd_fill(args: argparse.Namespace) -> int:
    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"Profile error: {exc}", file=sys.stderr)
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Run:\n"
            "  pip install -r requirements.txt\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        print(f"Opening {args.url} ...")
        page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
        page.wait_for_timeout(1000)

        report = fill_form(page, profile)
        print_report(report)

        if args.headless:
            browser.close()
            return 0

        input("\nPress Enter here once you're done reviewing/submitting in the browser (this will close it)... ")
        browser.close()

    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"Profile error: {exc}", file=sys.stderr)
        return 1
    print(f"Profile OK: {profile.full_name} <{profile.email}>")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apply.py",
        description=(
            "Autofills job application forms from your profile, then pauses "
            "for you to review and submit manually. Never submits on its own."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fill_p = sub.add_parser("fill", help="Open a job posting and autofill its application form.")
    fill_p.add_argument("--url", required=True, help="URL of the job application page.")
    fill_p.add_argument("--profile", default="profile.yaml", help="Path to your profile YAML file.")
    fill_p.add_argument("--headless", action="store_true", help="Run without a visible browser window (no manual review possible -- use only to sanity-check field matching).")
    fill_p.add_argument("--timeout", type=int, default=30, help="Page load timeout in seconds (default: 30).")
    fill_p.set_defaults(func=_cmd_fill)

    validate_p = sub.add_parser("validate", help="Check that a profile YAML file is well-formed.")
    validate_p.add_argument("--profile", default="profile.yaml", help="Path to your profile YAML file.")
    validate_p.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
