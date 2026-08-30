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


def test_matches_education_fields():
    assert matcher.match_field("School Name *") == "school"
    assert matcher.match_field("Highest Level of Education") == "degree"
    assert matcher.match_field("Major") == "field_of_study"
    assert matcher.match_field("Expected Graduation") == "graduation_year"


def test_matches_most_recent_employment():
    assert matcher.match_field("Most Recent Employer") == "current_company"
    assert matcher.match_field("Most Recent Job Title") == "current_title"


def test_sensitive_questions_are_flagged_not_answered():
    for label in ["Pronouns", "Are you a US citizen?", "Date of Birth", "National Origin"]:
        assert matcher.is_eeo_label(label), label


def test_matches_common_screening_questions():
    cases = {
        "Are you at least 18 years of age?": "over_18",
        "Do you have a valid driver's license?": "has_drivers_license",
        "Are you willing to travel?": "willing_to_travel",
        "Are you willing to submit to a background check?": "consent_background_check",
        "Are you willing to take a drug screen?": "consent_drug_test",
        "Can you perform the essential functions of this job?": "can_perform_essential_functions",
        "Have you ever worked for this company before?": "previously_employed_here",
        "Cumulative GPA": "gpa",
        "Preferred Name": "preferred_name",
        "Middle Initial": "middle_name",
        "Preferred Work Location": "preferred_location",
        "Employment Type": "employment_type",
        "Security Clearance": "security_clearance",
    }
    for label, expected in cases.items():
        assert matcher.match_field(label) == expected, label


def test_matches_fields_seen_on_real_forms():
    # Wordings taken from a live JazzHR application form.
    cases = {
        "Postal": "postal_code",
        "Website, blog or portfolio:": "portfolio_url",
        "What languages do you speak fluently?": "languages",
        "References: Please enter names and contact information:": "references",
        "Cover Letter": "cover_letter_text",
        "What is your desired salary?": "desired_salary",
        "Earliest start date?": "notice_period",
    }
    for label, expected in cases.items():
        assert matcher.match_field(label) == expected, label


def test_sensitive_reasons_are_category_specific():
    assert "Self-identification" in matcher.sensitive_reason("Gender")
    assert "Criminal-history" in matcher.sensitive_reason("Have you been convicted of a felony?")
    assert "Salary-history" in matcher.sensitive_reason("What is your current salary?")
    assert matcher.sensitive_reason("First Name") is None


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
