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
    "current_company": ["current company", "current employer", "employer"],
    "current_title": ["current title", "current job title", "current position", "job title"],
    "years_experience": ["years of experience", "years experience", "total years of experience"],
    "desired_salary": [
        "desired salary", "salary expectation", "salary expectations",
        "compensation expectation", "expected salary", "expected compensation",
    ],
    "notice_period": ["notice period", "availability", "earliest start date", "start date", "when can you start"],
    "how_heard": ["how did you hear", "referral source", "how did you find", "source"],
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
EEO_KEYWORDS: list[str] = [
    "gender", "sex", "race", "ethnicity", "veteran", "disability",
    "disabilities", "sexual orientation", "transgender", "self identif",
]

RESUME_KEYWORDS = ["resume", "resume cv", "cv"]
COVER_LETTER_KEYWORDS = ["cover letter", "covering letter", "letter of interest"]

# Fields whose values are booleans and typically presented as Yes/No radios
# or a single checkbox.
BOOLEAN_FIELDS = {"work_authorized", "needs_sponsorship", "willing_to_relocate"}

TRUE_WORDS = {"yes", "y", "true", "i am", "authorized", "agree", "eligible"}
FALSE_WORDS = {"no", "n", "false", "i am not", "not authorized", "disagree", "ineligible"}
