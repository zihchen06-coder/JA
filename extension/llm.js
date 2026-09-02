// Asks Claude to fill the fields the rule-based matcher couldn't.
//
// Runs in the extension's service worker, never in the page: the API key
// lives in extension storage and is only ever read here, so no page script
// (and no content script sharing a tab with one) can reach it.
//
// This is a fallback, not a replacement. field_aliases/matcher handle the
// fields they know for free and instantly; only what's left over is sent
// here. The hard guarantees -- nothing submitted, nothing guessed on
// self-ID / criminal-history / salary-history / consent questions -- are
// enforced in filler.js on the way back in, not left to the prompt.
//
// Raw fetch rather than @anthropic-ai/sdk deliberately: this extension is
// loaded unpacked from a folder with no build step, and the SDK is npm-only,
// so using it would mean a bundler between every edit and a reload.
"use strict";

var ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";
var ANTHROPIC_VERSION = "2023-06-01";
var LLM_MODEL = "claude-opus-5";
var FALLBACK_BETA = "server-side-fallback-2026-07-01";

var LLM_SYSTEM_RULES = `You are helping one job applicant fill in a job
application form in their own browser. You get their saved profile and the
form fields that the extension's rule-based matcher could not fill by
itself. For each field, return the exact text to put in it.

Rules, most important first:

1. Never invent anything about the applicant. Every answer must be
   supported by the profile. If the profile doesn't contain what a field is
   asking for, return an empty value and say why in skip_reason. Never
   guess at employers, job titles, dates, schools, degrees, GPAs,
   certifications, clearances, references, licence numbers, salary figures,
   or anything else that is a matter of record. A blank the applicant fills
   in themselves costs them ten seconds; a plausible invention on a job
   application is a lie told in their name.

2. These questions are the applicant's to answer, never yours:
   - voluntary self-identification / demographics: race, ethnicity, gender,
     pronouns, veteran status, disability, sexual orientation, transgender
     status, date of birth, national origin
   - criminal history of any kind
   - salary history -- what they have been paid before. Desired or expected
     salary going forward is fine to answer from the profile.
   - anything asking them to consent, agree, authorise, certify, or sign:
     SMS consent, background-check authorisation, terms, e-signature boxes

   By default, return an empty value with skip_reason "sensitive" for every
   one of them.

   If, and only if, a "saved_answers" block is given below, the applicant has
   asked you to route those saved answers to questions whose wording the
   matcher didn't recognise. Then your job on one of these is to work out
   *which of their saved answers this question is asking for* and return it,
   phrased as one of the field's own options. You are matching, not
   deciding: if their saved answers do not cover what is being asked, or you
   are unsure which one applies, return empty. Never work out what the
   answer probably is from their name, their resume, or anything else --
   inventing a demographic declaration or a consent on someone's behalf is
   the one thing here that cannot be undone by editing the form afterwards.

3. If a field lists "options", your value must be exactly one of those
   option strings, copied character for character. If none of them is
   right, return empty rather than the closest one.

4. For open-ended questions, write in the applicant's own first person,
   from the substance of their profile -- their actual jobs, projects and
   the answers they have already written under custom_answers. If a custom
   answer covers the question, adapt that rather than writing something
   new; it is their own voice and they chose it. Be concrete and specific
   to what is in the profile. No filler, no superlatives they didn't earn,
   no claims the profile doesn't support.

   When a "job" block is given, use it: name the role and the company where
   it reads naturally, and pick the parts of their background that this
   particular job actually calls for. A generic answer to "why do you want
   this role" is worse than a specific one, and an answer that is specific
   about the wrong job is worse than both -- if the job block is thin or
   missing, stay general rather than guessing at what the company does.

   A cover letter field gets a real letter for this job: a short opening
   naming the role, a middle drawing on the most relevant one or two things
   in their profile, a brief close. Three short paragraphs, not a page. No
   salutation placeholder like "Dear Hiring Manager," unless the profile
   gives a name to use.

5. Match the size of the box. A single-line input wants a phrase or a
   sentence; a textarea wants a paragraph or two. Don't write an essay into
   a one-line field.

6. If two fields ask for the same thing, answer both. If a field is asking
   for something the applicant has clearly already given elsewhere on the
   form, still answer it from the profile.

7. A field of type "radio" is a set of choices like a dropdown: return one
   of its option strings exactly, or empty. Rule 2 still applies -- a radio
   group asking a self-ID, criminal-history or consent question gets an
   empty value however it is phrased.

Return exactly one entry for every field you were given, keyed by its
ja_id.`;

var LLM_OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    answers: {
      type: "array",
      items: {
        type: "object",
        properties: {
          ja_id: { type: "string" },
          value: {
            type: "string",
            description: "Exact text to put in the field. Empty string means leave it blank.",
          },
          skip_reason: {
            type: "string",
            description:
              'Why the field was left blank; "" when a value is given. Use "sensitive" for ' +
              "self-identification, criminal-history, salary-history and consent questions.",
          },
        },
        required: ["ja_id", "value", "skip_reason"],
        additionalProperties: false,
      },
    },
  },
  required: ["answers"],
  additionalProperties: false,
};

// The saved written answers are by far the largest thing in a profile -- a
// filled-in Answers tab runs to several thousand tokens -- and they exist to
// supply the applicant's own voice for open-ended questions. A page of
// contact boxes and dropdowns has no such question on it, so sending them
// there is most of the request's cost buying nothing.
function _needsWrittenVoice(fields) {
  return (fields || []).some((f) => {
    if (f.type === "textarea") return true;
    if (f.type === "select") return false;
    const label = `${f.label || ""} ${f.group_label || ""}`.trim();
    return label.includes("?") || label.length > 40;
  });
}

