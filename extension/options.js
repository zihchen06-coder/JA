"use strict";

const BOOL_LABELS = {
  work_authorized: "Authorized to work in this country",
  needs_sponsorship: "Will require visa sponsorship",
  willing_to_relocate: "Willing to relocate",
  over_18: "At least 18 years old",
  has_drivers_license: "Has a valid driver's license",
  willing_to_travel: "Willing to travel for this role",
  consent_background_check: "Consents to a background check",
  consent_drug_test: "Consents to a drug test",
  can_perform_essential_functions: "Can perform essential functions (with/without accommodation)",
  previously_employed_here: "Previously employed at this specific company",
  willing_overtime_varied_schedule: "Willing to work overtime / varied schedules",
  has_reliable_transportation: "Has reliable transportation",
  bound_by_noncompete: "Currently bound by a non-compete",
};

let state = { profile: {}, settings: {}, credentials: {} };

// Keywords, not exact question text -- matched as a substring against a
// question's normalized label (see ja/filler.py's _match_custom_answer),
// so each one is written broadly enough to catch the common ways a
// real form phrases the same underlying question, without being so
// generic ("team", "work") that it risks matching something unrelated.
// Populated with blank answers -- these are prompts for the applicant to
// answer in their own words, never something this tool should guess at.
const TOP_QUESTIONS = [
  "why do you want to work",
  "why are you interested in this",
  "why should we hire you",
  "tell us about yourself",
  "tell me about yourself",
  "describe yourself in a few words",
  "good fit for this",
  "greatest strength",
  "greatest weakness",
  "areas of improvement",
  "describe a challenge",
  "time you failed",
  "overcame an obstacle",
  "conflict with a co",
  "leadership experience",
  "greatest achievement",
  "proudest accomplishment",
  "why are you leaving",
  "why did you leave",
  "career goals",
  "see yourself in",
  "what motivates you",
  "ideal work environment",
  "management style",
  "handle stress",
  "handle pressure",
  "prioritize your work",
  "communication style",
  "know about our company",
  "know about this role",
  "anything else you would like",
  "additional information",
  "worked as part of a team",
  "showed initiative",
  "learn something new quickly",
  "sets you apart",
  "work style",
  "coworkers describe you",
  "colleagues describe you",
  "manager describe you",
  "disagreed with your manager",
  "mistake you made",
  "experience with remote work",
  "change careers",
  "questions do you have",
  "ideal manager",
  "passionate about",
  "project you are most proud",
  "stay organized",
  "approach to problem solving",
  "work in this industry",
  "mentoring others",
];

function emptyProfile() {
  return {
    first_name: "", last_name: "", middle_name: "", preferred_name: "",
    email: "", phone: "",
    address_line1: "", address_line2: "", city: "", state: "", postal_code: "", country: "",
    linkedin_url: "", github_url: "", portfolio_url: "",
    current_company: "", current_title: "", years_experience: "", desired_salary: "",
    notice_period: "", how_heard: "", gpa: "", security_clearance: "",
    preferred_location: "", employment_type: "", languages: "", references: "",
    education_level: "", citizenship_status: "", referral_name: "",
    gender: "", pronouns: "", hispanic_latino: "", race_ethnicity: "",
    veteran_status: "", disability_status: "", sexual_orientation: "", transgender_status: "",
    cover_letter_text: "",
    education: [], experience: [], custom_answers: {},
    resume_file: null, cover_letter_file: null,
  };
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function renderDocSlot(key, elId, inputId) {
  const holder = document.getElementById(elId);
  const info = state.profile[key];
  if (!info) {
    holder.innerHTML = '<span class="note">No file saved.</span>';
    return;
  }
  holder.innerHTML = `<span class="note">${esc(info.name)}${info.size ? ` (${formatBytes(info.size)})` : ""}</span>`;
  const btn = document.createElement("button");
  btn.className = "danger";
  btn.type = "button";
  btn.textContent = "Remove";
  btn.style.marginLeft = "8px";
  btn.onclick = async () => {
    state.profile[key] = null;
    await chrome.storage.local.set({ profile: state.profile });
    renderDocSlot(key, elId, inputId);
  };
  holder.appendChild(btn);
}

function renderDocs() {
  renderDocSlot("resume_file", "resume-current", "resume-input");
  renderDocSlot("cover_letter_file", "cover-current", "cover-input");
}

function buildBoolGrid() {
  const grid = document.getElementById("bool-grid");
  grid.innerHTML = "";
  for (const field of BOOLEAN_FIELDS) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    wrap.innerHTML = `
      <label>${BOOL_LABELS[field] || field}</label>
      <select data-bool="${field}">
        <option value="">Not set</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>`;
    grid.appendChild(wrap);
  }
}

