// Entry point injected into the active tab when the toolbar icon is
// clicked. Loads the saved profile/settings, runs the fill, and shows a
// small on-page summary -- the same "see it on the actual form" pattern as
// the outlines drawn on individual fields.
"use strict";

var REQUIRED_FIELDS = ["first_name", "last_name", "email", "phone"];

function _showBanner(html, tone) {
  document.getElementById("ja-autofill-banner")?.remove();
  const colors = {
    info: ["#1e293b", "#38bdf8"],
    ok: ["#1e293b", "#22c55e"],
    warn: ["#1e293b", "#f59e0b"],
  };
  const [bg, accent] = colors[tone] || colors.info;
  const banner = document.createElement("div");
  banner.id = "ja-autofill-banner";
  banner.style.cssText = `
    position: fixed; top: 16px; right: 16px; z-index: 2147483647;
    background: ${bg}; color: #e2e8f0; border: 1px solid ${accent};
    border-radius: 10px; padding: 14px 18px; font: 13px/1.5 -apple-system,
    BlinkMacSystemFont, "Segoe UI", sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,.4);
    max-width: 320px;
  `;
  banner.innerHTML = html;
  const close = document.createElement("div");
  close.textContent = "×";
  close.style.cssText =
    "position:absolute; top:6px; right:10px; cursor:pointer; color:#94a3b8; font-size:16px;";
  close.onclick = () => banner.remove();
  banner.style.position = "fixed";
  banner.appendChild(close);
  document.body.appendChild(banner);
  setTimeout(() => banner.remove(), 15000);
}

(async () => {
  // This runs in every frame on the page, and most of them are ads and
  // trackers with no form in them at all. Bail before doing anything --
  // before even reading storage -- so those frames stay silent instead of
  // each drawing their own banner.
  if (!document.querySelector('input, select, textarea, button[aria-haspopup="listbox"]')) return;

  const {
    profile,
    settings,
    credentials: savedCreds,
    learned_aliases: learnedAliases,
  } = await chrome.storage.local.get(["profile", "settings", "credentials", "learned_aliases"]);

  if (!profile || REQUIRED_FIELDS.some((f) => !profile[f])) {
    _showBanner(
      "<strong>Set up your profile first</strong><br>Right-click this extension's icon &rarr; Options, " +
        "fill in your name/email/phone, then click the icon again on the application page.",
      "warn"
    );
    chrome.runtime.sendMessage({ type: "ja-fill-done", filled: 0, review: 0, blank: 0, setupNeeded: true });
    return;
  }

  const autoCreateAccounts = !!(settings && settings.auto_create_accounts);
  const fieldsData = extractFields();
  // A frame whose only controls were hidden or non-fillable.
  if (!fieldsData.length) return;
  let creds = null;
  if (autoCreateAccounts && fieldsData.some((f) => f.type === "password")) {
    const hostname = hostnameFor(location.href);
    creds = await getOrCreate(hostname, profile.email);
  }

  // Label phrasings worked out on earlier applications, so they match for
  // free this time instead of costing another API call.
  setLearnedAliases(learnedAliases || {});

  const useLlm = !!(settings && settings.use_llm);
  const report = await fillForm(profile, creds, {
    tailorCoverLetter: useLlm && !!(settings && settings.tailor_cover_letter),
  });

  // Second pass: hand whatever the rule-based matcher couldn't place to
  // Claude, if the user has turned that on and saved a key. Failures here
  // are never fatal -- the deterministic fill already happened and stands.
  let claudeFilled = 0;
  let claudeError = null;
  if (useLlm) {
    const pending = llmFieldsFor(report);
    if (pending.length) {
      _showBanner(
        `<strong>Asking Claude</strong><br>${pending.length} field(s) the matcher didn't recognise\u2026`,
        "info"
      );
      try {
        const reply = await chrome.runtime.sendMessage({
          type: "ja-llm-resolve",
          request: {
            profile,
            fields: pending,
            pageUrl: location.href,
            job: extractJobContext(),
          },
        });
        if (reply && reply.error) {
          claudeError = reply.error;
        } else if (reply) {
          claudeFilled = await applyLlmAnswers(report, reply.answers, reply.skipped);
          const learned = learnFromAnswers(report, reply.answers, profile);
          if (Object.keys(learned).length) {
            chrome.runtime.sendMessage({ type: "ja-learned", learned });
          }
        }
      } catch (exc) {
        claudeError = String(exc);
      }
    }
  }

  const filled = report.results.filter((r) => r.action === "filled").length;
  const review = report.results.filter((r) => r.action === "needs_review").length;
  const blankRequired = report.results.filter(
    (r) => r.required && (r.action === "skipped_no_match" || r.action === "skipped_no_data")
  ).length;

  const parts = [`<strong>Autofill done</strong>`];
  parts.push(`<div style="margin-top:6px; color:#4ade80;">&#9679; ${filled} field(s) filled</div>`);
  if (claudeFilled) {
    parts.push(
      `<div style="color:#7dd3fc;">&#9679; ${claudeFilled} of those answered by Claude &mdash; read them before you submit</div>`
    );
  }
  if (claudeError) {
    parts.push(`<div style="color:#fbbf24;">&#9679; Claude step failed: ${claudeError}</div>`);
  }
  if (review) parts.push(`<div style="color:#fbbf24;">&#9679; ${review} flagged for you to answer</div>`);
  if (blankRequired) parts.push(`<div style="color:#f87171;">&#9679; ${blankRequired} required field(s) left blank</div>`);
  parts.push(`<div style="margin-top:8px; color:#94a3b8; font-size:11px;">Nothing was submitted. Review the highlighted fields, then submit yourself.</div>`);
  _showBanner(parts.join(""), blankRequired ? "warn" : "ok");

  chrome.runtime.sendMessage({ type: "ja-fill-done", filled, review, blank: blankRequired, setupNeeded: false });
})();
