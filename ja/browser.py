"""Browser launching, shared by the CLI and the web UI.

Supports three setups:
  * the Chromium that `playwright install` downloads (the default)
  * the Google Chrome already installed on the machine (`chrome=True`)
  * a persistent profile directory, so logins survive between runs
    (`user_data_dir`) -- useful for Workday sites that require an account
"""

from __future__ import annotations

import os
from typing import Any


def launch_browser(
    playwright: Any,
    *,
    headless: bool = False,
    browser_path: str = "",
    chrome: bool = False,
    user_data_dir: str = "",
) -> tuple[Any, Any]:
    """Return (closeable, page). Close `closeable` when finished."""
    kwargs: dict[str, Any] = {"headless": headless}
    if browser_path:
        kwargs["executable_path"] = browser_path
    elif chrome:
        # Playwright locates the installed Google Chrome itself.
        kwargs["channel"] = "chrome"

    # Without this, Playwright forces every page into a fixed 1280x720 CSS
    # viewport regardless of the actual window size -- the window opens at
    # full size but the page content is held to that smaller box, which is
    # exactly what makes native controls like <select> dropdowns look
    # oversized against the page and leaves blank space around it.
    # no_viewport lets the page fill the real window instead; --start-
    # maximized makes that window as large as the screen allows.
    page_kwargs: dict[str, Any] = {}
    if not headless:
        kwargs.setdefault("args", []).append("--start-maximized")
        page_kwargs["no_viewport"] = True

    if user_data_dir:
        context = playwright.chromium.launch_persistent_context(
            os.path.expanduser(user_data_dir), **kwargs, **page_kwargs
        )
        page = context.pages[0] if context.pages else context.new_page()
        return context, page

    browser = playwright.chromium.launch(**kwargs)
    return browser, browser.new_page(**page_kwargs)


def launch_error_message(exc: Exception) -> str:
    text = str(exc)
    hint = (
        "Install the bundled browser with:\n"
        "  playwright install chromium\n"
        "or use your installed Google Chrome with --chrome, or point at a\n"
        "specific binary with --browser-path (or the JA_BROWSER_PATH env var)."
    )
    if "ProcessSingleton" in text or "profile appears to be in use" in text:
        hint = (
            "That Chrome profile is already open. Quit Chrome completely\n"
            "(Cmd+Q, not just closing the window) and try again -- Chrome only\n"
            "allows one process per profile directory."
        )
    return f"Could not launch the browser: {exc}\n\n{hint}"