function buildSelfIdGrid() {
  const grid = document.getElementById("selfid-grid");
  grid.innerHTML = "";
  for (const field of SELF_ID_FIELDS) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const options = (SELF_ID_CHOICES[field] || [])
      .map((c) => `<option value="${c.replace(/"/g, "&quot;")}">${c}</option>`)
      .join("");
    wrap.innerHTML = `
      <label>${SELF_ID_DISPLAY_NAMES[field] || field}</label>
      <select data-f="${field}"><option value="">Not set</option>${options}</select>`;
    grid.appendChild(wrap);
  }
}

function fillOptionChoices() {
  document.querySelectorAll("select[data-choices]").forEach((sel) => {
    const key = sel.getAttribute("data-choices");
    const options = (OPTION_CHOICES[key] || [])
      .map((c) => `<option value="${c.replace(/"/g, "&quot;")}">${c}</option>`)
      .join("");
    sel.innerHTML = `<option value="">Not set</option>${options}`;
  });
}

function eduRow(entry = {}) {
  const div = document.createElement("div");
  div.className = "listitem";
  div.innerHTML = `
    <div class="top"><button class="danger" type="button">Remove</button></div>
    <div class="grid">
      <div class="field"><label>School</label><input data-k="school" value="${esc(entry.school)}"></div>
      <div class="field"><label>Degree</label><input data-k="degree" value="${esc(entry.degree)}"></div>
      <div class="field"><label>Field of study</label><input data-k="field_of_study" value="${esc(entry.field_of_study)}"></div>
      <div class="field"><label>Graduation year</label><input data-k="graduation_year" value="${esc(entry.graduation_year)}"></div>
    </div>`;
  div.querySelector("button").onclick = () => div.remove();
  return div;
}

function expRow(entry = {}) {
  const div = document.createElement("div");
  div.className = "listitem";
  div.innerHTML = `
    <div class="top"><button class="danger" type="button">Remove</button></div>
    <div class="grid">
      <div class="field"><label>Company</label><input data-k="company" value="${esc(entry.company)}"></div>
      <div class="field"><label>Title</label><input data-k="title" value="${esc(entry.title)}"></div>
      <div class="field"><label>Location</label><input data-k="location" value="${esc(entry.location)}"></div>
      <div class="field"><label>Start date (YYYY-MM)</label><input data-k="start_date" value="${esc(entry.start_date)}" placeholder="2024-07"></div>
      <div class="field"><label>End date (YYYY-MM, or "Present")</label><input data-k="end_date" value="${esc(entry.end_date)}" placeholder="Present"></div>
      <div class="field full"><label>Description</label><textarea data-k="description">${esc(entry.description)}</textarea></div>
    </div>`;
  div.querySelector("button").onclick = () => div.remove();
  return div;
}

function answerRow(keyword = "", answer = "") {
  const div = document.createElement("div");
  div.className = "listitem";
  div.innerHTML = `
    <div class="top"><button class="danger" type="button">Remove</button></div>
    <div class="field"><label>Keyword (matched anywhere in the question's text)</label><input data-k="keyword" value="${esc(keyword)}"></div>
    <div class="field"><label>Answer</label><textarea data-k="answer">${esc(answer)}</textarea></div>`;
  div.querySelector("button").onclick = () => div.remove();
  return div;
}

