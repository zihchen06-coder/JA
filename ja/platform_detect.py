"""Best-effort detection of which ATS a job posting URL belongs to.

This is used only for reporting and for small per-platform tuning notes --
the field-filling logic itself is shared (see filler.py) because label-based
matching works the same way regardless of which ATS rendered the form.
"""

from __future__ import annotations

from urllib.parse import urlparse


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "myworkdayjobs.com" in host or "workday.com" in host:
        return "workday"
    return "generic"
