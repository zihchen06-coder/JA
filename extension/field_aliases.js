// Maps canonical profile fields to the label phrasings job forms commonly
// use. Ported line-for-line from ja/field_aliases.py -- keep the two in sync.
"use strict";

var FIELD_ALIASES = {
  first_name: ["first name", "given name", "legal first name"],
  last_name: ["last name", "surname", "family name", "legal last name"],
  full_name: ["full name", "your name", "applicant name", "legal name"],
  middle_name: ["middle name", "middle initial"],
  preferred_name: ["preferred name", "nickname", "preferred first name", "goes by"],
  email: ["email", "e mail", "email address"],
  phone: ["phone", "phone number", "mobile", "mobile number", "telephone", "cell phone", "cell number"],
  address_line1: ["address", "street address", "address line 1", "home address"],
  address_line2: ["address line 2", "apt suite", "apartment unit", "unit number"],
  city: ["city", "town"],
  state: ["state", "province", "state province", "region"],
  postal_code: ["zip", "zip code", "postal", "postal code", "postcode"],
  country: ["country"],
  linkedin_url: ["linkedin", "linkedin url", "linkedin profile"],
  github_url: ["github", "github url", "github profile"],
  portfolio_url: ["portfolio", "website", "personal website", "portfolio url"],
  current_company: [
    "current company", "current employer", "employer",
    "most recent employer", "most recent company",
  ],
  current_title: [
    "current title", "current job title", "current position", "job title",
    "most recent title", "most recent job title", "position title",
  ],
  school: [
    "school", "school name", "university", "college", "institution",
    "most recent school",
  ],
  degree: ["degree", "degree earned", "degree type"],
  education_level: [
    "highest level of education", "level of education", "education level",
    "highest degree completed", "highest degree",
  ],
  field_of_study: [
    "field of study", "major", "discipline", "concentration", "area of study",
  ],
  graduation_year: [
    "graduation year", "year of graduation", "expected graduation",
    "graduation date", "grad year",
  ],
  gpa: ["gpa", "grade point average", "cumulative gpa"],
  languages: [
    "languages", "languages you speak", "language proficiency",
    "what languages do you speak", "languages spoken", "fluent languages",
  ],
  references: [
    "references", "professional references", "reference contact",
    "names and contact information",
  ],
  cover_letter_text: [
    "cover letter", "covering letter", "letter of interest",
    "why should we hire you",
  ],
  security_clearance: [
    "security clearance", "clearance level", "active clearance",
  ],
  preferred_location: [
    "preferred location", "preferred work location", "desired location",
    "location preference", "work location",
  ],
  employment_type: [
    "employment type", "position type", "desired employment type",
    "full time or part time", "type of employment",
  ],
  years_experience: ["years of experience", "years experience", "total years of experience"],
  desired_salary: [
    "desired salary", "salary expectation", "salary expectations",
    "compensation expectation", "expected salary", "expected compensation",
  ],
  notice_period: [
    "notice period", "availability", "earliest start date", "start date",
    "when can you start", "date available", "available start date",
  ],
  how_heard: [
    "how did you hear", "how did you hear about", "referral source",
    "how did you find", "source", "referred by",
  ],
  work_authorized: [
    "authorized to work", "legally authorized", "work authorization",
    "eligible to work", "eligible to live and work", "authorized to live and work",
  ],
  citizenship_status: [
    "citizenship employment eligibility", "citizenship status",
    "employment eligibility",
  ],
  referral_name: [
    "who referred you", "referred you to this position", "referral name",
    "employee referral",
  ],
  willing_overtime_varied_schedule: [
    "willing to work overtime", "varied schedules", "overtime and or varied schedules",
    "work overtime",
  ],
  has_reliable_transportation: [
    "adequate transportation", "reliable transportation",
    "access to transportation", "own transportation",
  ],
  bound_by_noncompete: [
    "non competition", "non solicitation", "non compete",
    "restrictive covenant", "bound by a non competition",
  ],
  needs_sponsorship: [
    "require sponsorship", "need sponsorship", "will you require sponsorship",
    "visa sponsorship", "future sponsorship",
  ],
  willing_to_relocate: ["willing to relocate", "relocate", "relocation"],
  gender: ["gender", "sex", "gender identity", "what is your gender"],
  pronouns: ["pronouns", "preferred pronouns", "my pronouns"],
  hispanic_latino: [
    "hispanic or latino", "hispanic latino", "are you hispanic",
    "hispanic or latino ethnicity",
  ],
  race_ethnicity: [
    "race", "ethnicity", "race ethnicity", "racial", "ethnic background",
    "race or ethnicity",
  ],
  veteran_status: [
    "veteran", "veteran status", "protected veteran", "military service",
    "protected veteran status",
  ],
  disability_status: [
    "disability", "disabilities", "disability status",
  ],
  sexual_orientation: ["sexual orientation"],
  transgender_status: ["transgender", "transgender identity"],
  over_18: [
    "at least 18", "18 years of age", "18 years old", "over 18",
    "are you 18", "of legal working age",
  ],
  has_drivers_license: [
    "driver s license", "drivers license", "valid driver s license",
    "valid drivers license", "driving license",
  ],
  willing_to_travel: [
    "willing to travel", "able to travel", "travel requirement",
    "open to travel",
  ],
  consent_background_check: [
    "background check", "background screening", "consent to a background check",
    "submit to a background check",
  ],
  consent_drug_test: [
    "drug test", "drug screen", "drug screening", "substance screening",
  ],
  can_perform_essential_functions: [
    "essential functions", "perform the essential functions",
    "with or without reasonable accommodation",
  ],
  previously_employed_here: [
    "previously employed", "ever worked for", "former employee",
    "worked here before", "previously worked for",
  ],
};

