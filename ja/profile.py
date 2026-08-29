"""Loads and validates the applicant profile used to fill job application forms."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Any

import yaml

REQUIRED_FIELDS = ["first_name", "last_name", "email", "phone"]


class ProfileError(Exception):
    pass


@dataclass
class EducationEntry:
    school: str = ""
    degree: str = ""
    field_of_study: str = ""
    graduation_year: str = ""


@dataclass
class WorkExperience:
    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""


@dataclass
class Profile:
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""

    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""

    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""

    current_company: str = ""
    current_title: str = ""
    years_experience: str = ""
    desired_salary: str = ""
    notice_period: str = ""
    how_heard: str = ""

    work_authorized: bool | None = None
    needs_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None

    resume_path: str = ""
    cover_letter_path: str = ""

    education: list[EducationEntry] = field(default_factory=list)
    experience: list[WorkExperience] = field(default_factory=list)

    # Free-form answers keyed by a keyword that should appear in the
    # question's label (case-insensitive substring match). Use this for
    # recurring open-ended questions like "Why do you want to work here?".
    custom_answers: dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def _coerce_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("yes", "true", "y", "1"):
            return True
        if v in ("no", "false", "n", "0"):
            return False
    raise ProfileError(f"Expected a yes/no value, got: {value!r}")


def load_profile(path: str) -> Profile:
    if not os.path.isfile(path):
        raise ProfileError(
            f"Profile file not found: {path}\n"
            f"Copy profile.example.yaml to {path} and fill in your details."
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ProfileError("Profile file must contain a YAML mapping of fields.")

    known_fields = {f.name for f in fields(Profile)}
    unknown = [k for k in raw if k not in known_fields]
    if unknown:
        raise ProfileError(
            f"Unknown field(s) in profile: {', '.join(unknown)}. "
            f"Check spelling against profile.example.yaml."
        )

    for bool_field in ("work_authorized", "needs_sponsorship", "willing_to_relocate"):
        if bool_field in raw:
            raw[bool_field] = _coerce_bool(raw[bool_field])

    education_raw = raw.pop("education", []) or []
    experience_raw = raw.pop("experience", []) or []

    profile = Profile(**raw)
    profile.education = [EducationEntry(**e) for e in education_raw]
    profile.experience = [WorkExperience(**e) for e in experience_raw]

    missing = [f for f in REQUIRED_FIELDS if not getattr(profile, f)]
    if missing:
        raise ProfileError(
            f"Profile is missing required field(s): {', '.join(missing)}"
        )

    if profile.resume_path and not os.path.isfile(profile.resume_path):
        raise ProfileError(f"resume_path does not point to a file: {profile.resume_path}")
    if profile.cover_letter_path and not os.path.isfile(profile.cover_letter_path):
        raise ProfileError(
            f"cover_letter_path does not point to a file: {profile.cover_letter_path}"
        )

    return profile
