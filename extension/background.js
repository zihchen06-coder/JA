// No default_popup is set in the manifest, so clicking the toolbar icon
// fires this listener directly -- one click, no intermediate menu, matching
// how the commercial autofill extensions this was modeled on behave.
"use strict";

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
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: SCRIPT_FILES });
  } catch (exc) {
    console.error("Job Application Autofill: could not run on this page.", exc);
  }
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== "ja-fill-done" || !sender.tab?.id) return;
  const tabId = sender.tab.id;
  if (message.setupNeeded) {
    chrome.action.setBadgeText({ tabId, text: "!" });
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#f59e0b" });
    return;
  }
  chrome.action.setBadgeText({ tabId, text: String(message.filled) });
  chrome.action.setBadgeBackgroundColor({
    tabId,
    color: message.blank ? "#ef4444" : message.review ? "#f59e0b" : "#22c55e",
  });
});
