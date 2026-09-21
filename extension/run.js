// Entry point injected into the active tab when the toolbar icon is
// clicked. Loads the saved profile/settings, runs the fill, and shows a
// small on-page summary -- the same "see it on the actual form" pattern as
// the outlines drawn on individual fields.
"use strict";

var REQUIRED_FIELDS = ["first_name", "last_name", "email", "phone"];

// Set as soon as a panel exists, so a failure after that point can be
// reported into it rather than vanishing.
var _jaPanel = null;

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

// Pressed the icon on a page whose top frame has no fields of its own.
// Either the application sits in an embedded frame -- Greenhouse and Lever
// inside a company's own careers site, which is a lot of them -- and the
// filling happened down there where no panel can draw, or there is no form
// here at all. From the outside those looked identical: nothing happened.
async function _reportWithoutOwnForm() {
  const { settings } = await chrome.storage.local.get(["settings"]);
  if (settings && settings.show_panel === false) return;

  const panel = createPanel();
  panel.log("No fields on the page itself -- looking for a form in an embedded frame\u2026", "muted");

  const heard = await new Promise((resolve) => {
    const done = (value) => {
      chrome.runtime.onMessage.removeListener(listener);
      clearTimeout(timer);
      resolve(value);
    };
    const listener = (msg) => {
      if (msg && msg.type === "ja-tally") done(msg);
    };
    chrome.runtime.onMessage.addListener(listener);
    const timer = setTimeout(() => done(null), 4000);
  });

  if (!heard || (!heard.filled && !heard.review && !heard.blank)) {
    panel.log("No application form found on this page.", "warn");
    panel.log(
      "If this is the job description, open the application itself and press the icon again.",
      "muted"
    );
    return;
  }

  panel.log(`Filled ${heard.filled} field(s) in a frame on this page.`, "ok");
  if (heard.review) panel.log(`${heard.review} flagged for you to answer.`, "warn");
  if (heard.blank) panel.log(`${heard.blank} required field(s) left blank.`, "err");
  panel.log(
    "Those fields live in an embedded frame, so they are outlined on the form itself rather than listed here.",
    "muted"
  );
  panel.log("Nothing was submitted.", "muted");
}

