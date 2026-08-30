"""Browser preferences the UI can change, stored next to the profile.

Kept out of profile.yaml so the profile stays purely "who you are", and
gitignored either way.
"""

from __future__ import annotations

import json
import os
from typing import Any

FILENAME = "settings.json"

DEFAULTS: dict[str, Any] = {
    # Use the Google Chrome installed on this machine rather than the
    # Chromium `playwright install` downloads.
    "use_chrome": False,
    # Keep cookies and logins between runs in a profile folder of the tool's
    # own, so sites you signed into once stay signed in.
    "stay_signed_in": False,
    # Some ATS platforms (iCIMS especially) require creating a candidate
    # account -- a Login and Password -- before showing the real
    # application form. When on, a strong password is generated and saved
    # locally per site (see ja/credentials.py) instead of leaving those
    # fields for you to fill by hand every time.
    "auto_create_accounts": False,
}

# Deliberately not the real Chrome profile: Chrome permits one process per
# profile directory, so pointing at the everyday one would mean quitting
# Chrome before every run.
PROFILE_DIR = "~/.ja-browser-profile"


def path_for(root: str) -> str:
    return os.path.join(root, FILENAME)


def load_settings(root: str) -> dict[str, Any]:
    settings = dict(DEFAULTS)
    try:
        with open(path_for(root), "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            settings.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, json.JSONDecodeError):
        pass  # a missing or corrupt file just means defaults
    return settings


def save_settings(root: str, data: dict[str, Any]) -> dict[str, Any]:
    settings = {k: bool(data.get(k, DEFAULTS[k])) for k in DEFAULTS}
    tmp = path_for(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, path_for(root))
    return settings


def launch_opts(root: str, browser_path: str = "") -> dict[str, Any]:
    """Translate stored settings into ja.browser.launch_browser arguments."""
    settings = load_settings(root)
    return {
        "browser_path": browser_path,
        "chrome": settings["use_chrome"],
        "user_data_dir": PROFILE_DIR if settings["stay_signed_in"] else "",
    }
