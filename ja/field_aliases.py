"""Maps canonical profile fields to the label phrasings job forms commonly use."""

# canonical field name -> label phrases that should match it (lowercase, normalized)
FIELD_ALIASES: dict[str, list[str]] = {
    "first_name": ["first name", "given name", "legal first name", "fname"],
    "last_name": ["last name", "surname", "family name", "legal last name", "lname"],
    "full_name": ["full name", "your name", "applicant name", "legal name"],
    "middle_name": ["middle name", "middle initial"],
    "preferred_name": ["preferred name", "nickname", "preferred first name", "goes by"],
    "email": ["email", "e mail", "email address"],
    "phone": ["phone", "phone number", "mobile", "mobile number", "telephone", "cell phone", "cell number"],
    "address_line1": ["address", "street address", "address line 1", "home address"],
    "address_line2": ["address line 2", "apt suite", "apartment unit", "unit number"],
    "city": ["city", "town"],
    "state": ["state", "province", "state province", "region"],
    "postal_code": ["zip", "zip code", "postal", "postal code", "postcode"],
    "country": ["country"],
    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
    "github_url": ["github", "github url", "github profile"],
    "portfolio_url": ["portfolio", "website", "personal website", "portfolio url"],
    "current_company": [
        "current company", "current employer", "employer",
        "most recent employer", "most recent company",
    ],
    "current_title": [
        "current title", "current job title", "current position", "job title",
        "most recent title", "most recent job title", "position title",
    ],
    # Filled from the first entry of the profile's `education` list, for the
    # many forms that ask for one flat school/degree rather than a history.
    "school": [
        "school", "school name", "university", "college", "institution",
        "most recent school",
    ],
    "degree": [
        "degree", "degree earned", "highest degree", "degree type",
        "level of education", "highest level of education", "education level",
    ],
    "field_of_study": [
        "field of study", "major", "discipline", "concentration", "area of study",
    ],
    "graduation_year": [
        "graduation year", "year of graduation", "expected graduation",
        "graduation date", "grad year",
    ],
    "gpa": ["gpa", "grade point average", "cumulative gpa"],
    "languages": [
        "languages", "languages you speak", "language proficiency",
        "what languages do you speak", "languages spoken", "fluent languages",
    ],
    "references": [
        "references", "professional references", "reference contact",
        "names and contact information",
    ],
    # For forms that want the cover letter pasted into a box rather than
    # uploaded as a file.
    "cover_letter_text": [
        "cover letter", "covering letter", "letter of interest",
        "why should we hire you",
    ],
    "security_clearance": [
        "security clearance", "clearance level", "active clearance",
    ],
    "preferred_location": [
        "preferred location", "preferred work location", "desired location",
        "location preference", "work location",
    ],
    "employment_type": [
        "employment type", "position type", "desired employment type",
        "full time or part time", "type of employment",
    ],
    "years_experience": ["years of experience", "years experience", "total years of experience"],
    "desired_salary": [
        "desired salary", "salary expectation", "salary expectations",
        "compensation expectation", "expected salary", "expected compensation",
    ],
    "notice_period": [
        "notice period", "availability", "earliest start date", "start date",
        "when can you start", "date available", "available start date",
    ],
    "how_heard": [
        "how did you hear", "how did you hear about", "referral source",
        "how did you find", "source", "referred by",
    ],
    "work_authorized": [
        "authorized to work", "legally authorized", "work authorization",
        "eligible to work",
    ],
    "needs_sponsorship": [
        "require sponsorship", "need sponsorship", "will you require sponsorship",
        "visa sponsorship", "future sponsorship",
    ],
    "willing_to_relocate": ["willing to relocate", "relocate", "relocation"],
    # Voluntary self-identification. These only ever fill from an answer the
    # applicant entered themselves; nothing here is inferred.
    "gender": ["gender", "sex", "gender identity", "what is your gender"],
    "pronouns": ["pronouns", "preferred pronouns", "my pronouns"],
    "hispanic_latino": [
        "hispanic or latino", "hispanic latino", "are you hispanic",
        "hispanic or latino ethnicity",
    ],
    "race_ethnicity": [
        "race", "ethnicity", "race ethnicity", "racial", "ethnic background",
        "race or ethnicity",
    ],
    "veteran_status": [
        "veteran", "veteran status", "protected veteran", "military service",
        "protected veteran status",
    ],
    "disability_status": [
        "disability", "disabilities", "disability status",
    ],
    "sexual_orientation": ["sexual orientation"],
    "transgender_status": ["transgender", "transgender identity"],
    "over_18": [
        "at least 18", "18 years of age", "18 years old", "over 18",
        "are you 18", "of legal working age",
    ],
    "has_drivers_license": [
        "driver s license", "drivers license", "valid driver s license",
        "valid drivers license", "driving license",
    ],
    "willing_to_travel": [
        "willing to travel", "able to travel", "travel requirement",
        "open to travel",
    ],
    "consent_background_check": [
        "background check", "background screening", "consent to a background check",
        "submit to a background check",
    ],
    "consent_drug_test": [
        "drug test", "drug screen", "drug screening", "substance screening",
    ],
    "can_perform_essential_functions": [
        "essential functions", "perform the essential functions",
        "with or without reasonable accommodation",
    ],
    # Company-specific: a blanket "no" is wrong at any employer you HAVE
    # worked for, so leave it unset unless you're sure it applies.
    "previously_employed_here": [
        "previously employed", "ever worked for", "former employee",
        "worked here before", "previously worked for",
    ],
}

