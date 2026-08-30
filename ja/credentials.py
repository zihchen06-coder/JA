"""Per-site account credentials for job portals that require signing up
before you can apply (iCIMS is the most common offender).

Stored locally only, gitignored, in plain JSON -- this is a convenience
store for one person's own machine, not a hardened password manager.
Never transmitted anywhere by this tool.
"""

from __future__ import annotations

import json
import os
import secrets
import string
from urllib.parse import urlparse

FILENAME = "credentials.json"

_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def generate_password(length: int = 16) -> str:
    """A random password meeting the complexity rules nearly every signup
    form asks for: upper, lower, digit, and a special character.
    """
    while True:
        pwd = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^&*" for c in pwd)
        ):
            return pwd


def _path(root: str) -> str:
    return os.path.join(root, FILENAME)


def load_credentials(root: str) -> dict[str, dict[str, str]]:
    try:
        with open(_path(root), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_credentials(root: str, data: dict[str, dict[str, str]]) -> None:
    tmp = _path(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _path(root))


def hostname_for(url: str) -> str:
    return urlparse(url).netloc


def get_or_create(root: str, hostname: str, default_login: str) -> tuple[str, str]:
    """Return (login, password) for this hostname, creating and saving a
    new strong password the first time. Keyed by the FULL hostname, not
    just the base domain -- many companies share the same underlying ATS
    (e.g. many different employers each run their own careers site on
    *.icims.com), and each is a separate candidate database even though
    the platform is shared, so a login at one does not carry over to
    another on the same base domain.
    """
    creds = load_credentials(root)
    if hostname in creds and creds[hostname].get("login") and creds[hostname].get("password"):
        return creds[hostname]["login"], creds[hostname]["password"]

    password = generate_password()
    creds[hostname] = {"login": default_login, "password": password}
    save_credentials(root, creds)
    return default_login, password
