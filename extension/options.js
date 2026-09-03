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
  criminal_history: "Has a criminal conviction to disclose",
  sms_consent: "Consents to application texts (SMS)",
  consent_general: "Agrees to standard application terms and authorisations",
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
  document.getElementById("s-use-llm").checked = !!(state.settings && state.settings.use_llm);
  document.getElementById("s-tailor-cover").checked = !!(state.settings && state.settings.tailor_cover_letter);
  document.getElementById("s-route-saved").checked = !!(state.settings && state.settings.route_saved_answers);
  document.getElementById("s-watch-learn").checked = !state.settings || state.settings.watch_and_learn !== false;
  document.getElementById("s-show-panel").checked = !state.settings || state.settings.show_panel !== false;
  document.getElementById("s-auto-fill").checked = !!(state.settings && state.settings.auto_fill_known_sites);
  renderLearned();
  document.getElementById("llm-key").value = state.llmApiKey || "";

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
  const settings = {
    auto_create_accounts: document.getElementById("s-auto-accounts").checked,
    use_llm: document.getElementById("s-use-llm").checked,
    tailor_cover_letter: document.getElementById("s-tailor-cover").checked,
    route_saved_answers: document.getElementById("s-route-saved").checked,
    watch_and_learn: document.getElementById("s-watch-learn").checked,
    show_panel: document.getElementById("s-show-panel").checked,
    auto_fill_known_sites: document.getElementById("s-auto-fill").checked,
  };
  // Kept out of `profile` so it is never in anything exported, imported, or
  // sent to the API as part of the profile blob.
  const llmApiKey = document.getElementById("llm-key").value.trim();
  await chrome.storage.local.set({ profile, settings, llm_api_key: llmApiKey });
  state.llmApiKey = llmApiKey;
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

  const stored = await chrome.storage.local.get([
    "profile", "settings", "credentials", "llm_api_key", "learned_aliases",
    "learned_answers", "misses", "applications",
  ]);
  state.llmApiKey = stored.llm_api_key || "";
  state.learned = stored.learned_aliases || {};
  state.learnedAnswers = stored.learned_answers || {};
  state.misses = stored.misses || {};
  state.applications = stored.applications || [];
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

  document.getElementById("export-profile").onclick = () => {
    // Documents are large base64 blobs not worth pasting into a chat, and
    // credentials are security-sensitive -- neither belongs in an export
    // meant to be shared as plain text.
    const { resume_file, cover_letter_file, ...exportable } = gatherProfile();
    const blob = new Blob([JSON.stringify(exportable, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ja-profile-backup.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

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
    const overwrite = document.getElementById("import-overwrite").checked;
    const eduList = document.getElementById("edu-list");
    const expList = document.getElementById("exp-list");
    const answersList = document.getElementById("answers-list");

    const counts = { added: 0, updated: 0, skipped: 0 };

    // Education and experience have no single natural key, so identity is
    // the pair that actually distinguishes one entry from another:
    // school+degree, company+title. Without this, re-importing the same
    // snippet just stacks up duplicate rows.
    const importList = (entries, listEl, rowFactory, keyOf) => {
      const existing = new Map();
      listEl.querySelectorAll(".listitem").forEach((row) => {
        const values = {};
        row.querySelectorAll("[data-k]").forEach((inp) => (values[inp.getAttribute("data-k")] = inp.value));
        existing.set(keyOf(values), row);
      });
      entries.forEach((entry) => {
        const row = existing.get(keyOf(entry));
        if (!row) {
          listEl.appendChild(rowFactory(entry));
          counts.added++;
          return;
        }
        if (!overwrite) {
          counts.skipped++;
          return;
        }
        row.querySelectorAll("[data-k]").forEach((inp) => {
          const key = inp.getAttribute("data-k");
          if (key in entry) inp.value = entry[key] ?? "";
        });
        counts.updated++;
      });
    };

    const norm = (s) => (s ?? "").toString().trim().toLowerCase();

    // Scalar profile fields, as a resume parse returns them. Same rule as
    // everything else here: a box you have already filled in is left alone
    // unless you asked for it to be replaced.
    Object.entries(data.fields || {}).forEach(([key, value]) => {
      const input = document.querySelector(`[data-f="${CSS.escape(key)}"]`);
      if (!input || !value) return;
      if (input.value.trim() && !overwrite) {
        counts.skipped++;
        return;
      }
      if (input.value.trim()) counts.updated++;
      else counts.added++;
      input.value = value;
    });

    importList(data.education || [], eduList, eduRow, (e) => `${norm(e.school)}|${norm(e.degree)}`);
    importList(data.experience || [], expList, expRow, (e) => `${norm(e.company)}|${norm(e.title)}`);

    // Keyed by keyword -> that row's answer textarea, so a row already
    // added (e.g. by "+ Add top 50 common questions") but still blank gets
    // filled in here instead of silently skipped just because the keyword
    // already exists as a row. A row that already has real content is only
    // replaced when "Replace existing" is ticked -- otherwise something
    // written by hand would be silently overwritten by an import.
    const existingRows = new Map();
    answersList.querySelectorAll(".listitem").forEach((row) => {
      const kwInput = row.querySelector('[data-k="keyword"]');
      if (kwInput) existingRows.set(norm(kwInput.value), row.querySelector('[data-k="answer"]'));
    });
    Object.entries(data.custom_answers || {}).forEach(([keyword, answer]) => {
      const existingAnswerEl = existingRows.get(norm(keyword));
      if (!existingAnswerEl) {
        answersList.appendChild(answerRow(keyword, answer));
        counts.added++;
        return;
      }
      if (!existingAnswerEl.value.trim() || overwrite) {
        if (answer) {
          existingAnswerEl.value = answer;
          counts.updated++;
        }
        return;
      }
      counts.skipped++;
    });

    status.style.color = "var(--green)";
    status.textContent =
      `Added ${counts.added}, updated ${counts.updated}, left ${counts.skipped} alone` +
      (counts.skipped && !overwrite
        ? " (already had content -- tick \"Replace existing\" to overwrite those too)."
        : ".") +
      " Review the Education & Work and Answers tabs, then Save.";
    document.getElementById("import-json").value = "";
  };
})();

// --- Learned label mappings -------------------------------------------------

function renderLearned() {
  const list = document.getElementById("learned-list");
  const empty = document.getElementById("learned-empty");
  const entries = Object.entries(state.learned || {}).sort();
  list.innerHTML = "";
  empty.style.display = entries.length ? "none" : "";

  for (const [label, field] of entries) {
    const row = document.createElement("div");
    row.className = "cred-row";
    row.style.marginBottom = "8px";
    row.innerHTML = `
      <input readonly value="${label.replace(/"/g, "&quot;")}">
      <input readonly value="${BOOL_LABELS[field] || field}">
      <span></span>
      <button class="danger" type="button">Forget</button>`;
    row.querySelector("button").onclick = async () => {
      delete state.learned[label];
      await chrome.storage.local.set({ learned_aliases: state.learned });
      renderLearned();
    };
    list.appendChild(row);
  }
}

function renderLearnedAnswers() {
  const list = document.getElementById("answers-learned-list");
  const empty = document.getElementById("answers-learned-empty");
  const entries = Object.entries(state.learnedAnswers || {}).sort();
  list.innerHTML = "";
  empty.style.display = entries.length ? "none" : "";

  for (const [label, value] of entries) {
    const row = document.createElement("div");
    row.className = "cred-row";
    row.style.marginBottom = "8px";
    row.innerHTML = `
      <input readonly value="${label.replace(/"/g, "&quot;")}">
      <input data-answer="1" value="${String(value).replace(/"/g, "&quot;")}">
      <span></span>
      <button class="danger" type="button">Forget</button>`;
    // Editable in place: a remembered answer you would rather phrase
    // differently is worth correcting once, not deleting and waiting to be
    // asked it again.
    row.querySelector("input[data-answer]").onchange = async (e) => {
      state.learnedAnswers[label] = e.target.value;
      await chrome.storage.local.set({ learned_answers: state.learnedAnswers });
    };
    row.querySelector("button").onclick = async () => {
      delete state.learnedAnswers[label];
      await chrome.storage.local.set({ learned_answers: state.learnedAnswers });
      renderLearnedAnswers();
    };
    list.appendChild(row);
  }
}

document.getElementById("clear-learned").addEventListener("click", async () => {
  state.learned = {};
  state.learnedAnswers = {};
  await chrome.storage.local.set({ learned_aliases: {}, learned_answers: {} });
  renderLearned();
  renderLearnedAnswers();
  renderMisses();
  renderApplications();
});

// --- Gaps and applications --------------------------------------------------

function downloadCsv(name, rows) {
  const escape = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
  const body = rows.map((r) => r.map(escape).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([body], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function missRows() {
  return Object.values(state.misses || {}).sort((a, b) => b.count - a.count);
}

function renderMisses() {
  const list = document.getElementById("misses-list");
  const empty = document.getElementById("misses-empty");
  const rows = missRows();
  list.innerHTML = "";
  empty.style.display = rows.length ? "none" : "";

  for (const m of rows) {
    const row = document.createElement("div");
    row.className = "cred-row";
    row.style.marginBottom = "8px";
    row.innerHTML = `
      <input readonly value="${esc(m.label)}">
      <input readonly value="${esc(m.host)}">
      <input readonly value="${m.count}&times; &middot; ${esc(m.type)}${m.required ? " &middot; required" : ""}">
      <span class="note">${esc(m.action.replace(/_/g, " "))}</span>`;
    list.appendChild(row);
  }
}

function renderApplications() {
  const list = document.getElementById("applications-list");
  const empty = document.getElementById("applications-empty");
  const rows = (state.applications || []).slice().reverse();
  list.innerHTML = "";
  empty.style.display = rows.length ? "none" : "";

  for (const a of rows) {
    const row = document.createElement("div");
    row.className = "cred-row";
    row.style.marginBottom = "8px";
    const when = new Date(a.at).toLocaleString();
    row.innerHTML = `
      <input readonly value="${esc(a.title || a.host)}">
      <input readonly value="${esc(a.host)}">
      <input readonly value="${when}">
      <span class="note">${a.filled} filled${a.blank ? ` &middot; ${a.blank} blank` : ""}</span>`;
    list.appendChild(row);
  }
}

document.getElementById("export-misses").addEventListener("click", () => {
  downloadCsv("autofill-gaps.csv", [
    ["label", "site", "times", "type", "required", "outcome", "detail"],
    ...missRows().map((m) => [m.label, m.host, m.count, m.type, m.required, m.action, m.detail]),
  ]);
});

document.getElementById("clear-misses").addEventListener("click", async () => {
  state.misses = {};
  await chrome.storage.local.set({ misses: {} });
  renderMisses();
});

document.getElementById("export-applications").addEventListener("click", () => {
  downloadCsv("applications.csv", [
    ["date", "role", "company", "site", "url", "pages", "filled", "flagged", "blank"],
    ...(state.applications || []).map((a) => [
      new Date(a.at).toISOString(), a.title, a.company, a.host, a.url,
      a.pages || 1, a.filled, a.review, a.blank,
    ]),
  ]);
});

document.getElementById("clear-applications").addEventListener("click", async () => {
  state.applications = [];
  await chrome.storage.local.set({ applications: [] });
  renderApplications();
});

// --- Reading the saved resume ----------------------------------------------

function dataUrlToBytes(dataUrl) {
  const binary = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// A .docx is a ZIP whose word/document.xml holds the text. Chrome can inflate
// a raw deflate stream natively, so the whole thing is doable here without a
// library -- which matters for an extension loaded from a folder with no
// build step. Only the one entry is needed, so this walks the local file
// headers rather than parsing the central directory.
async function docxText(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder();

  for (let i = 0; i + 30 < bytes.length; i++) {
    if (view.getUint32(i, true) !== 0x04034b50) continue; // local file header
    const method = view.getUint16(i + 8, true);
    const compressed = view.getUint32(i + 18, true);
    const nameLength = view.getUint16(i + 26, true);
    const extraLength = view.getUint16(i + 28, true);
    const nameStart = i + 30;
    const name = decoder.decode(bytes.subarray(nameStart, nameStart + nameLength));
    if (name !== "word/document.xml") continue;

    const start = nameStart + nameLength + extraLength;
    // A streamed zip writes sizes in a trailing descriptor rather than the
    // header; the rest of the file is a safe upper bound either way.
    const body = bytes.subarray(start, compressed ? start + compressed : bytes.length);
    let xml;
    if (method === 0) {
      xml = decoder.decode(body);
    } else {
      const stream = new Blob([body]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
      xml = await new Response(stream).text();
    }
    return xml
      .replace(/<\/w:p>/g, "\n")
      .replace(/<w:tab[^>]*\/>/g, "\t")
      .replace(/<[^>]+>/g, "")
      .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }
  return "";
}

async function resumeForParsing() {
  const info = state.profile.resume_file;
  if (!info || !info.dataUrl) {
    return { error: "No resume saved -- add one above first." };
  }
  const name = (info.name || "").toLowerCase();
  if (name.endsWith(".pdf")) {
    return { fileData: info.dataUrl.slice(info.dataUrl.indexOf(",") + 1), mediaType: "application/pdf" };
  }
  const bytes = dataUrlToBytes(info.dataUrl);
  if (name.endsWith(".docx")) {
    const text = await docxText(bytes);
    return text ? { text } : { error: "Couldn't read text out of that .docx." };
  }
  return { text: new TextDecoder().decode(bytes) };
}

document.getElementById("parse-resume").addEventListener("click", async () => {
  const status = document.getElementById("import-status");
  const button = document.getElementById("parse-resume");
  status.style.color = "";
  status.textContent = "Reading your resume…";
  button.disabled = true;
  try {
    const source = await resumeForParsing();
    if (source.error) throw new Error(source.error);
    const reply = await chrome.runtime.sendMessage({ type: "ja-parse-resume", request: source });
    if (!reply) throw new Error("No reply from the extension's background worker.");
    if (reply.error) throw new Error(reply.error);

    // Into the import box, not straight into the profile: a parse is a
    // reading of a document, and it should be looked at before it becomes
    // the answers that go out on applications.
    document.getElementById("import-json").value = JSON.stringify(reply.parsed, null, 2);
    status.style.color = "var(--green)";
    const { education = [], experience = [], fields = {} } = reply.parsed;
    status.textContent =
      `Read ${education.length} school(s), ${experience.length} job(s) and ` +
      `${Object.keys(fields).length} other field(s). Check it below, then Import.`;
  } catch (exc) {
    status.style.color = "var(--red)";
    status.textContent = String(exc.message || exc);
  } finally {
    button.disabled = false;
  }
});
