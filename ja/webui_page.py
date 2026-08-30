"""The single HTML page served by the local web UI."""

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Application Autofill</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #07080c;
    --glass: rgba(255,255,255,.045);
    --glass-strong: rgba(255,255,255,.075);
    --stroke: rgba(255,255,255,.10);
    --stroke-soft: rgba(255,255,255,.055);
    --text: #eceef4;
    --muted: #9aa3b5;
    --faint: #6b7488;
    --accent: #7c8cff;
    --accent-2: #4bd6c4;
    --ok: #4ade9c;
    --warn: #fbbf5c;
    --bad: #ff8b7d;
    --radius: 18px;
  }
  * { box-sizing: border-box; }
  html { -webkit-font-smoothing: antialiased; }
  body {
    margin: 0; min-height: 100vh; background: var(--bg); color: var(--text);
    font: 15px/1.55 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    position: relative; overflow-x: hidden;
  }
  /* Ambient colour behind the glass -- without something to refract, a
     blurred translucent panel just looks grey. */
  body::before {
    content: ""; position: fixed; inset: -20% -10% auto -10%; height: 90vh; z-index: -1;
    background:
      radial-gradient(48% 46% at 18% 12%, rgba(124,140,255,.30), transparent 70%),
      radial-gradient(42% 40% at 82% 8%, rgba(75,214,196,.20), transparent 70%),
      radial-gradient(50% 48% at 55% 42%, rgba(180,110,255,.16), transparent 72%);
    filter: blur(20px);
  }
  .wrap { max-width: 900px; margin: 0 auto; padding: 0 22px 90px; }

  header { padding: 44px 0 24px; }
  h1 {
    margin: 0; font-size: 30px; letter-spacing: -.028em; font-weight: 650;
    background: linear-gradient(96deg, #fff 20%, #b9c2ff 62%, #7fe6d8 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .tagline { color: var(--muted); font-size: 14.5px; margin-top: 9px; }
  .tagline strong { color: var(--text); font-weight: 600; }

  .section-label {
    font-size: 11.5px; text-transform: uppercase; letter-spacing: .12em;
    color: var(--faint); font-weight: 660; margin: 34px 0 12px;
  }
  .section-label:first-of-type { margin-top: 8px; }

  .tabs {
    display: flex; flex-wrap: wrap; gap: 4px; padding: 5px; margin-bottom: 18px;
    background: var(--glass); border: 1px solid var(--stroke-soft);
    border-radius: 14px; backdrop-filter: blur(18px) saturate(160%);
    -webkit-backdrop-filter: blur(18px) saturate(160%);
  }
  .tabs button {
    border: 0; background: none; font: inherit; font-size: 13.5px; font-weight: 550;
    color: var(--muted); padding: 8px 15px; border-radius: 10px; cursor: pointer;
    transition: background .18s, color .18s; white-space: nowrap;
  }
  .tabs button:hover { color: var(--text); }
  .tabs button.on {
    background: var(--glass-strong); color: #fff;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 2px 12px rgba(0,0,0,.3);
  }

  .card {
    background: var(--glass); border: 1px solid var(--stroke); border-radius: var(--radius);
    padding: 26px; margin-bottom: 18px;
    backdrop-filter: blur(26px) saturate(170%); -webkit-backdrop-filter: blur(26px) saturate(170%);
    box-shadow: 0 1px 0 rgba(255,255,255,.06) inset, 0 18px 44px rgba(0,0,0,.42);
  }

  label { display: block; font-size: 12.5px; font-weight: 550; color: var(--muted); margin-bottom: 6px; }
  input, select, textarea {
    width: 100%; padding: 10px 13px; border: 1px solid var(--stroke); border-radius: 11px;
    background: rgba(0,0,0,.26); color: var(--text); font: inherit; font-size: 14.5px;
    transition: border-color .18s, box-shadow .18s, background .18s;
  }
  input::placeholder { color: var(--faint); }
  input:focus, select:focus, textarea:focus {
    outline: none; border-color: var(--accent); background: rgba(0,0,0,.36);
    box-shadow: 0 0 0 3.5px rgba(124,140,255,.20);
  }
  select option { background: #14161d; color: var(--text); }
  textarea { min-height: 92px; resize: vertical; line-height: 1.5; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(218px, 1fr)); gap: 16px; }
  .row { margin-bottom: 16px; }
  .row:last-child { margin-bottom: 0; }

  button.act {
    background: linear-gradient(180deg, #8b98ff, #6472f5); color: #fff; border: 0;
    padding: 12px 22px; border-radius: 11px; font: inherit; font-size: 14.5px;
    font-weight: 600; cursor: pointer; box-shadow: 0 6px 18px rgba(100,114,245,.35);
    transition: filter .18s, transform .07s, box-shadow .18s;
  }
  button.act:hover:not(:disabled) { filter: brightness(1.1); box-shadow: 0 8px 24px rgba(100,114,245,.45); }
  button.act:active:not(:disabled) { transform: translateY(1px); }
  button.act:disabled { opacity: .4; cursor: default; box-shadow: none; }
  button.ghost {
    background: var(--glass-strong); border: 1px solid var(--stroke); color: var(--text);
    padding: 11px 18px; border-radius: 11px; font: inherit; font-size: 14px;
    font-weight: 550; cursor: pointer; backdrop-filter: blur(12px);
    transition: background .18s, border-color .18s;
  }
  button.ghost:hover { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.2); }

  h2 {
    font-size: 11.5px; text-transform: uppercase; letter-spacing: .1em;
    color: var(--faint); font-weight: 660; margin: 32px 0 14px;
  }
  h2:first-child { margin-top: 0; }
  .hint { color: var(--muted); font-size: 13.5px; margin: 10px 0 0; line-height: 1.55; }
  .hint strong { color: #cdd4e4; }
  code {
    font-size: 12.5px; background: rgba(255,255,255,.08); padding: 2px 6px;
    border-radius: 5px; color: var(--accent-2);
  }

  .banner { padding: 13px 16px; border-radius: 12px; margin-top: 15px; font-size: 14px; }
  .banner.bad {
    background: rgba(255,139,125,.10); color: var(--bad); white-space: pre-wrap;
    border: 1px solid rgba(255,139,125,.28);
  }

  .group { margin-top: 24px; }
  .group:first-child { margin-top: 0; }
  .ghead { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .ghead h3 { margin: 0; font-size: 14.5px; font-weight: 620; }
  .pill { font-size: 11.5px; font-weight: 660; padding: 3px 10px; border-radius: 20px; }
  .pill.g { background: rgba(74,222,156,.14); color: var(--ok); }
  .pill.y { background: rgba(251,191,92,.14); color: var(--warn); }
  .pill.r { background: rgba(255,139,125,.14); color: var(--bad); }

  ul.res { list-style: none; padding: 0; margin: 0; }
  ul.res li {
    padding: 10px 0 10px 24px; border-bottom: 1px solid var(--stroke-soft);
    font-size: 14px; position: relative;
  }
  ul.res li:last-child { border-bottom: 0; }
  ul.res li::before { position: absolute; left: 2px; font-weight: 700; }
  ul.res.g li::before { content: "✓"; color: var(--ok); }
  ul.res.y li::before { content: "!"; color: var(--warn); }
  ul.res.r li::before { content: "×"; color: var(--bad); }
  ul.res.n li::before { content: "·"; color: var(--faint); }
  .sm { color: var(--muted); font-size: 13px; }
  .val { color: var(--faint); font-size: 13px; }

  details { margin-top: 26px; border-top: 1px solid var(--stroke); padding-top: 18px; }
  summary {
    cursor: pointer; font-size: 13.5px; color: var(--muted); font-weight: 550;
    list-style: none; user-select: none;
  }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: "▸ "; }
  details[open] summary::before { content: "▾ "; }
  summary:hover { color: var(--text); }

  .repeat {
    border: 1px solid var(--stroke-soft); border-radius: 13px; padding: 17px;
    margin-bottom: 12px; background: rgba(0,0,0,.2);
  }
  .del {
    float: right; background: none; border: 0; color: var(--faint); cursor: pointer;
    font-size: 13px; font-weight: 550; padding: 3px 8px; border-radius: 7px;
  }
  .del:hover { color: var(--bad); background: rgba(255,139,125,.12); }
  .steps { margin: 20px 0 0; padding-left: 20px; color: var(--muted); font-size: 13.5px; }
  .steps li { margin-bottom: 5px; }
  .actions { margin-top: 22px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  .spin { color: var(--muted); font-size: 13.5px; }
  .saved { font-size: 13.5px; font-weight: 550; }
  .saved.g { color: var(--ok); } .saved.r { color: var(--bad); }

  .toggle { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
  .toggle input { width: 18px; height: 18px; margin: 2px 0 0; flex: none; accent-color: var(--accent); }
  .toggle div { flex: 1; }
  .toggle .t { font-size: 14px; font-weight: 550; color: var(--text); }
  .toggle .d { font-size: 13px; color: var(--muted); margin-top: 3px; line-height: 1.5; }

  .ptab[hidden] { display: none; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Job Application Autofill</h1>
  <div class="tagline">Fills what it can, flags the rest.
    <strong>It never submits</strong> — you always click that yourself.</div>
</header>

<div class="card">
  <div class="row">
    <label for="url">Job application URL</label>
    <input id="url" placeholder="https://job-boards.greenhouse.io/company/jobs/1234567"
           onkeydown="if(event.key==='Enter')openUrl()">
    <p class="hint">Paste the page with the <em>blank boxes</em> on it — click “Apply” on the
      listing first, then copy that URL. LinkedIn and Indeed listing pages won’t work.</p>
  </div>
  <div class="actions" style="margin-top:16px">
    <button class="act" id="go" onclick="openUrl()">Fill this application</button>
    <span id="status" class="spin"></span>
  </div>
  <div id="err" class="banner bad" hidden></div>
</div>

<div class="card" id="resultCard" hidden>
  <div id="results"></div>
  <div class="actions">
    <button class="ghost" onclick="post('/api/refill')">Re-fill this page</button>
    <button class="ghost" onclick="post('/api/close')">Done — close browser</button>
  </div>
  <ol class="steps">
    <li>Check every filled field in the browser window that opened.</li>
    <li>Answer anything flagged above.</li>
    <li>Click Submit in that window yourself.</li>
    <li>Multi-page form? Click Next there, then “Re-fill this page” here.</li>
  </ol>
</div>

<div class="section-label">Your profile</div>
<div class="tabs" id="ptabs">
  <button data-pt="contact" class="on" onclick="showPTab('contact')">Contact</button>
  <button data-pt="background" onclick="showPTab('background')">Background</button>
  <button data-pt="eligibility" onclick="showPTab('eligibility')">Eligibility</button>
  <button data-pt="selfid" onclick="showPTab('selfid')">Self-ID</button>
  <button data-pt="eduwork" onclick="showPTab('eduwork')">Education &amp; Work</button>
  <button data-pt="docs" onclick="showPTab('docs')">Documents &amp; Answers</button>
  <button data-pt="browser" onclick="showPTab('browser')">Browser &amp; Sign-in</button>
</div>

<div class="card">
  <div id="profileForm">
    <div class="ptab" id="pt-contact"></div>
    <div class="ptab" id="pt-background" hidden></div>
    <div class="ptab" id="pt-eligibility" hidden></div>
    <div class="ptab" id="pt-selfid" hidden></div>
    <div class="ptab" id="pt-eduwork" hidden></div>
    <div class="ptab" id="pt-docs" hidden></div>
    <div class="ptab" id="pt-browser" hidden></div>
  </div>
  <div class="actions">
    <button class="act" onclick="saveProfile()">Save profile</button>
    <span id="saveMsg" class="saved"></span>
  </div>
</div>
</div>

<script>
const CONTACT = [
  ["first_name","First name"],["middle_name","Middle name / initial"],["last_name","Last name"],
  ["preferred_name","Preferred name / nickname"],["email","Email"],["phone","Phone"],
  ["address_line1","Street address"],["address_line2","Apt / unit"],["city","City"],
  ["state","State"],["postal_code","ZIP code"],["country","Country"],
  ["linkedin_url","LinkedIn URL"],["github_url","GitHub URL"],["portfolio_url","Portfolio / website"],
];
const BACKGROUND = [
  ["current_company","Current employer"],["current_title","Current job title"],
  ["years_experience","Years of experience"],["gpa","GPA"],
  ["desired_salary","Desired salary"],["notice_period","Earliest start date"],
  ["preferred_location","Preferred work location"],
  ["employment_type","Employment type (full-time / intern / co-op)"],
  ["security_clearance","Security clearance (if any)"],
  ["languages","Languages you speak"],
  ["how_heard","How you heard about the role"],
  ["referral_name","Referred by (name)"],
];
const SCALARS = CONTACT.concat(BACKGROUND);
const BOOLS = [
  ["work_authorized","Legally authorized to work in the US?"],
  ["needs_sponsorship","Will you need visa sponsorship (now or later)?"],
  ["willing_to_relocate","Willing to relocate?"],
  ["over_18","At least 18 years old?"],
  ["has_drivers_license","Valid driver's license?"],
  ["has_reliable_transportation","Reliable transportation to work?"],
  ["willing_to_travel","Willing to travel?"],
  ["willing_overtime_varied_schedule","Willing to work overtime / varied schedules?"],
  ["consent_background_check","Consent to a background check?"],
  ["consent_drug_test","Consent to a drug screening?"],
  ["can_perform_essential_functions","Can perform the job's essential functions?"],
  ["bound_by_noncompete","Currently bound by a non-compete / non-solicitation agreement?"],
  ["previously_employed_here","Previously employed by this company?"],
];
const CATEGORY_FIELDS = [
  ["education_level","Highest level of education"],
  ["citizenship_status","Citizenship / employment eligibility"],
];
const SELF_ID = [
  ["gender","Gender"],
  ["pronouns","Pronouns"],
  ["hispanic_latino","Hispanic or Latino?"],
  ["race_ethnicity","Race / ethnicity"],
  ["veteran_status","Protected veteran status"],
  ["disability_status","Disability status"],
  ["sexual_orientation","Sexual orientation"],
  ["transgender_status","Do you identify as transgender?"],
];
const LONG = [
  ["references","References (names and contact info)"],
  ["cover_letter_text","Cover letter text (for forms with a paste box)"],
];
const EDU = [["school","School"],["degree","Degree"],["field_of_study","Field of study"],["graduation_year","Graduation year"]];
const EXP = [["company","Company"],["title","Title"],["start_date","Start date"],["end_date","End date"],["description","Description"]];
const PTABS = ["contact","background","eligibility","selfid","eduwork","docs","browser"];

let profile = null, documents = [], selfIdChoices = {}, optionChoices = {}, settings = {};
let timer = null, lastKey = "", blanksOpen = false;

function el(h) { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstChild; }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

function showPTab(name) {
  for (const t of PTABS) {
    document.getElementById("pt-"+t).hidden = (t !== name);
    document.querySelector(`#ptabs button[data-pt="${t}"]`).className = (t === name) ? "on" : "";
  }
  try { localStorage.setItem("ja-ptab", name); } catch (e) {}
}

async function post(path, body) {
  const r = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"},
                              body: JSON.stringify(body || {})});
  return r.json();
}

async function openUrl() {
  const url = document.getElementById("url").value.trim();
  const err = document.getElementById("err");
  err.hidden = true;
  lastKey = "";
  const res = await post("/api/open", {url});
  if (!res.ok) { err.textContent = res.error; err.hidden = false; return; }
  poll();
}

function group(cls, title, items, fmt) {
  if (!items.length) return "";
  return `<div class="group"><div class="ghead"><h3>${title}</h3>
    <span class="pill ${cls}">${items.length}</span></div>
    <ul class="res ${cls}">` + items.map(r => `<li>${fmt(r)}</li>`).join("") + `</ul></div>`;
}

function renderResults(state) {
  const card = document.getElementById("resultCard");
  const box = document.getElementById("results");
  if (!state.report) {
    card.hidden = !state.message;
    box.innerHTML = esc(state.message || "");
    return;
  }
  card.hidden = false;
  const rs = state.report.results;
  let h = `<div class="sm" style="margin-bottom:4px">Platform detected:
           <strong>${esc(state.report.platform)}</strong></div>`;

  h += group("g", "Filled", rs.filter(r => r.action === "filled"),
    r => `${esc(r.label)} <span class="val">→ ${esc(r.detail)}</span>`);
  h += group("y", "Needs your answer", rs.filter(r => r.action === "needs_review"),
    r => `${esc(r.label)}<div class="val">${esc(r.detail)}</div>`);
  h += group("r", "Required, still blank",
    rs.filter(r => r.required && (r.action === "skipped_no_match" || r.action === "skipped_no_data")),
    r => `${esc(r.label)} <span class="val">— type this one in yourself</span>`);
  h += group("r", "Errors", rs.filter(r => r.action === "error"),
    r => `${esc(r.label)} <span class="val">— ${esc(r.detail)}</span>`);

  const optional = rs.filter(r => !r.required &&
    (r.action === "skipped_no_match" || r.action === "skipped_no_data"));
  if (optional.length) {
    h += `<details id="blanks" ${blanksOpen ? "open" : ""}>
      <summary>Other fields left blank (${optional.length}) — what else this form asked for</summary>
      <ul class="res n" style="margin-top:10px">` +
      optional.map(r => `<li>${esc(r.label)} <span class="val">— ${esc(r.detail || "not recognized")}</span></li>`).join("") +
      `</ul>
      <p class="hint">Something here that should fill automatically? Add an open-ended one under
      <strong>Documents &amp; Answers</strong> below. For a standard field the tool didn’t know the
      wording for, add that wording to <code>ja/field_aliases.py</code>.</p>
    </details>`;
  }
  box.innerHTML = h;

  // Remember the disclosure state across re-renders, or it snaps shut on
  // the next poll while the user is reading it.
  const d = document.getElementById("blanks");
  if (d) d.addEventListener("toggle", () => { blanksOpen = d.open; });
}

async function poll() {
  const state = await (await fetch("/api/state")).json();
  document.getElementById("status").textContent =
    state.status === "working" ? (state.message || "Working…") :
    state.status === "starting" ? "Launching browser…" : "";
  document.getElementById("go").disabled = (state.status === "working" || state.status === "starting");
  const err = document.getElementById("err");
  if (state.status === "error") { err.textContent = state.message; err.hidden = false; }

  // Only touch the DOM when something actually changed. Re-rendering on
  // every poll would collapse any open disclosure and fight the scroll.
  const key = state.status + "|" + state.message + "|" + JSON.stringify(state.report);
  if (key !== lastKey) {
    lastKey = key;
    if (state.status === "idle" && !state.report) document.getElementById("resultCard").hidden = true;
    else renderResults(state);
  }

  clearTimeout(timer);
  if (["working","starting","open"].includes(state.status)) timer = setTimeout(poll, 900);
}

function field(name, label, value, list) {
  return `<div class="row"><label for="f-${name}">${esc(label)}</label>
    <input id="f-${name}" value="${esc(value)}" ${list ? `list="${list}"` : ""}></div>`;
}

function boolField(n, l, p) {
  const v = p[n] === true ? "yes" : p[n] === false ? "no" : "";
  return `<div class="row"><label for="f-${n}">${esc(l)}</label>
    <select id="f-${n}">
      <option value="" ${v===""?"selected":""}>— not set —</option>
      <option value="yes" ${v==="yes"?"selected":""}>Yes</option>
      <option value="no" ${v==="no"?"selected":""}>No</option>
    </select></div>`;
}

function choiceField(n, l, p, opts) {
  const cur = p[n] || "";
  if (!opts) return field(n, l, cur);
  return `<div class="row"><label for="f-${n}">${esc(l)}</label>
    <select id="f-${n}">
      <option value="" ${cur===""?"selected":""}>— not set —</option>` +
      opts.map(o => `<option value="${esc(o)}" ${cur===o?"selected":""}>${esc(o)}</option>`).join("") +
      (cur && !opts.includes(cur) ? `<option value="${esc(cur)}" selected>${esc(cur)}</option>` : "") +
    `</select></div>`;
}

function renderProfile() {
  const p = profile;

  document.getElementById("pt-contact").innerHTML =
    `<div class="grid">` + CONTACT.map(([n,l]) => field(n, l, p[n])).join("") + `</div>`;

  document.getElementById("pt-background").innerHTML =
    `<div class="grid">` + BACKGROUND.map(([n,l]) => field(n, l, p[n])).join("") +
    CATEGORY_FIELDS.map(([n,l]) => choiceField(n, l, p, optionChoices[n])).join("") + `</div>
    <p class="hint">“Highest level of education” and “Citizenship / employment eligibility” are
    typical wordings offered as a starting point — pick the closest match to what a given form
    asks, or type your own; the tool fuzzy-matches it against that form’s real options either way.</p>`;

  document.getElementById("pt-eligibility").innerHTML =
    `<div class="grid">` + BOOLS.map(([n,l]) => boolField(n, l, p)).join("") + `</div>
     <p class="hint">Anything left unset is skipped and reported, never guessed.
     Leave <strong>“Previously employed by this company”</strong> unset — it’s company-specific,
     so one saved answer would be wrong at any employer you actually worked for.</p>`;

  document.getElementById("pt-selfid").innerHTML =
    `<p class="hint" style="margin:0 0 14px">These are the voluntary EEO questions almost every
     application asks. Answer them once here and they fill automatically from then on.
     <strong>Anything left unset stays flagged for you to answer by hand</strong> — and nothing here
     is ever guessed from your name or resume. Employers use these for aggregate reporting;
     declining is always a valid answer.</p>
     <div class="grid">` + SELF_ID.map(([n,l]) => choiceField(n, l, p, selfIdChoices[n])).join("") + `</div>
    <p class="hint">Criminal-history and salary-history questions are deliberately not here.
    Those stay flagged every time: what employers may lawfully ask varies by state and city.</p>`;

  document.getElementById("pt-eduwork").innerHTML =
    `<h2>Education</h2><div id="eduList"></div>
     <button class="ghost" onclick="addRow('edu')">Add school</button>
     <h2>Work history</h2><div id="expList"></div>
     <button class="ghost" onclick="addRow('exp')">Add job</button>`;
  (p.education || []).forEach(e => addRow("edu", e));
  (p.experience || []).forEach(e => addRow("exp", e));

  const docsList = `<datalist id="docs">` + documents.map(d => `<option value="${esc(d)}">`).join("") + `</datalist>`;
  document.getElementById("pt-docs").innerHTML =
    `<h2>Documents</h2>${docsList}<div class="grid">` +
    field("resume_path", "Resume file", p.resume_path, "docs") +
    field("cover_letter_path", "Cover letter file (optional)", p.cover_letter_path, "docs") +
    `</div><p class="hint">Put files in the <code>documents</code> folder inside JA, then pick them here.</p>
     <h2>Longer answers</h2>` + LONG.map(([n,l]) =>
      `<div class="row"><label for="f-${n}">${esc(l)}</label>
       <textarea id="f-${n}">${esc(p[n] || "")}</textarea></div>`).join("") +
    `<h2>Saved answers</h2>
     <p class="hint" style="margin-bottom:12px">For questions that keep coming up. The keyword is
     matched against the question text, so “why do you want to work here” catches most phrasings.
     Best for factual repeats — a canned answer to “why this company” reads exactly as canned as it is.</p>
     <div id="ansList"></div>
     <button class="ghost" onclick="addRow('ans')">Add answer</button>`;
  Object.entries(p.custom_answers || {}).forEach(([k,v]) => addRow("ans", {keyword:k, answer:v}));

  document.getElementById("pt-browser").innerHTML =
    `<div class="toggle">
      <input type="checkbox" id="s-use_chrome" ${settings.use_chrome ? "checked" : ""}>
      <div><div class="t">Use my Google Chrome</div>
        <div class="d">Drives the Chrome installed on this Mac instead of the bundled browser.</div></div>
    </div>
    <div class="toggle">
      <input type="checkbox" id="s-stay_signed_in" ${settings.stay_signed_in ? "checked" : ""}>
      <div><div class="t">Stay signed in between applications</div>
        <div class="d">Keeps cookies in a browser profile of the tool’s own, so sites you sign into
        once — Workday accounts especially — stay signed in next time. Sign in inside the window
        that opens; your password is never stored by this tool or sent anywhere.</div></div>
    </div>
    <div class="toggle">
      <input type="checkbox" id="s-auto_create_accounts" ${settings.auto_create_accounts ? "checked" : ""}>
      <div><div class="t">Automatically create accounts on sites that require sign-up</div>
        <div class="d">Some ATS platforms (iCIMS especially) make you create a candidate account
        before showing the real application. When this is on, a strong password is generated the
        first time you hit one of these and filled into Login/Password for you; the same one is
        reused every time you come back to that same company's site, so it never creates a
        duplicate account. Saved logins appear below — you'll want them again to check your
        application status later.</div></div>
    </div>
    <p class="hint">Both take effect on the next application you open.</p>

    <h2>Saved site logins</h2>
    <p class="hint" style="margin-bottom:12px">Stored only on this computer, in a plain file next
    to your profile — never sent anywhere by this tool. Not a hardened password manager: if you
    want stronger protection, keep this folder on an encrypted disk (FileVault, on by default on
    most Macs).</p>
    <div id="credList"><p class="sm">Loading…</p></div>`;

  loadCredentials();

  let saved = "contact";
  try { saved = localStorage.getItem("ja-ptab") || "contact"; } catch (e) {}
  showPTab(PTABS.includes(saved) ? saved : "contact");
}

function addRow(kind, data) {
  data = data || {};
  const spec = kind === "edu" ? EDU : kind === "exp" ? EXP
             : [["keyword","If the question mentions…"],["answer","Answer with"]];
  const listId = kind === "edu" ? "eduList" : kind === "exp" ? "expList" : "ansList";
  const node = el(`<div class="repeat">
    <button class="del" onclick="this.parentNode.remove()">Remove</button>
    <div class="grid">` + spec.map(([n,l]) =>
      `<div class="row"><label>${esc(l)}</label>
       ${n === "description" || n === "answer"
         ? `<textarea data-k="${n}">${esc(data[n] || "")}</textarea>`
         : `<input data-k="${n}" value="${esc(data[n] || "")}">`}</div>`).join("") + `</div></div>`);
  document.getElementById(listId).appendChild(node);
}

function collectRows(listId) {
  return [...document.getElementById(listId).children].map(row => {
    const o = {};
    row.querySelectorAll("[data-k]").forEach(i => o[i.dataset.k] = i.value.trim());
    return o;
  });
}

async function saveProfile() {
  const out = {};
  SCALARS.forEach(([n]) => out[n] = document.getElementById("f-"+n).value.trim());
  LONG.forEach(([n]) => out[n] = document.getElementById("f-"+n).value.trim());
  SELF_ID.forEach(([n]) => out[n] = document.getElementById("f-"+n).value.trim());
  CATEGORY_FIELDS.forEach(([n]) => out[n] = document.getElementById("f-"+n).value.trim());
  BOOLS.forEach(([n]) => { const v = document.getElementById("f-"+n).value; out[n] = v === "" ? null : v; });
  out.resume_path = document.getElementById("f-resume_path").value.trim();
  out.cover_letter_path = document.getElementById("f-cover_letter_path").value.trim();
  out.education = collectRows("eduList").filter(e => e.school);
  out.experience = collectRows("expList").filter(e => e.company);
  out.custom_answers = {};
  collectRows("ansList").forEach(r => { if (r.keyword) out.custom_answers[r.keyword] = r.answer; });

  const msg = document.getElementById("saveMsg");
  msg.textContent = "Saving…"; msg.className = "saved";
  settings = {
    use_chrome: document.getElementById("s-use_chrome").checked,
    stay_signed_in: document.getElementById("s-stay_signed_in").checked,
    auto_create_accounts: document.getElementById("s-auto_create_accounts").checked,
  };
  await post("/api/settings", {settings});
  const res = await post("/api/profile", {profile: out});
  msg.textContent = res.ok ? "Saved." : res.error;
  msg.className = res.ok ? "saved g" : "saved r";
  if (res.ok) setTimeout(() => { msg.textContent = ""; }, 2500);
}

async function loadCredentials() {
  const box = document.getElementById("credList");
  if (!box) return;
  let creds = {};
  try { creds = (await (await fetch("/api/credentials")).json()).credentials || {}; } catch (e) {}
  const hosts = Object.keys(creds);
  if (!hosts.length) {
    box.innerHTML = `<p class="sm">None yet — one is created the first time you hit a site that needs a sign-up.</p>`;
    return;
  }
  box.innerHTML = hosts.map(h => `
    <div class="repeat">
      <button class="del" onclick="forgetCredential('${esc(h)}')">Forget</button>
      <div class="grid">
        <div class="row"><label>Site</label><input value="${esc(h)}" readonly></div>
        <div class="row"><label>Login</label><input value="${esc(creds[h].login || '')}" readonly></div>
        <div class="row"><label>Password</label>
          <input type="password" id="pw-${esc(h)}" value="${esc(creds[h].password || '')}" readonly>
        </div>
      </div>
      <button class="ghost" onclick="togglePw('${esc(h)}')" style="margin-top:8px">Show/hide password</button>
    </div>`).join("");
}

function togglePw(host) {
  const el = document.getElementById("pw-" + host);
  if (el) el.type = el.type === "password" ? "text" : "password";
}

async function forgetCredential(host) {
  await post("/api/credentials/forget", {hostname: host});
  loadCredentials();
}

async function loadProfile() {
  const data = await (await fetch("/api/profile")).json();
  documents = data.documents || [];
  selfIdChoices = data.self_id_choices || {};
  optionChoices = data.option_choices || {};
  try { settings = (await (await fetch("/api/settings")).json()).settings || {}; } catch (e) { settings = {}; }
  if (!data.ok) {
    document.getElementById("pt-contact").innerHTML = `<div class="banner bad">${esc(data.error)}</div>`;
    return;
  }
  profile = data.profile;
  renderProfile();
}

loadProfile();
poll();
</script>
</body>
</html>
"""