# Question labels containing any of these phrases are demographic/EEO questions.
# These are always left for the applicant to answer by hand, regardless of
# whether the profile could supply a guess -- self-identification questions
# should never be auto-filled.
# Also covers age, citizenship, and national origin: all protected
# characteristics where a wrong auto-filled answer is far worse than a blank
# one the applicant fills in deliberately.
SENSITIVE_GROUPS: dict[str, tuple[str, list[str]]] = {
    # Voluntary self-identification. Filled only from an answer you entered
    # yourself under `self_identification`; never inferred from anything else.
    # Left blank there, these stay flagged for you to answer by hand.
    "demographic": (
        "Self-identification question: set your answer under "
        "Self-identification in your profile, or answer it here.",
        [
            "gender", "sex", "race", "ethnicity", "veteran", "disability",
            "disabilities", "sexual orientation", "transgender", "self identif",
            "pronoun", "hispanic", "latino", "military service", "protected",
            "date of birth", "citizen", "national origin",
        ],
    ),
    # What may lawfully be asked varies by state and city, and a wrong answer
    # here is serious.
    "criminal": (
        "Criminal-history question: answer this one yourself.",
        ["convicted", "conviction", "felony", "misdemeanor", "criminal", "arrest"],
    ),
    # Illegal for employers to ask in many states.
    "salary_history": (
        "Salary-history question: answer this one yourself (many states bar "
        "employers from asking).",
        ["salary history", "current salary", "previous salary", "last salary"],
    ),
}

EEO_KEYWORDS: list[str] = [
    kw for _, keywords in SENSITIVE_GROUPS.values() for kw in keywords
]

RESUME_KEYWORDS = ["resume", "resume cv", "cv"]
COVER_LETTER_KEYWORDS = ["cover letter", "covering letter", "letter of interest"]

# Fields whose values are booleans and typically presented as Yes/No radios
# or a single checkbox.
BOOLEAN_FIELDS = {
    "work_authorized", "needs_sponsorship", "willing_to_relocate",
    "over_18", "has_drivers_license", "willing_to_travel",
    "consent_background_check", "consent_drug_test",
    "can_perform_essential_functions", "previously_employed_here",
}

# Canonical names that live on the profile's first education entry rather
# than on the profile itself.
EDUCATION_FIELDS = {"school", "degree", "field_of_study", "graduation_year"}

# Voluntary self-identification answers. A demographic question is filled
# ONLY when the matching field here holds an answer the applicant entered
# themselves -- these values are never derived from a name, a resume, or
# anything else. Left empty, the question is flagged for manual answering,
# which stays the default.
SELF_ID_FIELDS = {
    "gender", "pronouns", "hispanic_latino", "race_ethnicity",
    "veteran_status", "disability_status", "sexual_orientation",
    "transgender_status",
}

# The standard option wordings used by Greenhouse, Lever, Workday and
# JazzHR, offered in the UI so a saved answer matches the real dropdowns.
SELF_ID_CHOICES: dict[str, list[str]] = {
    "gender": ["Male", "Female", "Non-binary", "Decline to self-identify"],
    "hispanic_latino": ["Yes", "No", "Decline to self-identify"],
    "race_ethnicity": [
        "American Indian or Alaska Native",
        "Asian",
        "Black or African American",
        "Hispanic or Latino",
        "Native Hawaiian or Other Pacific Islander",
        "White",
        "Two or More Races",
        "Decline to self-identify",
    ],
    "veteran_status": [
        "I am not a protected veteran",
        "I identify as one or more of the classifications of a protected veteran",
        "I don't wish to answer",
    ],
    "disability_status": [
        "Yes, I have a disability, or have had one in the past",
        "No, I do not have a disability and have not had one in the past",
        "I do not want to answer",
    ],
    "sexual_orientation": [
        "Heterosexual", "Gay", "Lesbian", "Bisexual", "Queer",
        "Decline to self-identify",
    ],
    "transgender_status": ["Yes", "No", "Decline to self-identify"],
}

TRUE_WORDS = {"yes", "y", "true", "i am", "authorized", "agree", "eligible"}
FALSE_WORDS = {"no", "n", "false", "i am not", "not authorized", "disagree", "ineligible"}
