from __future__ import annotations

import argparse
import os
import sys

from .filler import fill_form
from .profile import ProfileError, load_profile
from .report import print_report


PROMPT = (
    "\n[r] re-fill this page (use after clicking Next on a multi-page form)"
    "\n[n] done with this application"
    "\n[q] quit"
    "\n> "
)


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Run:\n"
            "  pip install -r requirements.txt\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        return None
    return sync_playwright


def _apply_to_url(page, profile, url: str, timeout: int, interactive: bool) -> str:
    """Fill one application. Returns 'next' or 'quit'."""
    print(f"\n{'=' * 70}\nOpening {url}\n{'=' * 70}")
    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
    page.wait_for_timeout(1000)

    print_report(fill_form(page, profile))

    if not interactive:
        return "next"

    while True:
        choice = input(PROMPT).strip().lower()
        if choice == "r":
            page.wait_for_timeout(500)
            print_report(fill_form(page, profile))
        elif choice == "n":
            return "next"
        elif choice == "q":
            return "quit"
        else:
            print("Please enter r, n, or q.")


def _run(urls: list[str], args: argparse.Namespace) -> int:
    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"Profile error: {exc}", file=sys.stderr)
        return 1

    sync_playwright = _load_playwright()
    if sync_playwright is None:
        return 1

    interactive = not args.headless
    browser_path = args.browser_path or os.environ.get("JA_BROWSER_PATH") or None

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=args.headless, executable_path=browser_path)
        except Exception as exc:  # noqa: BLE001
            print(
                f"Could not launch Chromium: {exc}\n\n"
                "Install the matching browser with:\n"
                "  playwright install chromium\n"
                "or point at an existing Chrome/Chromium binary with "
                "--browser-path (or the JA_BROWSER_PATH env var).",
                file=sys.stderr,
            )
            return 1
        page = browser.new_page()
        try:
            for i, url in enumerate(urls, 1):
                if len(urls) > 1:
                    print(f"\n### Application {i} of {len(urls)}")
                try:
                    if _apply_to_url(page, profile, url, args.timeout, interactive) == "quit":
                        print("Stopping. Remaining applications were not opened.")
                        break
                except Exception as exc:  # noqa: BLE001 - one bad URL shouldn't kill a batch
                    print(f"Failed on {url}: {exc}", file=sys.stderr)
                    if len(urls) == 1:
                        return 1
        finally:
            browser.close()

    return 0


def _cmd_fill(args: argparse.Namespace) -> int:
    return _run([args.url], args)


def _cmd_batch(args: argparse.Namespace) -> int:
    try:
        with open(args.urls, encoding="utf-8") as f:
            urls = [
                line.strip() for line in f
                if line.strip() and not line.lstrip().startswith("#")
            ]
    except OSError as exc:
        print(f"Could not read URL list: {exc}", file=sys.stderr)
        return 1

    if not urls:
        print(f"No URLs found in {args.urls}.", file=sys.stderr)
        return 1

    print(f"Loaded {len(urls)} application URL(s) from {args.urls}.")
    return _run(urls, args)


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

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--profile", default="profile.yaml", help="Path to your profile YAML file.")
        p.add_argument("--headless", action="store_true", help="Run without a visible browser window (no manual review possible -- use only to sanity-check field matching).")
        p.add_argument("--timeout", type=int, default=30, help="Page load timeout in seconds (default: 30).")
        p.add_argument("--browser-path", default="", help="Path to a Chrome/Chromium binary, if not using the one installed by `playwright install`.")

    fill_p = sub.add_parser("fill", help="Open a job posting and autofill its application form.")
    fill_p.add_argument("--url", required=True, help="URL of the job application page.")
    add_common(fill_p)
    fill_p.set_defaults(func=_cmd_fill)

    batch_p = sub.add_parser("batch", help="Work through a list of job application URLs, one at a time.")
    batch_p.add_argument("--urls", required=True, help="Text file with one job application URL per line (# comments allowed).")
    add_common(batch_p)
    batch_p.set_defaults(func=_cmd_batch)

    validate_p = sub.add_parser("validate", help="Check that a profile YAML file is well-formed.")
    validate_p.add_argument("--profile", default="profile.yaml", help="Path to your profile YAML file.")
    validate_p.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
