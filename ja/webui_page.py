"""The single HTML page served by the local web UI."""

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Application Autofill</title>
<style>
  :root {
    --bg: #f4f5f7;
    --card: #ffffff;
    --text: #14161a;
    --muted: #6b7280;
    --faint: #9aa1ad;
    --line: #e4e7ec;
    --line-soft: #eef0f4;
    --accent: #4f46e5;
    --accent-soft: #eef2ff;
    --ok: #067647;
    --ok-soft: #ecfdf3;
    --warn: #b54708;
    --warn-soft: #fffaeb;
    --bad: #b42318;
    --bad-soft: #fef3f2;
    --shadow: 0 1px 2px rgba(16,24,40,.04), 0 4px 16px rgba(16,24,40,.06);
    --radius: 14px;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d0f13;
      --card: #16191f;
      --text: #e8eaed;
      --muted: #98a0ad;
      --faint: #6e7681;
      --line: #262b33;
      --line-soft: #1e222a;
      --accent: #818cf8;
      --accent-soft: #1e1b4b;
      --ok: #5ee9a4;
      --ok-soft: #052e1c;
      --warn: #fdb022;
      --warn-soft: #2e1e05;
      --bad: #fda29b;
      --bad-soft: #2e1210;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 4px 16px rgba(0,0,0,.25);
    }
  }
  * { box-sizing: border-box; }
  html { -webkit-font-smoothing: antialiased; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.55 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 880px; margin: 0 auto; padding: 0 20px 80px; }

  header { padding: 34px 0 22px; }
  h1 { margin: 0; font-size: 26px; letter-spacing: -.022em; font-weight: 640; }
  .tagline { color: var(--muted); font-size: 14px; margin-top: 7px; }
  .tagline strong { color: var(--text); font-weight: 600; }

  .tabs {
    display: inline-flex; gap: 3px; padding: 4px; margin-bottom: 20px;
    background: var(--line-soft); border-radius: 11px;
  }
  .tabs button {
    border: 0; background: none; font: inherit; font-size: 14px; font-weight: 550;
    color: var(--muted); padding: 7px 16px; border-radius: 8px; cursor: pointer;
    transition: background .15s, color .15s;
  }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { background: var(--card); color: var(--text); box-shadow: var(--shadow); }

  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 24px; margin-bottom: 16px; box-shadow: var(--shadow);
  }

  label { display: block; font-size: 13px; font-weight: 550; color: var(--muted); margin-bottom: 6px; }
  input, select, textarea {
    width: 100%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 9px;
    background: var(--bg); color: var(--text); font: inherit; font-size: 14.5px;
    transition: border-color .15s, box-shadow .15s;
  }
  input:focus, select:focus, textarea:focus {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 3.5px color-mix(in srgb, var(--accent) 16%, transparent);
  }
  textarea { min-height: 88px; resize: vertical; line-height: 1.5; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); gap: 15px; }
  .row { margin-bottom: 15px; }
  .row:last-child { margin-bottom: 0; }

  button.act {
    background: var(--accent); color: #fff; border: 0; padding: 11px 20px;
    border-radius: 9px; font: inherit; font-size: 14.5px; font-weight: 600; cursor: pointer;
    transition: filter .15s, transform .06s;
  }
  button.act:hover:not(:disabled) { filter: brightness(1.08); }
  button.act:active:not(:disabled) { transform: translateY(1px); }
  button.act:disabled { opacity: .45; cursor: default; }
  button.ghost {
    background: var(--card); border: 1px solid var(--line); color: var(--text);
    padding: 10px 16px; border-radius: 9px; font: inherit; font-size: 14px;
    font-weight: 550; cursor: pointer; transition: background .15s, border-color .15s;
  }
  button.ghost:hover { background: var(--line-soft); border-color: var(--faint); }

  h2 {
    font-size: 12px; text-transform: uppercase; letter-spacing: .07em;
    color: var(--faint); font-weight: 650; margin: 28px 0 13px;
  }
  h2:first-child { margin-top: 0; }
  .hint { color: var(--muted); font-size: 13.5px; margin: 9px 0 0; line-height: 1.5; }
  code { font-size: 12.5px; background: var(--line-soft); padding: 1.5px 5px; border-radius: 4px; }

  .banner { padding: 12px 15px; border-radius: 10px; margin-top: 14px; font-size: 14px; }
  .banner.bad { background: var(--bad-soft); color: var(--bad); white-space: pre-wrap;
                border: 1px solid color-mix(in srgb, var(--bad) 22%, transparent); }

  .group { margin-top: 22px; }
  .group:first-child { margin-top: 0; }
  .ghead { display: flex; align-items: center; gap: 9px; margin-bottom: 9px; }
  .ghead h3 { margin: 0; font-size: 14.5px; font-weight: 620; }
  .pill {
    font-size: 12px; font-weight: 650; padding: 2px 9px; border-radius: 20px; line-height: 1.6;
  }
  .pill.g { background: var(--ok-soft); color: var(--ok); }
  .pill.y { background: var(--warn-soft); color: var(--warn); }
  .pill.r { background: var(--bad-soft); color: var(--bad); }

  ul.res { list-style: none; padding: 0; margin: 0; }
  ul.res li {
    padding: 9px 0 9px 22px; border-bottom: 1px solid var(--line-soft);
    font-size: 14px; position: relative;
  }
  ul.res li:last-child { border-bottom: 0; }
  ul.res li::before { position: absolute; left: 2px; font-weight: 700; }
  ul.res.g li::before { content: "✓"; color: var(--ok); }
  ul.res.y li::before { content: "!"; color: var(--warn); }
  ul.res.r li::before { content: "×"; color: var(--bad); }
  ul.res.n li::before { content: "·"; color: var(--faint); }
  .sm { color: var(--muted); font-size: 13px; }
  .val { color: var(--muted); font-size: 13px; }

  details { margin-top: 24px; border-top: 1px solid var(--line); padding-top: 16px; }
  summary {
    cursor: pointer; font-size: 13.5px; color: var(--muted); font-weight: 550;
    list-style: none; user-select: none;
  }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: "▸ "; display: inline-block; transition: transform .15s; }
  details[open] summary::before { content: "▾ "; }
  summary:hover { color: var(--text); }

  .repeat {
    border: 1px solid var(--line); border-radius: 11px; padding: 16px;
    margin-bottom: 11px; background: var(--bg);
  }
  .del {
    float: right; background: none; border: 0; color: var(--faint); cursor: pointer;
    font-size: 13px; font-weight: 550; padding: 2px 6px; border-radius: 6px;
  }
  .del:hover { color: var(--bad); background: var(--bad-soft); }
  .steps { margin: 18px 0 0; padding-left: 20px; color: var(--muted); font-size: 13.5px; }
  .steps li { margin-bottom: 4px; }
  .actions { margin-top: 20px; display: flex; gap: 9px; flex-wrap: wrap; }
  .spin { color: var(--muted); font-size: 13.5px; }
  .saved { font-size: 13.5px; font-weight: 550; }
  .saved.g { color: var(--ok); } .saved.r { color: var(--bad); }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Job Application Autofill</h1>
  <div class="tagline">Fills what it can, flags the rest.
    <strong>It never submits</strong> — you always click that yourself.</div>
