// Per-site account credentials for job portals that require signing up
// before you can apply (iCIMS is the most common offender). Stored in
// chrome.storage.local -- local to this browser profile only, never synced
// to a Google account, never transmitted anywhere by this extension.
// Ported from ja/credentials.py -- keep the two in sync.
"use strict";

var _ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*";
var _SPECIAL_RE = /[!@#$%^&*]/;

function generatePassword(length = 16) {
  for (;;) {
    const bytes = new Uint32Array(length);
    crypto.getRandomValues(bytes);
    let pwd = "";
    for (let i = 0; i < length; i++) pwd += _ALPHABET[bytes[i] % _ALPHABET.length];
    if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd) && /[0-9]/.test(pwd) && _SPECIAL_RE.test(pwd)) {
      return pwd;
    }
  }
}

function hostnameFor(url) {
  try {
    return new URL(url).host;
  } catch (e) {
    return "";
  }
}

async function loadCredentials() {
  const { credentials } = await chrome.storage.local.get("credentials");
  return credentials || {};
}

async function saveCredentials(data) {
  await chrome.storage.local.set({ credentials: data });
}

// Returns [login, password] for this hostname, creating and saving a new
// strong password the first time. Keyed by the full hostname, not just the
// base domain -- many companies share the same underlying ATS (e.g. many
// different employers each run their own careers site on *.icims.com), and
// each is a separate candidate database even though the platform is shared.
async function getOrCreate(hostname, defaultLogin) {
  const creds = await loadCredentials();
  if (creds[hostname] && creds[hostname].login && creds[hostname].password) {
    return [creds[hostname].login, creds[hostname].password];
  }
  const password = generatePassword();
  creds[hostname] = { login: defaultLogin, password };
  await saveCredentials(creds);
  return [defaultLogin, password];
}
