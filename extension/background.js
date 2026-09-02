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
  "run.js",
];

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !tab.url || !/^https?:/.test(tab.url)) return;
  resetTally(tab.id);
  chrome.action.setBadgeText({ tabId: tab.id, text: "" });
  try {
    // allFrames matters more than it looks: plenty of companies host the job
    // itself on their own site and embed the actual Greenhouse/Lever/iCIMS
    // application in an iframe. Injecting only the top frame does nothing at
    // all on those pages -- the form is in a child frame.
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: SCRIPT_FILES,
    });
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

chrome.tabs.onRemoved.addListener((tabId) => tally.delete(tabId));

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