(async () => {
  // This runs in every frame on the page, and most of them are ads and
  // trackers with no form in them at all. Bail before doing anything --
  // before even reading storage -- so those frames stay silent instead of
  // each drawing their own banner.
  if (!document.querySelector('input, select, textarea, button[aria-haspopup="listbox"]')) {
    // Silent is right for an ad frame, and wrong for the page someone just
    // pressed the icon on.
    if (globalThis.__JA_VIA_CLICK && window.top === window) {
      await _reportWithoutOwnForm();
    }
    return;
  }

  const {
    profile,
    settings,
    credentials: savedCreds,
    learned_aliases: learnedAliases,
    learned_answers: learnedAnswers,
  } = await chrome.storage.local.get([
    "profile", "settings", "credentials", "learned_aliases", "learned_answers",
  ]);

  // Only the top frame draws a panel. This script runs in every frame, and a
  // panel inside an embedded application iframe would be clipped to that
  // iframe's box -- and a page with two frames holding forms would get two
  // panels fighting over the same corner.
  const wantPanel = window.top === window && !(settings && settings.show_panel === false);

  // On a click it goes up here, before anything below can return. Every one
  // of those returns was a way for pressing the icon to produce nothing at
  // all, and each was found separately -- an incomplete profile showed a
  // banner that took itself away after fifteen seconds, and a page whose
  // fields are all hidden said nothing whatsoever. On the fill-on-load path
  // it still waits until there is something to report.
  let panel = wantPanel && globalThis.__JA_VIA_CLICK ? createPanel() : null;
  _jaPanel = panel;

  if (!profile || REQUIRED_FIELDS.some((f) => !profile[f])) {
    panel?.log(
      "Set up your profile first: right-click the extension's icon, choose Options, " +
        "and fill in your name, email and phone.",
      "warn"
    );
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
  if (!fieldsData.length) {
    panel?.log("Nothing fillable on this page -- what is here is hidden or read-only.", "warn");
    return;
  }
  let creds = null;
  if (autoCreateAccounts && fieldsData.some((f) => f.type === "password")) {
    const hostname = hostnameFor(location.href);
    creds = await getOrCreate(hostname, profile.email);
  }

  // Label phrasings worked out on earlier applications, so they match for
  // free this time instead of costing another API call.
  // Anything a previous version learned that today's rules would refuse is
  // dropped here rather than left to keep doing damage.
  const safeAliases = sanitizeLearnedAliases(learnedAliases || {}, profile);
  setLearnedAliases(safeAliases);
  if (Object.keys(safeAliases).length !== Object.keys(learnedAliases || {}).length) {
    chrome.runtime.sendMessage({ type: "ja-learned-replace", learned: safeAliases });
  }
  setLearnedAnswers(learnedAnswers || {});

  if (!panel && wantPanel) {
    panel = createPanel();
    _jaPanel = panel;
  }
  panel?.log(`Found ${fieldsData.length} field(s) on this page.`);

  // The fill itself, as something that can be asked for rather than
  // something that just happens. Another autofill extension on the same
  // page -- Simplify, most often -- listens to the same change events this
  // fires, and the two overwrite each other: on Blue Origin every core
  // field came back cleared. Filling on arrival makes that fight happen
  // whether or not it was wanted.
  let report = null;

  async function doFill() {
    const useLlm = !!(settings && settings.use_llm);
    report = await fillForm(profile, creds, {
      tailorCoverLetter: useLlm && !!(settings && settings.tailor_cover_letter),
      answerSensitive: useLlm && (!settings || settings.route_saved_answers !== false),
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
              routeSavedAnswers: !settings || settings.route_saved_answers !== false,
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
            // Including what the fill already set: correcting one of those
            // is most of what anybody asks the chat for.
            fields: llmFieldsFor(report, { includeFilled: true }),
          },
        });
        if (!reply) return "No reply came back.";
        if (reply.error) return reply.error;
        const changed = await applyLlmAnswers(report, reply.answers, {}, profile, {
          includeFilled: true,
        });
        history.push({ role: "user", content: text });
        history.push({ role: "assistant", content: reply.reply });
        return changed ? `${reply.reply}\n\n(${changed} field(s) changed.)` : reply.reply;
      });
    }
  }

  panel?.onFill(doFill);

  // Manual mode is the answer to that fight: the panel opens, nothing is
  // touched, and it is a choice -- Autofill when this is the tool doing the
  // filling, Learn this form when the other one already did it and its
  // answers are worth keeping. With no panel there is no button to press,
  // so the fill still runs rather than the click doing nothing at all.
  if (panel && settings && settings.manual_fill) {
    panel.log(
      "Ready, and nothing touched yet. Press Autofill to fill this in, or " +
        "Learn this form to keep what is already here.",
      "info"
    );
  } else {
    await doFill();
  }

  // "Learn this form", for the form that comes round again: fill it in by
  // hand once, press this, and the next one like it fills itself. Separate
  // from the fill on purpose -- watch-and-learn only notices what is typed
  // into what was left blank, so an answer the applicant corrected, or one
  // they entered before the panel ever opened, was never picked up.
  //
  // It sets nothing on the page. Sensitive and consent answers go to the
  // profile-suggestion store, never to the label-keyed one -- learnFromPage
  // goes through learnFromPrefilled for exactly that gate.
  panel?.onLearn(async () => {
    const { answers, suggestions } = learnFromPage(profile);
    const learned = Object.keys(answers).length;
    const gaps = Object.keys(suggestions).length;

    if (learned) {
      await chrome.runtime.sendMessage({ type: "ja-learned-answers", answers });
    }
    if (gaps) {
      await chrome.runtime.sendMessage({ type: "ja-profile-suggestions", suggestions });
    }

    if (!learned && !gaps) {
      return "Nothing to remember here -- fill the form in first, then press this.";
    }

    // What was just stored is keyed by this form's exact wording, which is
    // brittle: the same question asked differently on the next site misses.
    // With the AI pass on, ask Claude which profile field each question is
    // asking for -- never what the answer is, which is already stored -- and
    // keep that as an alias, which holds for any wording of that field.
    let mapped = 0;
    if (settings && settings.use_llm && learned) {
      const reply = await chrome.runtime.sendMessage({
        type: "ja-learn-map",
        request: {
          profile,
          items: Object.entries(answers).map(([label, answer]) => ({ label, answer })),
        },
      });
      if (reply && reply.error) {
        panel?.log(reply.error, "err");
      } else if (reply && reply.mappings) {
        // The gate, rather than the prompt: a mapping onto a self-ID,
        // consent or criminal-history field never reaches storage, whatever
        // came back.
        const safe = sanitizeLearnedAliases(reply.mappings, profile);
        mapped = Object.keys(safe).length;
        if (mapped) {
          setLearnedAliases({ ...getLearnedAliases(), ...safe });
          await chrome.runtime.sendMessage({ type: "ja-learned", learned: safe });
        }
      }
    }

    const parts = [];
    if (learned) parts.push(`Remembered ${learned} answer(s). The next form like this one fills itself.`);
    if (mapped) {
      parts.push(`${mapped} of them matched to a profile field, so any wording of those fills now.`);
    }
    // Never written on their behalf: these are identity, and a page can hold
    // a default nobody chose or somebody else's value.
    if (gaps) parts.push(`${gaps} more to confirm under Options -> Learned.`);
    return parts.join(" ");
  });

  // Whatever arrived already filled -- typed before clicking, put there by
  // another autofill extension, or remembered by the site -- is an answer
  // too, and was being stepped over in silence.
  if (report && (!settings || settings.watch_and_learn !== false)) {
    const prefilled = learnFromPrefilled(report, profile);
    const learnedNow = Object.keys(prefilled.answers).length;
    if (learnedNow) {
      chrome.runtime.sendMessage({ type: "ja-learned-answers", answers: prefilled.answers });
      panel?.log(`Remembered ${learnedNow} answer(s) already on this page.`, "info");
    }
    const gaps = Object.keys(prefilled.suggestions).length;
    if (gaps) {
      chrome.runtime.sendMessage({
        type: "ja-profile-suggestions",
        suggestions: prefilled.suggestions,
      });
      panel?.log(
        `${gaps} value(s) here aren't in your profile -- see Options, Learned tab.`,
        "info"
      );
    }
  }

  // From here on, whatever the applicant types into what was left blank is
  // noticed and kept, so the same question fills itself next time. No API
  // call, no prompting, and their own answer rather than anyone's reading
  // of it.
  if (report && (!settings || settings.watch_and_learn !== false)) {
    watchForCorrections(
      report,
      (learned) => chrome.runtime.sendMessage({ type: "ja-learned-answers", answers: learned }),
      (suggested) =>
        chrome.runtime.sendMessage({ type: "ja-profile-suggestions", suggestions: suggested })
    );
  }
})().catch((exc) => {
  // Otherwise this is an unhandled rejection in a console nobody has open,
  // and the icon looks like it did nothing. Which is how it looked.
  try {
    _jaPanel?.log(String(exc && exc.stack ? exc.stack : exc), "err");
  } catch (ignored) {
    /* the panel is the thing that broke */
  }
  console.error("Job Application Autofill:", exc);
});
