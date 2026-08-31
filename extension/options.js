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
  };
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
      <div class="field"><label>Start date</label><input data-k="start_date" value="${esc(entry.start_date)}"></div>
      <div class="field"><label>End date</label><input data-k="end_date" value="${esc(entry.end_date)}"></div>
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
  document.getElementById("save").onclick = save;
})();
