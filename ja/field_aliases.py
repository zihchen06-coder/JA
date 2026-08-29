"""Maps canonical profile fields to the label phrasings job forms commonly use."""

# canonical field name -> label phrases that should match it (lowercase, normalized)
FIELD_ALIASES: dict[str, list[str]] = {
    "first_name": ["first name", "given name", "legal first name", "fname"],
    "last_name": ["last name", "surname", "family name", "legal last name", "lname"],
    "full_name": ["full name", "your name", "applicant name"],
    "email": ["email", "e mail", "email address"],
    "phone": ["phone", "phone number", "mobile", "mobile number", "telephone", "cell phone", "cell number"],
    "address_line1": ["address", "street address", "address line 1", "home address"],
    "address_line2": ["address line 2", "apt suite", "apartment unit", "unit number"],
    "city": ["city", "town"],
    "state": ["state", "province", "state province", "region"],
    "postal_code": ["zip", "zip code", "postal code", "postcode"],
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
}

# Question labels containing any of these phrases are demographic/EEO questions.
# These are always left for the applicant to answer by hand, regardless of
# whether the profile could supply a guess -- self-identification questions
# should never be auto-filled.
# Also covers age, citizenship, and national origin: all protected
# characteristics where a wrong auto-filled answer is far worse than a blank
# one the applicant fills in deliberately.
EEO_KEYWORDS: list[str] = [
    "gender", "sex", "race", "ethnicity", "veteran", "disability",
    "disabilities", "sexual orientation", "transgender", "self identif",
    "pronoun", "hispanic", "latino", "military service", "protected",
    "date of birth", "citizen", "national origin",
]

RESUME_KEYWORDS = ["resume", "resume cv", "cv"]
COVER_LETTER_KEYWORDS = ["cover letter", "covering letter", "letter of interest"]

# Fields whose values are booleans and typically presented as Yes/No radios
# or a single checkbox.
BOOLEAN_FIELDS = {"work_authorized", "needs_sponsorship", "willing_to_relocate"}

# Canonical names that live on the profile's first education entry rather
# than on the profile itself.
EDUCATION_FIELDS = {"school", "degree", "field_of_study", "graduation_year"}

TRUE_WORDS = {"yes", "y", "true", "i am", "authorized", "agree", "eligible"}
FALSE_WORDS = {"no", "n", "false", "i am not", "not authorized", "disagree", "ineligible"}
