import os

import pytest

from ja.profile import ProfileError, load_profile

EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), "..", "profile.example.yaml")


def test_loads_example_profile(tmp_path, monkeypatch):
    # The example references documents/ paths that don't exist in a fresh
    # checkout, so point resume/cover-letter paths at real temp files.
    resume = tmp_path / "resume.pdf"
    resume.write_text("dummy")
    cover = tmp_path / "cover.pdf"
    cover.write_text("dummy")

    content = open(EXAMPLE_PATH, encoding="utf-8").read()
    content = content.replace("documents/resume.pdf", str(resume))
    content = content.replace("documents/cover_letter.pdf", str(cover))

    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(content)

    profile = load_profile(str(profile_path))
    assert profile.first_name == "Jane"
    assert profile.full_name == "Jane Doe"
    assert profile.work_authorized is True
    assert profile.needs_sponsorship is False
    assert len(profile.education) == 1
    assert len(profile.experience) == 1


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(ProfileError, match="not found"):
        load_profile(str(tmp_path / "nope.yaml"))


def test_missing_required_field_raises(tmp_path):
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("first_name: Jane\n")
    with pytest.raises(ProfileError, match="missing required field"):
        load_profile(str(profile_path))


def test_unknown_field_raises(tmp_path):
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "first_name: Jane\nlast_name: Doe\nemail: j@example.com\nphone: '123'\nnickname: Janey\n"
    )
    with pytest.raises(ProfileError, match="Unknown field"):
        load_profile(str(profile_path))