</header>

<div class="tabs">
  <button id="tab-apply" class="on" onclick="showTab('apply')">Apply</button>
  <button id="tab-profile" onclick="showTab('profile')">My Profile</button>
</div>

<section id="pane-apply">
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
</section>

<section id="pane-profile" hidden>
  <div class="card">
    <div id="profileForm"></div>
    <div class="actions">
      <button class="act" onclick="saveProfile()">Save profile</button>
      <span id="saveMsg" class="saved"></span>
    </div>
  </div>
</section>
</div>

<script>
const SCALARS = [
  ["first_name","First name"],["middle_name","Middle name / initial"],["last_name","Last name"],
  ["preferred_name","Preferred name / nickname"],["email","Email"],["phone","Phone"],
  ["address_line1","Street address"],["address_line2","Apt / unit"],["city","City"],
  ["state","State"],["postal_code","ZIP code"],["country","Country"],
  ["linkedin_url","LinkedIn URL"],["github_url","GitHub URL"],["portfolio_url","Portfolio / website"],
  ["current_company","Current employer"],["current_title","Current job title"],
  ["years_experience","Years of experience"],["gpa","GPA"],
  ["desired_salary","Desired salary"],["notice_period","Earliest start date"],
  ["preferred_location","Preferred work location"],
  ["employment_type","Employment type (full-time / intern / co-op)"],
  ["security_clearance","Security clearance (if any)"],
  ["languages","Languages you speak"],
  ["how_heard","How you heard about the role"],
];
const BOOLS = [
  ["work_authorized","Legally authorized to work in the US?"],
  ["needs_sponsorship","Will you need visa sponsorship (now or later)?"],
  ["willing_to_relocate","Willing to relocate?"],
  ["over_18","At least 18 years old?"],
  ["has_drivers_license","Valid driver's license?"],
  ["willing_to_travel","Willing to travel?"],
  ["consent_background_check","Consent to a background check?"],
  ["consent_drug_test","Consent to a drug screening?"],
  ["can_perform_essential_functions","Can perform the job's essential functions?"],
  ["previously_employed_here","Previously employed by this company?"],
];
const LONG = [
  ["references","References (names and contact info)"],
  ["cover_letter_text","Cover letter text (for forms with a paste box)"],
];
const EDU = [["school","School"],["degree","Degree"],["field_of_study","Field of study"],["graduation_year","Graduation year"]];
const EXP = [["company","Company"],["title","Title"],["start_date","Start date"],["end_date","End date"],["description","Description"]];

