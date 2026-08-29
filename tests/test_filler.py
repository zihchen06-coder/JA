"""Tests for fill decisions, using a fake page so no browser is needed."""

from unittest.mock import patch

from ja.filler import fill_form
from ja.profile import Profile


class FakeLocator:
    def __init__(self, page, sel):
        self.page = page
        self.sel = sel

    def fill(self, value):
        self.page.actions.append(("fill", self.sel, value))

    def select_option(self, value=None):
        self.page.actions.append(("select", self.sel, value))

    def check(self):
        self.page.actions.append(("check", self.sel))

    def uncheck(self):
        self.page.actions.append(("uncheck", self.sel))

    def set_input_files(self, path):
        self.page.actions.append(("upload", self.sel, path))


class FakePage:
    url = "https://boards.greenhouse.io/acme/jobs/1"

    def __init__(self):
        self.actions = []

    def locator(self, sel):
        return FakeLocator(self, sel)


def run(fields, profile):
    page = FakePage()
    with patch("ja.filler.extract_fields", return_value=fields):
        report = fill_form(page, profile)
    return page.actions, report


BASE = Profile(first_name="Jane", last_name="Doe", email="j@example.com", phone="555")


def field(**kw):
    base = {"ja_id": "ja-0", "tag": "input", "type": "text", "name": "f", "required": False, "label": ""}
    base.update(kw)
    return base


def test_fills_empty_matched_field():
    actions, report = run([field(label="First Name", has_value=False)], BASE)
    assert actions == [("fill", '[data-ja-id="ja-0"]', "Jane")]
    assert report.filled[0].canonical == "first_name"


def test_does_not_clobber_field_that_already_has_a_value():
    actions, report = run([field(label="First Name", has_value=True)], BASE)
    assert actions == []
    assert report.results[0].action == "already_filled"


def test_eeo_question_is_never_filled():
    profile = Profile(**{**BASE.__dict__, "custom_answers": {"gender": "Female"}})
    actions, report = run([field(label="Gender", has_value=False)], profile)
    assert actions == []
    assert report.results[0].action == "needs_review"


def test_radio_group_left_alone_when_an_option_is_already_checked():
    fields = [
        field(ja_id="ja-0", type="radio", name="auth", label="Yes",
              group_label="Are you legally authorized to work?", checked=True),
        field(ja_id="ja-1", type="radio", name="auth", label="No",
              group_label="Are you legally authorized to work?", checked=False),
    ]
    profile = Profile(**{**BASE.__dict__, "work_authorized": False})
    actions, report = run(fields, profile)
    assert actions == []
    assert report.results[0].action == "already_filled"


def test_radio_group_selects_matching_option_when_untouched():
    fields = [
        field(ja_id="ja-0", type="radio", name="auth", label="Yes",
              group_label="Are you legally authorized to work?", checked=False),
        field(ja_id="ja-1", type="radio", name="auth", label="No",
              group_label="Are you legally authorized to work?", checked=False),
    ]
    profile = Profile(**{**BASE.__dict__, "work_authorized": True})
    actions, _ = run(fields, profile)
    assert actions == [("check", '[data-ja-id="ja-0"]')]


def test_resume_upload_skipped_when_file_already_attached():
    profile = Profile(**{**BASE.__dict__, "resume_path": "/tmp/r.pdf"})
    actions, report = run([field(type="file", label="Resume/CV", has_value=True)], profile)
    assert actions == []
    assert report.results[0].action == "already_filled"


def test_unmatched_required_field_is_reported():
    actions, report = run(
        [field(label="Describe a challenging project", required=True, has_value=False)], BASE
    )
    assert actions == []
    assert len(report.unmatched_required) == 1
