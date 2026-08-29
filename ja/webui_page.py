"""The single HTML page served by the local web UI."""

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Application Autofill</title>
<style>
  :root {
    --bg: #f6f7f9; --card: #fff; --text: #1b1d21; --muted: #656b76;
    --line: #dfe2e8; --accent: #2f6df6; --ok: #1a7f4b; --warn: #9a6700; --bad: #b42318;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #16181c; --card: #1e2126; --text: #e9eaec; --muted: #9aa1ac;
      --line: #2f343c; --accent: #6c9bff; --ok: #4ac585; --warn: #e0b341; --bad: #ff7b6b;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  header { padding: 20px 24px; border-bottom: 1px solid var(--line); background: var(--card); }
  h1 { margin: 0; font-size: 18px; }
  .sub { color: var(--muted); font-size: 13px; margin-top: 3px; }
  nav { display: flex; gap: 6px; padding: 12px 24px 0; }
  nav button { background: none; border: 0; padding: 9px 14px; border-radius: 8px 8px 0 0;
               font: inherit; color: var(--muted); cursor: pointer; }
  nav button.on { background: var(--card); color: var(--text); font-weight: 600;
                  border: 1px solid var(--line); border-bottom-color: var(--card); }
  main { padding: 0 24px 60px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
          padding: 20px; margin-top: 14px; max-width: 900px; }
  label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 4px; }
  input, select, textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--line);
    border-radius: 8px; background: var(--bg); color: var(--text); font: inherit; }
  textarea { min-height: 60px; resize: vertical; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
  .row { margin-bottom: 14px; }
  button.act { background: var(--accent); color: #fff; border: 0; padding: 10px 18px;
    border-radius: 8px; font: inherit; font-weight: 600; cursor: pointer; }
  button.act:disabled { opacity: .5; cursor: default; }
  button.ghost { background: none; border: 1px solid var(--line); color: var(--text);
    padding: 10px 16px; border-radius: 8px; font: inherit; cursor: pointer; }
  h2 { font-size: 15px; margin: 26px 0 10px; }
  h2:first-child { margin-top: 0; }
  .hint { color: var(--muted); font-size: 13px; margin: 6px 0 0; }
  .banner { padding: 10px 14px; border-radius: 8px; margin-top: 12px; font-size: 14px; }
  .banner.ok { background: rgba(26,127,75,.12); color: var(--ok); }
  .banner.bad { background: rgba(180,35,24,.12); color: var(--bad); white-space: pre-wrap; }
  ul.res { list-style: none; padding: 0; margin: 6px 0 0; }
  ul.res li { padding: 5px 0; border-bottom: 1px solid var(--line); font-size: 14px; }
  ul.res li:last-child { border: 0; }
  .tag { font-weight: 600; }
  .g { color: var(--ok); } .y { color: var(--warn); } .r { color: var(--bad); }
  .sm { color: var(--muted); font-size: 13px; }
  .repeat { border: 1px solid var(--line); border-radius: 10px; padding: 14px; margin-bottom: 10px; }
  .del { float: right; background: none; border: 0; color: var(--muted); cursor: pointer; font-size: 13px; }
  .steps { margin: 10px 0 0; padding-left: 18px; color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>Job Application Autofill</h1>
  <div class="sub">Fills what it can, flags the rest. Never submits — you always click that yourself.</div>
</header>

<nav>
  <button id="tab-apply" class="on" onclick="showTab('apply')">Apply</button>
  <button id="tab-profile" onclick="showTab('profile')">My Profile</button>
</nav>

<main>
  <section id="pane-apply">
    <div class="card">
      <div class="row">
        <label for="url">Job application URL</label>
        <input id="url" placeholder="https://job-boards.greenhouse.io/company/jobs/1234567">
        <p class="hint">Paste the page with the <em>blank boxes</em> on it — click “Apply” on the
          job listing first, then copy that URL. LinkedIn/Indeed listing pages won’t work.</p>
      </div>
      <button class="act" id="go" onclick="openUrl()">Fill this application</button>
      <span id="status" class="sm" style="margin-left:10px"></span>
      <div id="err" class="banner bad" hidden></div>
    </div>

    <div class="card" id="resultCard" hidden>
      <div id="results"></div>
      <div style="margin-top:18px; display:flex; gap:8px; flex-wrap:wrap">
        <button class="ghost" onclick="post('/api/refill')">Re-fill this page</button>
        <button class="ghost" onclick="post('/api/close')">Done — close browser</button>
      </div>
      <ol class="steps">
        <li>Check every filled field in the browser window that opened.</li>
        <li>Answer anything flagged below.</li>
        <li>Click Submit in that window yourself.</li>
        <li>Multi-page form? Click Next there, then “Re-fill this page” here.</li>
      </ol>
    </div>
  </section>

  <section id="pane-profile" hidden>
    <div class="card">
      <div id="profileForm"></div>
      <div style="margin-top:20px">
        <button class="act" onclick="saveProfile()">Save profile</button>
        <span id="saveMsg" class="sm" style="margin-left:10px"></span>
      </div>
    </div>
  </section>
</main>

<script>
const SCALARS = [
  ["first_name","First name"],["last_name","Last name"],["email","Email"],["phone","Phone"],
  ["address_line1","Street address"],["address_line2","Apt / unit"],["city","City"],
  ["state","State"],["postal_code","ZIP code"],["country","Country"],
  ["linkedin_url","LinkedIn URL"],["github_url","GitHub URL"],["portfolio_url","Portfolio / website"],
  ["current_company","Current employer"],["current_title","Current job title"],
  ["years_experience","Years of experience"],["desired_salary","Desired salary"],
  ["notice_period","Earliest start date"],["how_heard","How you heard about the role"],
];
const BOOLS = [
  ["work_authorized","Legally authorized to work in the US?"],
  ["needs_sponsorship","Will you need visa sponsorship (now or later)?"],
  ["willing_to_relocate","Willing to relocate?"],
];
const EDU = [["school","School"],["degree","Degree"],["field_of_study","Field of study"],["graduation_year","Graduation year"]];
const EXP = [["company","Company"],["title","Title"],["start_date","Start date"],["end_date","End date"],["description","Description"]];

let profile = null, documents = [], timer = null;

function el(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; }
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
  const res = await post("/api/open", {url});
  if (!res.ok) { err.textContent = res.error; err.hidden = false; return; }
  poll();
}

function renderResults(state) {
  const card = document.getElementById("resultCard");
  const box = document.getElementById("results");
  if (!state.report) { card.hidden = !state.message; box.innerHTML = esc(state.message || ""); return; }
  card.hidden = false;
  const rs = state.report.results;
  const groups = [
    ["filled", "Filled", "g", r => `${esc(r.label)} <span class="sm">→ ${esc(r.detail)}</span>`],
    ["needs_review", "Needs your answer", "y", r => `${esc(r.label)} <span class="sm">— ${esc(r.detail)}</span>`],
  ];
  let html = `<div class="sm">Platform detected: ${esc(state.report.platform)}</div>`;
  for (const [action, title, cls, fmt] of groups) {
    const items = rs.filter(r => r.action === action);
    if (!items.length) continue;
    html += `<h2 class="${cls}">${title} (${items.length})</h2><ul class="res">` +
            items.map(r => `<li>${fmt(r)}</li>`).join("") + `</ul>`;
  }
  const blankReq = rs.filter(r => r.required && (r.action === "skipped_no_match" || r.action === "skipped_no_data"));
  if (blankReq.length) {
    html += `<h2 class="r">Required, still blank (${blankReq.length})</h2><ul class="res">` +
      blankReq.map(r => `<li>${esc(r.label)} <span class="sm">— type this one in yourself</span></li>`).join("") + `</ul>`;
  }
  const errs = rs.filter(r => r.action === "error");
  if (errs.length) {
    html += `<h2 class="r">Errors (${errs.length})</h2><ul class="res">` +
      errs.map(r => `<li>${esc(r.label)} <span class="sm">— ${esc(r.detail)}</span></li>`).join("") + `</ul>`;
  }
  box.innerHTML = html;
}

async function poll() {
  const state = await (await fetch("/api/state")).json();
  document.getElementById("status").textContent =
    state.status === "working" ? (state.message || "Working...") :
    state.status === "starting" ? "Launching browser..." : "";
  document.getElementById("go").disabled = (state.status === "working" || state.status === "starting");
  const err = document.getElementById("err");
  if (state.status === "error") { err.textContent = state.message; err.hidden = false; }
  if (state.status === "idle" && !state.report) document.getElementById("resultCard").hidden = true;
  else renderResults(state);

  clearTimeout(timer);
  if (state.status === "working" || state.status === "starting" || state.status === "open")
    timer = setTimeout(poll, 900);
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
  <p class="hint">Left unset, these are simply skipped and you answer them by hand each time.</p>`;

  const opts = `<datalist id="docs">` + documents.map(d => `<option value="${esc(d)}">`).join("") + `</datalist>`;
  h += `<h2>Documents</h2>${opts}<div class="grid">` +
    field("resume_path", "Resume file", p.resume_path, "docs") +
    field("cover_letter_path", "Cover letter file (optional)", p.cover_letter_path, "docs") +
    `</div><p class="hint">Put files in the <code>documents</code> folder inside JA, then pick them here.</p>`;

  h += `<h2>Education</h2><div id="eduList"></div>
        <button class="ghost" onclick="addRow('edu')">Add school</button>`;
  h += `<h2>Work history</h2><div id="expList"></div>
        <button class="ghost" onclick="addRow('exp')">Add job</button>`;
  h += `<h2>Saved answers</h2>
        <p class="hint">For questions that come up again and again. The keyword is matched
        against the question text, so “why do you want to work here” catches most phrasings.</p>
        <div id="ansList"></div>
        <button class="ghost" onclick="addRow('ans')">Add answer</button>`;

  document.getElementById("profileForm").innerHTML = h;
  (p.education || []).forEach(e => addRow("edu", e));
  (p.experience || []).forEach(e => addRow("exp", e));
  Object.entries(p.custom_answers || {}).forEach(([k,v]) => addRow("ans", {keyword:k, answer:v}));
}

function addRow(kind, data) {
  data = data || {};
  const spec = kind === "edu" ? EDU : kind === "exp" ? EXP : [["keyword","If the question mentions..."],["answer","Answer with"]];
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
  BOOLS.forEach(([n]) => { const v = document.getElementById("f-"+n).value; out[n] = v === "" ? null : v; });
  out.resume_path = document.getElementById("f-resume_path").value.trim();
  out.cover_letter_path = document.getElementById("f-cover_letter_path").value.trim();
  out.education = collectRows("eduList").filter(e => e.school);
  out.experience = collectRows("expList").filter(e => e.company);
  out.custom_answers = {};
  collectRows("ansList").forEach(r => { if (r.keyword) out.custom_answers[r.keyword] = r.answer; });

  const msg = document.getElementById("saveMsg");
  msg.textContent = "Saving...";
  const res = await post("/api/profile", {profile: out});
  msg.textContent = res.ok ? "Saved." : res.error;
  msg.className = res.ok ? "sm g" : "sm r";
}

async function loadProfile() {
  const data = await (await fetch("/api/profile")).json();
  documents = data.documents || [];
  if (!data.ok) {
    document.getElementById("profileForm").innerHTML =
      `<div class="banner bad">${esc(data.error)}</div>`;
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
