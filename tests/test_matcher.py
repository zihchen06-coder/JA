from ja import matcher


def test_matches_first_name_with_trailing_asterisk():
    assert matcher.match_field("First Name *") == "first_name"


def test_matches_email_with_hyphen():
    assert matcher.match_field("E-mail Address") == "email"


def test_matches_phone_variants():
    assert matcher.match_field("Mobile Number") == "phone"


def test_matches_work_authorization_question():
    assert matcher.match_field("Are you legally authorized to work in the US?") == "work_authorized"


def test_matches_sponsorship_question():
    assert matcher.match_field("Will you now or in the future require visa sponsorship?") == "needs_sponsorship"


def test_no_match_for_unrelated_text():
    assert matcher.match_field("Tell us about a challenging project") is None


def test_eeo_labels_are_flagged():
    for label in [
        "Gender",
        "Race/Ethnicity",
        "Veteran Status",
        "Do you have a disability?",
        "Sexual Orientation",
    ]:
        assert matcher.is_eeo_label(label), label


def test_non_eeo_labels_are_not_flagged():
    assert not matcher.is_eeo_label("First Name")
    assert not matcher.is_eeo_label("Are you authorized to work in the US?")


def test_resume_and_cover_letter_labels():
    assert matcher.is_resume_label("Upload your resume/CV")
    assert matcher.is_cover_letter_label("Cover Letter (optional)")
    assert not matcher.is_resume_label("Cover Letter (optional)")


def test_best_option_matches_closest_text():
    options = [
        {"value": "us", "text": "United States"},
        {"value": "ca", "text": "Canada"},
    ]
    assert matcher.best_option("United States", options) == "us"


def test_semantic_bool():
    assert matcher.semantic_bool("Yes") is True
    assert matcher.semantic_bool("No") is False
    assert matcher.semantic_bool("Not authorized") is False
    assert matcher.semantic_bool("Purple") is None