// Question labels containing any of these phrases are demographic/EEO
// questions and are always left for the applicant to answer by hand.
var SENSITIVE_GROUPS = {
  demographic: [
    "Self-identification question: set your answer under " +
      "Self-identification in your profile, or answer it here.",
    [
      "gender", "sex", "race", "ethnicity", "veteran", "disability",
      "disabilities", "sexual orientation", "transgender", "self identif",
      "pronoun", "hispanic", "latino", "military service", "protected",
      "date of birth", "national origin",
    ],
  ],
  criminal: [
    "Criminal-history question: answer this one yourself.",
    ["convicted", "conviction", "felony", "misdemeanor", "criminal", "arrest"],
  ],
  salary_history: [
    "Salary-history question: answer this one yourself (many states bar " +
      "employers from asking).",
    ["salary history", "current salary", "previous salary", "last salary"],
  ],
};

var EEO_KEYWORDS = Object.values(SENSITIVE_GROUPS).flatMap(([, keywords]) => keywords);

var RESUME_KEYWORDS = ["resume", "resume cv", "cv"];
var COVER_LETTER_KEYWORDS = ["cover letter", "covering letter", "letter of interest"];

var BOOLEAN_FIELDS = new Set([
  "work_authorized", "needs_sponsorship", "willing_to_relocate",
  "over_18", "has_drivers_license", "willing_to_travel",
  "consent_background_check", "consent_drug_test",
  "can_perform_essential_functions", "previously_employed_here",
  "willing_overtime_varied_schedule", "has_reliable_transportation",
  "bound_by_noncompete",
]);

var EDUCATION_FIELDS = new Set(["school", "degree", "field_of_study", "graduation_year"]);

var SELF_ID_FIELDS = new Set([
  "gender", "pronouns", "hispanic_latino", "race_ethnicity",
  "veteran_status", "disability_status", "sexual_orientation",
  "transgender_status",
]);

var SELF_ID_DISPLAY_NAMES = {
  gender: "Gender",
  pronouns: "Pronouns",
  hispanic_latino: "Hispanic or Latino?",
  race_ethnicity: "Race / Ethnicity",
  veteran_status: "Veteran Status",
  disability_status: "Disability Status",
  sexual_orientation: "Sexual Orientation",
  transgender_status: "Transgender Status",
};

var SELF_ID_CHOICES = {
  gender: ["Male", "Female", "Non-binary", "Decline to self-identify"],
  hispanic_latino: ["Yes", "No", "Decline to self-identify"],
  race_ethnicity: [
    "American Indian or Alaska Native",
    "Asian",
    "Black or African American",
    "Hispanic or Latino",
    "Native Hawaiian or Other Pacific Islander",
    "White",
    "Two or More Races",
    "Decline to self-identify",
  ],
  veteran_status: [
    "I am not a protected veteran",
    "I identify as one or more of the classifications of a protected veteran",
    "I don't wish to answer",
  ],
  disability_status: [
    "Yes, I have a disability, or have had one in the past",
    "No, I do not have a disability and have not had one in the past",
    "I do not want to answer",
  ],
  sexual_orientation: [
    "Heterosexual", "Gay", "Lesbian", "Bisexual", "Queer",
    "Decline to self-identify",
  ],
  transgender_status: ["Yes", "No", "Decline to self-identify"],
};

var OPTION_CHOICES = {
  education_level: [
    "High School Diploma / GED", "Associate's Degree", "Bachelor's Degree",
    "Master's Degree", "Doctorate (PhD)", "Professional Degree (MD, JD, etc.)", "Other",
  ],
  citizenship_status: [
    "U.S. Citizen", "Permanent Resident / Green Card Holder",
    "Authorized to work in the U.S. without sponsorship",
    "Will require visa sponsorship", "Not authorized to work in the U.S.",
  ],
};

var TRUE_WORDS = new Set(["yes", "y", "true", "i am", "authorized", "agree", "eligible"]);
var FALSE_WORDS = new Set(["no", "n", "false", "i am not", "not authorized", "disagree", "ineligible"]);