function esc(v) {
  return (v ?? "").toString().replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function renderCredentials() {
  const list = document.getElementById("cred-list");
  const empty = document.getElementById("cred-empty");
  list.innerHTML = "";
  const hosts = Object.keys(state.credentials || {});
  empty.style.display = hosts.length ? "none" : "block";
  for (const host of hosts) {
    const c = state.credentials[host];
    const row = document.createElement("div");
    row.className = "cred-row";
    row.style.marginBottom = "8px";
    row.innerHTML = `
      <input readonly value="${esc(host)}">
      <input readonly value="${esc(c.login)}">
      <input readonly type="password" value="${esc(c.password)}" data-pw>
      <div class="row">
        <button class="ghost" type="button" data-show>Show</button>
        <button class="danger" type="button" data-forget>Forget</button>
      </div>`;
    row.querySelector("[data-show]").onclick = (e) => {
      const pw = row.querySelector("[data-pw]");
      const isPw = pw.type === "password";
      pw.type = isPw ? "text" : "password";
      e.target.textContent = isPw ? "Hide" : "Show";
    };
    row.querySelector("[data-forget]").onclick = async () => {
      delete state.credentials[host];
      await chrome.storage.local.set({ credentials: state.credentials });
      renderCredentials();
    };
    list.appendChild(row);
  }
}

function loadIntoForm() {
  const p = state.profile;
  document.querySelectorAll("input[data-f], textarea[data-f]").forEach((el) => {
    el.value = p[el.getAttribute("data-f")] || "";
  });
  document.querySelectorAll("select[data-f]").forEach((el) => {
    el.value = p[el.getAttribute("data-f")] || "";
  });
  document.querySelectorAll("select[data-bool]").forEach((el) => {
    const field = el.getAttribute("data-bool");
    const v = p[field];
    el.value = v === true ? "true" : v === false ? "false" : "";
  });

  const eduList = document.getElementById("edu-list");
  eduList.innerHTML = "";
  (p.education || []).forEach((e) => eduList.appendChild(eduRow(e)));

  const expList = document.getElementById("exp-list");
  expList.innerHTML = "";
  (p.experience || []).forEach((e) => expList.appendChild(expRow(e)));

  const answersList = document.getElementById("answers-list");
  answersList.innerHTML = "";
  Object.entries(p.custom_answers || {}).forEach(([k, v]) => answersList.appendChild(answerRow(k, v)));

  document.getElementById("s-auto-accounts").checked = !!(state.settings && state.settings.auto_create_accounts);

  renderCredentials();
  renderDocs();
}

function gatherProfile() {
  const p = emptyProfile();
  document.querySelectorAll("input[data-f], textarea[data-f]").forEach((el) => {
    p[el.getAttribute("data-f")] = el.value.trim();
  });
  document.querySelectorAll("select[data-f]").forEach((el) => {
    p[el.getAttribute("data-f")] = el.value;
  });
  document.querySelectorAll("select[data-bool]").forEach((el) => {
    const field = el.getAttribute("data-bool");
    p[field] = el.value === "true" ? true : el.value === "false" ? false : null;
  });

  p.education = Array.from(document.getElementById("edu-list").children).map((row) => {
    const e = {};
    row.querySelectorAll("[data-k]").forEach((inp) => (e[inp.getAttribute("data-k")] = inp.value.trim()));
    return e;
  });
  p.experience = Array.from(document.getElementById("exp-list").children).map((row) => {
    const e = {};
    row.querySelectorAll("[data-k]").forEach((inp) => (e[inp.getAttribute("data-k")] = inp.value.trim()));
    return e;
  });
  p.custom_answers = {};
  Array.from(document.getElementById("answers-list").children).forEach((row) => {
    const keyword = row.querySelector('[data-k="keyword"]').value.trim();
    const answer = row.querySelector('[data-k="answer"]').value.trim();
    if (keyword) p.custom_answers[keyword] = answer;
  });

  p.resume_file = state.profile.resume_file || null;
  p.cover_letter_file = state.profile.cover_letter_file || null;

  return p;
}

async function save() {
  const status = document.getElementById("status");
  const profile = gatherProfile();
  const missing = ["first_name", "last_name", "email", "phone"].filter((f) => !profile[f]);
  if (missing.length) {
    status.className = "err";
    status.textContent = `Missing required field(s): ${missing.join(", ")}`;
    return;
  }
  const settings = { auto_create_accounts: document.getElementById("s-auto-accounts").checked };
  await chrome.storage.local.set({ profile, settings });
  state.profile = profile;
  state.settings = settings;
  status.className = "ok";
  status.textContent = "Saved.";
  setTimeout(() => (status.textContent = ""), 2500);
}

function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".ptab").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`pt-${tab.getAttribute("data-tab")}`).classList.add("active");
    };
  });
}

