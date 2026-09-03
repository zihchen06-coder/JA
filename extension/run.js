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
    learned_answers: learnedAnswers,
  } = await chrome.storage.local.get([
    "profile", "settings", "credentials", "learned_aliases", "learned_answers",
  ]);

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
  setLearnedAnswers(learnedAnswers || {});

  // Only the top frame draws a panel. This script runs in every frame, and a
  // panel inside an embedded application iframe would be clipped to that
  // iframe's box -- and a page with two frames holding forms would get two
  // panels fighting over the same corner.
  const wantPanel = window.top === window && !(settings && settings.show_panel === false);
  const panel = wantPanel ? createPanel() : null;
  panel?.log(`Found ${fieldsData.length} field(s) on this page.`);

  const useLlm = !!(settings && settings.use_llm);
  const report = await fillForm(profile, creds, {
    tailorCoverLetter: useLlm && !!(settings && settings.tailor_cover_letter),
    answerSensitive: useLlm && !!(settings && settings.route_saved_answers),
  });

  // Second pass: hand whatever the rule-based matcher couldn't place to
  // Claude, if the user has turned that on and saved a key. Failures here
  // are never fatal -- the deterministic fill already happened and stands.
  let claudeFilled = 0;
  let claudeError = null;
  let learnedCount = 0;
  const job = extractJobContext();
  panel?.log(
    `Filled ${report.results.filter((r) => r.action === "filled").length} from your profile.`,
    "ok"
  );
  if (job.title) panel?.log(`Job: ${job.title}`, "muted");
  if (useLlm) {
    const pending = llmFieldsFor(report);
    if (pending.length) {
      panel?.log(`Asking Claude about ${pending.length} field(s) it didn't recognise\u2026`, "info");
      try {
        const reply = await chrome.runtime.sendMessage({
          type: "ja-llm-resolve",
          request: {
            profile,
            fields: pending,
            pageUrl: location.href,
            job,
            routeSavedAnswers: !!(settings && settings.route_saved_answers),
          },
        });
        if (reply && reply.error) {
          claudeError = reply.error;
          panel?.log(reply.error, "err");
        } else if (reply) {
          panel?.showThinking(reply.thinking);
          claudeFilled = await applyLlmAnswers(report, reply.answers, reply.skipped, profile);
          const learned = learnFromAnswers(report, reply.answers, profile, reply.sources);
          learnedCount = Object.keys(learned).length;
          if (learnedCount) {
            chrome.runtime.sendMessage({ type: "ja-learned", learned });
          }
          // Short answers to questions the profile has no field for -- the
          // ones that would otherwise cost an API call on every form.
          const remembered = rememberableAnswers(report, reply.answers, reply.sources);
          if (Object.keys(remembered).length) {
            chrome.runtime.sendMessage({ type: "ja-learned-answers", answers: remembered });
          }
          panel?.log(`Claude filled ${claudeFilled}.`, claudeFilled ? "ok" : "muted");
          const declined = Object.keys(reply.skipped || {}).length;
          if (declined) panel?.log(`${declined} left for you to answer.`, "warn");
        }
      } catch (exc) {
        claudeError = String(exc);
        panel?.log(claudeError, "err");
      }
    }
  }

  // Setting a value and it staying set are different claims -- check.
  const lost = await verifyFilled(report);
  if (lost.length) {
    panel?.log(`${lost.length} field(s) were cleared by the page after filling.`, "warn");
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
  if (learnedCount) {
    parts.push(
      `<div style="color:#7dd3fc;">&#9679; ${learnedCount} label(s) remembered &mdash; free next time</div>`
    );
  }
  if (claudeError) {
    parts.push(`<div style="color:#fbbf24;">&#9679; Claude step failed: ${claudeError}</div>`);
  }
  if (review) parts.push(`<div style="color:#fbbf24;">&#9679; ${review} flagged for you to answer</div>`);
  if (blankRequired) parts.push(`<div style="color:#f87171;">&#9679; ${blankRequired} required field(s) left blank</div>`);
  parts.push(`<div style="margin-top:8px; color:#94a3b8; font-size:11px;">Nothing was submitted. Review the highlighted fields, then submit yourself.</div>`);
  // The panel says all this and stays put; the banner is the fallback for
  // when it has been turned off.
  if (!panel) _showBanner(parts.join(""), blankRequired ? "warn" : "ok");

  chrome.runtime.sendMessage({ type: "ja-fill-done", filled, review, blank: blankRequired, setupNeeded: false });

  // What this form asked that couldn't be answered, kept across applications
  // so the recurring gaps become visible instead of being re-discovered one
  // form at a time.
  const misses = missedFields(report);
  if (misses.length) {
    chrome.runtime.sendMessage({ type: "ja-misses", host: location.hostname, misses });
  }

  // One row per application, from the top frame only -- an embedded form
  // would otherwise log itself alongside the page hosting it.
  if (window.top === window) {
    chrome.runtime.sendMessage({
      type: "ja-applied",
      entry: {
        url: location.href.slice(0, 400),
        host: location.hostname,
        title: job.title || document.title.slice(0, 200),
        company: job.company || "",
        filled, review, blank: blankRequired,
        at: Date.now(),
      },
    });
  }

  if (panel) {
    if (learnedCount) panel.log(`${learnedCount} label(s) remembered -- free next time.`, "info");
    if (blankRequired) panel.log(`${blankRequired} required field(s) still blank.`, "err");
    panel.log("Nothing submitted. Check the highlighted fields, then submit yourself.", "muted");
    panel.showResults(report);

    // Asking about the form is asking about this exact fill, so the chat
    // gets the same report the panel is showing -- including why each field
    // was left the way it was.
    const history = [];
    panel.onAsk(async (text) => {
      const reply = await chrome.runtime.sendMessage({
        type: "ja-chat",
        request: {
          profile,
          job,
          message: text,
          history,
          report: {
            results: report.results.map((r) => ({
              ja_id: r.ja_id, label: r.label, action: r.action, detail: r.detail,
            })),
          },
          fields: llmFieldsFor(report),
        },
      });
      if (!reply) return "No reply came back.";
      if (reply.error) return reply.error;
      const changed = await applyLlmAnswers(report, reply.answers, {}, profile);
      history.push({ role: "user", content: text });
      history.push({ role: "assistant", content: reply.reply });
      return changed ? `${reply.reply}\n\n(${changed} field(s) changed.)` : reply.reply;
    });
  }

  // From here on, whatever the applicant types into what was left blank is
  // noticed and kept, so the same question fills itself next time. No API
  // call, no prompting, and their own answer rather than anyone's reading
  // of it.
  if (!settings || settings.watch_and_learn !== false) {
    watchForCorrections(report, (learned) => {
      chrome.runtime.sendMessage({ type: "ja-learned-answers", answers: learned });
    });
  }
})();
