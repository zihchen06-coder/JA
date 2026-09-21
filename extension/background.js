// No default_popup is set in the manifest, so clicking the toolbar icon
// fires this listener directly -- one click, no intermediate menu, matching
// how the commercial autofill extensions this was modeled on behave.
"use strict";

importScripts("llm.js");

const SCRIPT_FILES = [
  "field_aliases.js",
  "matcher.js",
  "extractor.js",
  "credentials.js",
  "filler.js",
  "panel.js",
  "run.js",
];

// The applicant-tracking systems worth auto-filling: a page on one of these
// is an application, not a page that happens to have a text box on it. Kept
// in step with manifest.json's host_permissions -- injecting without a click
// needs the permission granted up front, not activeTab's on-click grant.
const KNOWN_ATS = [
  "myworkdayjobs.com", "workday.com", "icims.com", "greenhouse.io",
  "lever.co", "smartrecruiters.com", "ashbyhq.com", "jobvite.com",
  "taleo.net", "successfactors.com", "workable.com", "breezy.hr",
  "applytojob.com", "bamboohr.com", "paylocity.com", "dayforcehcm.com",
];

function isKnownAts(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return KNOWN_ATS.some((d) => host === d || host.endsWith("." + d));
  } catch (exc) {
    return false;
  }
}

// Changing a default only reaches an install that has never opened Options:
// saving there writes every setting explicitly, so an existing install holds
// `false` for these and would go on behaving the old way after an update.
// This carries such an install over, once. It records that it ran, so a
// setting deliberately turned off afterwards is never turned back on.
const DEFAULTS_MIGRATION = "defaults_on_v1";

async function applyDefaultsOnce() {
  const stored = await chrome.storage.local.get(["settings", "llm_api_key", "migrations"]);
  const migrations = stored.migrations || {};
  if (migrations[DEFAULTS_MIGRATION]) return;

  const settings = { ...(stored.settings || {}) };
  settings.auto_fill_known_sites = true;
  settings.route_saved_answers = true;
  // The AI pass spends money on a paid API, so it follows the key rather than
  // a default: on once one is saved, left alone when there isn't one, where
  // turning it on would only put "No API key saved." on every page.
  if (stored.llm_api_key) settings.use_llm = true;

  migrations[DEFAULTS_MIGRATION] = Date.now();
  await chrome.storage.local.set({ settings, migrations });
}

// Fires on first install and on every update, which is when a pulled change
// to these defaults needs to reach a browser that already has the extension.
chrome.runtime.onInstalled.addListener(() => {
  applyDefaultsOnce().catch((exc) =>
    console.error("Job Application Autofill: could not apply defaults.", exc)
  );
});

async function runFill(tabId, viaClick) {
  resetTally(tabId);
  chrome.action.setBadgeText({ tabId, text: "" });

  // Pressing the icon and getting nothing at all is the worst answer this
  // can give, and it was the usual one on any page whose form sits in an
  // embedded frame: run.js bails in a frame with no fields, the top frame
  // of such a page often has none, and the panel only ever draws there.
  // A click says so, so the top frame knows to speak up either way.
  if (viaClick) {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: () => {
        globalThis.__JA_VIA_CLICK = true;
      },
    });
  }

  await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    files: SCRIPT_FILES,
  });

  // What every frame between them managed, back to the one that can show it.
  if (viaClick) {
    setTimeout(() => {
      const t = tally.get(tabId) || { filled: 0, review: 0, blank: 0 };
      chrome.tabs
        .sendMessage(tabId, { type: "ja-tally", ...t }, { frameId: 0 })
        .catch(() => {});
    }, 1500);
  }
}

// A multi-page application is the normal case on Workday and iCIMS -- five
// or six pages, each its own form. Filling each one on arrival turns that
// from six clicks into one. Nothing is submitted, so the applicant still
// walks the pages; they just arrive already filled.
const lastFilled = new Map();

chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== "complete" || !tab.url || !isKnownAts(tab.url)) return;
  const { settings } = await chrome.storage.local.get(["settings"]);
  if (settings && settings.auto_fill_known_sites === false) return;
  // Workday rewrites the URL as you move through the flow without a reload,
  // and a reload of the same page shouldn't fill twice over.
  if (lastFilled.get(tabId) === tab.url) return;
  lastFilled.set(tabId, tab.url);
  try {
    await runFill(tabId);
  } catch (exc) {
    console.error("Job Application Autofill: auto-fill failed.", exc);
  }
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !tab.url || !/^https?:/.test(tab.url)) return;
  try {
    // allFrames matters more than it looks: plenty of companies host the job
    // itself on their own site and embed the actual Greenhouse/Lever/iCIMS
    // application in an iframe. Injecting only the top frame does nothing at
    // all on those pages -- the form is in a child frame.
    lastFilled.set(tab.id, tab.url);
    await runFill(tab.id, true);
  } catch (exc) {
    console.error("Job Application Autofill: could not run on this page.", exc);
  }
});

// With allFrames injection a page can report from several frames at once
// (the outer page plus the embedded application), so the badge has to add
// them up rather than let the last frame to finish overwrite the rest.
// Reset on each click; frames with nothing fillable stay quiet entirely.
const tally = new Map();