let profile = null, documents = [], timer = null, lastKey = "", blanksOpen = false;

function el(h) { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstChild; }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

function showTab(name) {
  for (const t of ["apply","profile"]) {
    document.getElementById("pane-"+t).hidden = (t !== name);
    document.getElementById("tab-"+t).className = (t === name) ? "on" : "";
  }
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
      <strong>Saved answers</strong> on the My Profile tab. For a standard field the tool didn’t
      know the wording for, add that wording to <code>ja/field_aliases.py</code>.</p>
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

function renderProfile() {
  const p = profile;
  let h = `<h2>About you</h2><div class="grid">` +
    SCALARS.map(([n,l]) => field(n, l, p[n])).join("") + `</div>`;

  h += `<h2>Eligibility</h2><div class="grid">` + BOOLS.map(([n,l]) => {
    const v = p[n] === true ? "yes" : p[n] === false ? "no" : "";
    return `<div class="row"><label for="f-${n}">${esc(l)}</label>
      <select id="f-${n}">
        <option value="" ${v===""?"selected":""}>— not set —</option>
        <option value="yes" ${v==="yes"?"selected":""}>Yes</option>
        <option value="no" ${v==="no"?"selected":""}>No</option>
      </select></div>`;
  }).join("") + `</div>
  <p class="hint">Anything left unset is skipped and reported, never guessed.
  Leave <strong>“Previously employed by this company”</strong> unset — it’s company-specific,
  so one saved answer would be wrong at any employer you actually worked for. Questions about
  demographics, criminal history, and salary history are never auto-filled at all.</p>`;

  const docs = `<datalist id="docs">` + documents.map(d => `<option value="${esc(d)}">`).join("") + `</datalist>`;
  h += `<h2>Documents</h2>${docs}<div class="grid">` +
    field("resume_path", "Resume file", p.resume_path, "docs") +
    field("cover_letter_path", "Cover letter file (optional)", p.cover_letter_path, "docs") +
    `</div><p class="hint">Put files in the <code>documents</code> folder inside JA, then pick them here.</p>`;

  h += `<h2>Longer answers</h2>` + LONG.map(([n,l]) =>
    `<div class="row"><label for="f-${n}">${esc(l)}</label>
     <textarea id="f-${n}">${esc(p[n] || "")}</textarea></div>`).join("");

  h += `<h2>Education</h2><div id="eduList"></div>
        <button class="ghost" onclick="addRow('edu')">Add school</button>`;
  h += `<h2>Work history</h2><div id="expList"></div>
        <button class="ghost" onclick="addRow('exp')">Add job</button>`;
  h += `<h2>Saved answers</h2>
        <p class="hint" style="margin-bottom:12px">For questions that keep coming up. The keyword is
        matched against the question text, so “why do you want to work here” catches most phrasings.
        Best for factual repeats — a canned answer to “why this company” reads exactly as canned as it is.</p>
        <div id="ansList"></div>
        <button class="ghost" onclick="addRow('ans')">Add answer</button>`;

  document.getElementById("profileForm").innerHTML = h;
  (p.education || []).forEach(e => addRow("edu", e));
  (p.experience || []).forEach(e => addRow("exp", e));
  Object.entries(p.custom_answers || {}).forEach(([k,v]) => addRow("ans", {keyword:k, answer:v}));
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
  BOOLS.forEach(([n]) => { const v = document.getElementById("f-"+n).value; out[n] = v === "" ? null : v; });
  out.resume_path = document.getElementById("f-resume_path").value.trim();
  out.cover_letter_path = document.getElementById("f-cover_letter_path").value.trim();
  out.education = collectRows("eduList").filter(e => e.school);
  out.experience = collectRows("expList").filter(e => e.company);
  out.custom_answers = {};
  collectRows("ansList").forEach(r => { if (r.keyword) out.custom_answers[r.keyword] = r.answer; });

  const msg = document.getElementById("saveMsg");
  msg.textContent = "Saving…"; msg.className = "saved";
  const res = await post("/api/profile", {profile: out});
  msg.textContent = res.ok ? "Saved." : res.error;
  msg.className = res.ok ? "saved g" : "saved r";
  if (res.ok) setTimeout(() => { msg.textContent = ""; }, 2500);
}

async function loadProfile() {
  const data = await (await fetch("/api/profile")).json();
  documents = data.documents || [];
  if (!data.ok) {
    document.getElementById("profileForm").innerHTML = `<div class="banner bad">${esc(data.error)}</div>`;
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