// By default Claude is never asked a self-identification or criminal-history
// question -- those are answered from the applicant's own saved answer or
// not at all -- so no request could need race, gender, veteran status,
// disability or a conviction to answer, and none of it leaves the machine.
// With routing on they move to a separate block instead, where they are the
// menu to choose from rather than background for something else.
var _SENSITIVE_PROFILE_FIELDS = [
  "gender", "pronouns", "hispanic_latino", "race_ethnicity", "veteran_status",
  "disability_status", "sexual_orientation", "transgender_status",
  "criminal_history", "consent_general", "consent_background_check",
  "consent_drug_test", "sms_consent",
];

// The saved resume and cover letter are stored as base64 data URLs and can
// be megabytes; they are for attaching to upload fields, and have no
// business in a prompt.
function _promptProfile(profile, withAnswers) {
  const copy = { ...profile };
  delete copy.resume_file;
  delete copy.cover_letter_file;
  for (const field of _SENSITIVE_PROFILE_FIELDS) delete copy[field];
  if (!withAnswers) delete copy.custom_answers;
  return copy;
}

// The applicant's own answers to the questions only they may answer, sent
// only when they have turned routing on. Anything they left unset is left
// out: an absent answer is not a question Claude gets to fill in.
function _savedAnswers(profile) {
  const out = {};
  for (const field of _SENSITIVE_PROFILE_FIELDS) {
    const value = profile[field];
    if (value === null || value === undefined || value === "") continue;
    out[field] = value;
  }
  return out;
}

async function _postMessages(apiKey, body, useFallbacks) {
  const headers = {
    "content-type": "application/json",
    "x-api-key": apiKey,
    "anthropic-version": ANTHROPIC_VERSION,
    // Required to call the API from a browser context. The key is read only
    // in this service worker, so it is never exposed to a page.
    "anthropic-dangerous-direct-browser-access": "true",
  };
  if (useFallbacks) headers["anthropic-beta"] = FALLBACK_BETA;

  const payload = useFallbacks ? { ...body, fallbacks: "default" } : body;
  const response = await fetch(ANTHROPIC_URL, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  let parsed = null;
  try {
    parsed = JSON.parse(text);
  } catch (exc) {
    /* fall through to the raw text below */
  }
  return { ok: response.ok, status: response.status, body: parsed, raw: text };
}

function _apiErrorMessage(result) {
  const err = result.body && result.body.error;
  if (err && err.message) return err.message;
  return `HTTP ${result.status}: ${result.raw.slice(0, 300)}`;
}

// fields: [{ja_id, label, group_label, section, type, required, options}]
// Returns {answers: {ja_id: value}, skipped: {ja_id: reason}} or {error}.
async function resolveWithClaude({ apiKey, profile, fields, pageUrl, job, routeSavedAnswers }) {
  if (!apiKey) return { error: "No API key saved." };
  if (!fields || !fields.length) return { answers: {}, skipped: {} };

  const saved = routeSavedAnswers ? _savedAnswers(profile) : {};
  const savedBlock = Object.keys(saved).length
    ? `The applicant's own answers to the questions only they may answer. For` +
      ` one of those questions, return whichever of these it is asking for,` +
      ` phrased as one of that field's options -- or empty if none of them` +
      ` covers it:\n${JSON.stringify(saved, null, 1)}\n\n`
    : "";

  // The job goes in the per-page message rather than the cached system
  // block: it changes every application, and putting it in the prefix would
  // throw away the cache on every single request.
  const jobBlock = job && (job.title || job.description)
    ? `The job being applied for:\n${JSON.stringify(job, null, 1)}\n\n`
    : "";

  const body = {
    model: LLM_MODEL,
    max_tokens: 16000,
    system: [
      {
        type: "text",
        text: `${LLM_SYSTEM_RULES}\n\nThe applicant's profile:\n${JSON.stringify(
          _promptProfile(profile, _needsWrittenVoice(fields)),
          null,
          1
        )}`,
        // Stable across every application, so it caches; the fields below
        // are the only part that changes per page.
        cache_control: { type: "ephemeral" },
      },
    ],
    output_config: {
      // Field mapping and short drafting -- worth real thought, but the
      // applicant is sitting in front of the form waiting for it.
      effort: "medium",
      format: { type: "json_schema", schema: LLM_OUTPUT_SCHEMA },
    },
    messages: [
      {
        role: "user",
        content:
          `Application page: ${pageUrl}\n\n` +
          jobBlock +
          savedBlock +
          `Fields the matcher could not fill:\n${JSON.stringify(fields, null, 1)}`,
      },
    ],
  };

  let result = await _postMessages(apiKey, body, true);
  // The fallbacks parameter and its beta header are the newest thing in this
  // request. If the API rejects the shape, the useful thing is still to get
  // an answer, so try once more without them rather than failing the fill.
  if (!result.ok && result.status === 400) {
    result = await _postMessages(apiKey, body, false);
  }
  if (!result.ok) return { error: _apiErrorMessage(result) };

  const message = result.body;
  if (message.stop_reason === "refusal") {
    return { error: "Claude declined to answer these fields." };
  }

  const textBlock = (message.content || []).find((b) => b.type === "text");
  if (!textBlock) return { error: "No answer came back." };

  let parsed;
  try {
    parsed = JSON.parse(textBlock.text);
  } catch (exc) {
    return { error: `Could not read the answer: ${exc}` };
  }

  const answers = {};
  const skipped = {};
  for (const entry of parsed.answers || []) {
    if (!entry || !entry.ja_id) continue;
    if (entry.value) answers[entry.ja_id] = entry.value;
    else skipped[entry.ja_id] = entry.skip_reason || "No saved answer for this.";
  }
  return { answers, skipped, usage: message.usage || null };
}