function resetTally(tabId) {
  tally.set(tabId, { filled: 0, review: 0, blank: 0 });
}

function paintBadge(tabId) {
  const t = tally.get(tabId);
  if (!t) return;
  chrome.action.setBadgeText({ tabId, text: String(t.filled) });
  chrome.action.setBadgeBackgroundColor({
    tabId,
    color: t.blank ? "#ef4444" : t.review ? "#f59e0b" : "#22c55e",
  });
}

chrome.tabs.onRemoved.addListener((tabId) => {
  tally.delete(tabId);
  lastFilled.delete(tabId);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id;

  if (message?.type === "ja-llm-resolve") {
    // Returning true keeps the message channel open for the async reply.
    (async () => {
      try {
        const { llm_api_key: apiKey } = await chrome.storage.local.get(["llm_api_key"]);
        sendResponse(await resolveWithClaude({ ...message.request, apiKey }));
      } catch (exc) {
        sendResponse({ error: String(exc) });
      }
    })();
    return true;
  }

  if (message?.type === "ja-learn-map") {
    (async () => {
      try {
        const { llm_api_key: apiKey } = await chrome.storage.local.get(["llm_api_key"]);
        sendResponse(await mapLabelsWithClaude({ ...message.request, apiKey }));
      } catch (exc) {
        sendResponse({ error: String(exc) });
      }
    })();
    return true;
  }

  if (message?.type === "ja-chat") {
    (async () => {
      try {
        const { llm_api_key: apiKey } = await chrome.storage.local.get(["llm_api_key"]);
        sendResponse(await chatWithClaude({ ...message.request, apiKey }));
      } catch (exc) {
        sendResponse({ error: String(exc) });
      }
    })();
    return true;
  }

  if (message?.type === "ja-parse-resume") {
    (async () => {
      try {
        const { llm_api_key: apiKey } = await chrome.storage.local.get(["llm_api_key"]);
        sendResponse(await parseResumeWithClaude({ ...message.request, apiKey }));
      } catch (exc) {
        sendResponse({ error: String(exc) });
      }
    })();
    return true;
  }

  if (message?.type === "ja-misses") {
    (async () => {
      const { misses } = await chrome.storage.local.get(["misses"]);
      const store = misses || {};
      for (const miss of message.misses || []) {
        const key = `${message.host}|${miss.key}`;
        const prior = store[key];
        store[key] = {
          host: message.host,
          label: miss.label,
          action: miss.action,
          detail: miss.detail,
          required: miss.required,
          type: miss.type,
          count: (prior ? prior.count : 0) + 1,
          last: Date.now(),
        };
      }
      await chrome.storage.local.set({ misses: capMisses(store) });
    })();
    return;
  }

  if (message?.type === "ja-applied") {
    (async () => {
      const { applications } = await chrome.storage.local.get(["applications"]);
      const list = applications || [];
      const last = list[list.length - 1];
      // A multi-page application is one application. Same site within half an
      // hour updates that row rather than adding five more.
      if (last && last.host === message.entry.host && message.entry.at - last.at < 30 * 60 * 1000) {
        last.filled += message.entry.filled;
        last.review += message.entry.review;
        last.blank += message.entry.blank;
        last.pages = (last.pages || 1) + 1;
        last.at = message.entry.at;
        if (!last.title && message.entry.title) last.title = message.entry.title;
      } else {
        list.push({ ...message.entry, pages: 1 });
      }
      // Keeping every application ever would grow without limit; the recent
      // few hundred is what anyone actually looks back over.
      await chrome.storage.local.set({ applications: list.slice(-500) });
    })();
    return;
  }

  if (message?.type === "ja-learned-answers") {
    (async () => {
      const { learned_answers: existing } = await chrome.storage.local.get(["learned_answers"]);
      await chrome.storage.local.set({
        learned_answers: capLearned(mergeLearnedAnswers(existing, message.answers)),
      });
    })();
    return;
  }

  if (message?.type === "ja-profile-suggestions") {
    (async () => {
      const { profile_suggestions: existing } = await chrome.storage.local.get([
        "profile_suggestions",
      ]);
      await chrome.storage.local.set({
        profile_suggestions: capLearned({ ...(existing || {}), ...message.suggestions }, 200),
      });
    })();
    return;
  }

  if (message?.type === "ja-learned-replace") {
    chrome.storage.local.set({ learned_aliases: message.learned });
    return;
  }

  if (message?.type === "ja-learned") {
    (async () => {
      const { learned_aliases: existing } = await chrome.storage.local.get(["learned_aliases"]);
      await chrome.storage.local.set({
        learned_aliases: capLearned({ ...(existing || {}), ...message.learned }, 1000),
      });
    })();
    return;
  }

  if (message?.type !== "ja-fill-done" || !tabId) return;
  if (message.setupNeeded) {
    chrome.action.setBadgeText({ tabId, text: "!" });
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#f59e0b" });
    return;
  }
  const t = tally.get(tabId);
  if (!t) return;
  t.filled += message.filled || 0;
  t.review += message.review || 0;
  t.blank += message.blank || 0;
  paintBadge(tabId);
});
