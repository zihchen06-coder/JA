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
    assert matcher.match_field("Highest Level of Education") == "education_level"
    assert matcher.match_field("Major") == "field_of_study"
    assert matcher.match_field("Expected Graduation") == "graduation_year"


def test_matches_most_recent_employment():
    assert matcher.match_field("Most Recent Employer") == "current_company"
    assert matcher.match_field("Most Recent Job Title") == "current_title"


def test_sensitive_questions_are_flagged_not_answered():
    for label in ["Pronouns", "Date of Birth", "National Origin"]:
        assert matcher.is_eeo_label(label), label


def test_citizenship_eligibility_is_not_gated_as_demographic():
    # A required I-9 employment-eligibility category (US Citizen / Permanent
    # Resident / Authorized to work / ...) is not a voluntary EEO
    # disclosure -- it's handled the same as work_authorized, fillable
    # directly from the profile rather than flagged for manual entry.
    assert not matcher.is_eeo_label("What's your citizenship / employment eligibility?")
    assert matcher.match_field("What's your citizenship / employment eligibility?") == "citizenship_status"


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


def test_self_identification_labels_map_to_fields():
    cases = {
        "Gender": "gender",
        "Preferred Pronouns": "pronouns",
        "Are you Hispanic or Latino?": "hispanic_latino",
        "Race / Ethnicity": "race_ethnicity",
        "Veteran Status": "veteran_status",
        "Disability Status": "disability_status",
        "Sexual Orientation": "sexual_orientation",
    }
    for label, expected in cases.items():
        assert matcher.match_field(label) == expected, label


def test_criminal_and_salary_history_are_not_self_id():
    # These must never become fillable, however the profile is configured.
    assert matcher.sensitive_group("Have you been convicted of a felony?") == "criminal"
    assert matcher.sensitive_group("What is your current salary?") == "salary_history"
    assert matcher.sensitive_group("Gender") == "demographic"


def test_best_choice_matches_long_eeo_option_text():
    options = [
        "I am not a protected veteran",
        "I identify as one or more of the classifications of a protected veteran",
        "I don't wish to answer",
    ]
    assert matcher.best_choice("I am not a protected veteran", options) == 0
    assert matcher.best_choice("I don't wish to answer", options) == 2
    assert matcher.best_choice("", options) is None


def test_sensitive_reasons_are_category_specific():
    assert "Self-identification" in matcher.sensitive_reason("Gender")
    assert "Criminal-history" in matcher.sensitive_reason("Have you been convicted of a felony?")
    assert "Salary-history" in matcher.sensitive_reason("What is your current salary?")
    assert matcher.sensitive_reason("First Name") is None


def test_bare_name_and_date_are_never_matched():
    # Regression: "fname"/"lname" style aliases fuzzy-matched a bare "Name"
    # label (a signature field) to first_name, because "name" sits inside
    # "fname" as a literal substring and scores deceptively high under
    # difflib. A signature name/date must stay unmatched, not get
    # overwritten with the applicant's first name.
    assert matcher.match_field("Name") is None
    assert matcher.match_field("Date") is None


def test_select_boolean_options_from_a_real_jazzhr_form():
    # These wordings and option sets are close to a live JazzHR posting.
    assert matcher.match_field("What's your citizenship / employment eligibility?") == "citizenship_status"
    assert matcher.match_field("What's your highest level of education completed?") == "education_level"
    assert matcher.match_field("Who referred you to this position? Enter their first and last name here.") == "referral_name"
    assert matcher.match_field("Are you willing to work overtime and/or varied schedules due to workload?") == "willing_overtime_varied_schedule"
    assert matcher.match_field("Do you have access to adequate transportation for work?") == "has_reliable_transportation"
    assert matcher.match_field(
        "Are you currently bound by a Non-Competition, Non-Solicitation Agreement with your current employer?"
    ) == "bound_by_noncompete"
    assert matcher.match_field(
        "I confirm that I am eligible to live and work in the United States."
    ) == "work_authorized"


def test_years_experience_alias_appears_inside_an_unrelated_yes_no_question():
    # "Do you have 5+ years of experience in the AEC industry?" textually
    # contains "years of experience", so it matches years_experience -- but
    # the control is a company-specific Yes/No question, not a request for
    # a number. filler.py's select handling (not matcher's job) is what
    # must refuse to write free text into an all-Yes/No dropdown; this just
    # documents that the alias match itself is the expected, if misleading,
    # first step.
    assert matcher.match_field("Do you have 5+ years of experience in the AEC industry?") == "years_experience"


def test_race_ethnicity_label_resolves_correctly():
    # Regression context: a <select> nested inside its own <label
    # for="its-own-id"> made labelForById read the label's raw innerText,
    # which for a SELECT includes every option's rendered text glued onto
    # the real label. The race dropdown's own option list ("Hispanic or
    # Latino", "...not Hispanic or Latino" repeated per option) then
    # outscored the field's actual "Race/Ethnicity" label and resolved to
    # hispanic_latino instead. That contamination is inherently
    # unrecoverable once it reaches match_field -- there is no textual way
    # to tell "the label mentions Hispanic" from "one of the options is
    # named Hispanic" -- so the fix lives in the extractor (stripping a
    # label's own nested/pointed-to controls before reading its text, see
    # stripControlsText/stripOptionControls), not here. This just locks in
    # that an uncontaminated label keeps resolving correctly.
    assert matcher.match_field("Race/Ethnicity") == "race_ethnicity"
    assert matcher.match_field("Race / Ethnicity") == "race_ethnicity"


def test_normalize_date_for_native_date_inputs():
    # <input type=date> rejects anything but YYYY-MM-DD outright.
    assert matcher.normalize_date("05/11/2027") == "2027-05-11"
    assert matcher.normalize_date("May 11, 2027") == "2027-05-11"
    assert matcher.normalize_date("2027-05-11") == "2027-05-11"
    # Unparseable text is returned unchanged rather than dropped.
    assert matcher.normalize_date("ASAP") == "ASAP"


def test_best_bool_option_ignores_no_answer_placeholder():
    options = [
        {"value": "", "text": "-- No answer --"},
        {"value": "y", "text": "Yes"},
        {"value": "n", "text": "No"},
    ]
    match = next((o for o in options if matcher.semantic_bool(o["text"]) is True), None)
    assert match["value"] == "y"
    match = next((o for o in options if matcher.semantic_bool(o["text"]) is False), None)
    assert match["value"] == "n"


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