(async function init() {
  buildBoolGrid();
  buildSelfIdGrid();
  fillOptionChoices();
  initTabs();

  const stored = await chrome.storage.local.get(["profile", "settings", "credentials"]);
  state.profile = { ...emptyProfile(), ...(stored.profile || {}) };
  state.settings = stored.settings || {};
  state.credentials = stored.credentials || {};
  loadIntoForm();

  document.getElementById("add-edu").onclick = () => document.getElementById("edu-list").appendChild(eduRow());
  document.getElementById("add-exp").onclick = () => document.getElementById("exp-list").appendChild(expRow());
  document.getElementById("add-answer").onclick = () => document.getElementById("answers-list").appendChild(answerRow());

  document.getElementById("add-common-questions").onclick = () => {
    const list = document.getElementById("answers-list");
    const existing = new Set(
      Array.from(list.querySelectorAll('[data-k="keyword"]')).map((inp) => inp.value.trim().toLowerCase())
    );
    let added = 0;
    for (const keyword of TOP_QUESTIONS) {
      if (existing.has(keyword)) continue;
      list.appendChild(answerRow(keyword, ""));
      added++;
    }
    const status = document.getElementById("common-questions-status");
    status.textContent = added
      ? `Added ${added} question(s) below with blank answers -- fill in your own answer for each, delete any you don't want, then Save.`
      : "All of these are already in your list.";
  };
  document.getElementById("save").onclick = save;

  const wireFileInput = (inputId, key, elId) => {
    document.getElementById(inputId).onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const dataUrl = await fileToDataUrl(file);
      state.profile[key] = { name: file.name, size: file.size, dataUrl };
      await chrome.storage.local.set({ profile: state.profile });
      renderDocSlot(key, elId, inputId);
      e.target.value = "";
    };
  };
  wireFileInput("resume-input", "resume_file", "resume-current");
  wireFileInput("cover-input", "cover_letter_file", "cover-current");

  document.getElementById("import-json-btn").onclick = () => {
    const status = document.getElementById("import-status");
    const raw = document.getElementById("import-json").value.trim();
    if (!raw) return;
    let data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      status.className = "note";
      status.style.color = "var(--red)";
      status.textContent = "That's not valid JSON.";
      return;
    }
    const eduList = document.getElementById("edu-list");
    const expList = document.getElementById("exp-list");
    (data.education || []).forEach((e) => eduList.appendChild(eduRow(e)));
    (data.experience || []).forEach((e) => expList.appendChild(expRow(e)));
    status.style.color = "var(--green)";
    status.textContent = `Added ${(data.education || []).length} school(s) and ${(data.experience || []).length} job(s) -- review them on the Education & Work tab, then Save.`;
    document.getElementById("import-json").value = "";
  };
})();
