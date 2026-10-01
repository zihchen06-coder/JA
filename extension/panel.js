// The on-page panel: what the fill is doing while it does it, what it did to
// every field, what went wrong, and a box to ask about any of it.
//
// Built inside a shadow root. This gets injected into whatever job site the
// applicant happens to be on, and those pages have their own CSS with their
// own opinions about `div`, `button` and `input` -- a shadow root is the only
// way to be sure the panel looks the same on all of them, and that nothing
// here leaks out and disturbs the form being filled.
"use strict";

var JA_PANEL_ID = "ja-autofill-panel";

var _PANEL_CSS = `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .wrap {
    position: fixed; top: 12px; right: 12px; bottom: 12px; width: 340px;
    z-index: 2147483647; display: flex; flex-direction: column;
    background: #0f172a; color: #e2e8f0; border: 1px solid rgba(148,163,184,.25);
    border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,.45);
    font-size: 13px; line-height: 1.5; overflow: hidden;
  }
  .wrap.min { bottom: auto; height: auto; }
  header {
    display: flex; align-items: center; gap: 8px; padding: 10px 12px;
    border-bottom: 1px solid rgba(148,163,184,.18); flex: 0 0 auto;
  }
  header strong { font-size: 13px; font-weight: 600; flex: 1; }
  header button {
    background: transparent; border: none; color: #94a3b8; cursor: pointer;
    font-size: 15px; padding: 2px 6px; border-radius: 6px;
  }
  header button:hover { background: rgba(148,163,184,.15); color: #e2e8f0; }
  .body { flex: 1 1 auto; overflow-y: auto; padding: 10px 12px; }
  .wrap.min .body, .wrap.min .chat { display: none; }
  .line { display: flex; gap: 7px; align-items: baseline; margin-bottom: 4px; color: #cbd5e1; }
  .line .dot { flex: 0 0 auto; }
  .muted { color: #94a3b8; }
  .err { color: #f87171; }
  .ok { color: #4ade80; }
  .warn { color: #fbbf24; }
  .info { color: #7dd3fc; }
  details { margin: 8px 0; }
  summary { cursor: pointer; color: #94a3b8; outline: none; }
  summary:hover { color: #e2e8f0; }
  .thinking {
    white-space: pre-wrap; color: #94a3b8; font-size: 12px; margin-top: 6px;
    padding: 8px; background: rgba(148,163,184,.07); border-radius: 8px;
    max-height: 220px; overflow-y: auto;
  }
  h4 { margin: 12px 0 6px; font-size: 11px; text-transform: uppercase;
       letter-spacing: .06em; color: #94a3b8; font-weight: 600; }
  .field {
    display: block; width: 100%; text-align: left; background: transparent;
    border: none; border-left: 2px solid transparent; color: #cbd5e1;
    padding: 4px 6px; cursor: pointer; border-radius: 0 6px 6px 0; font-size: 12.5px;
  }
  .field:hover { background: rgba(148,163,184,.12); }
  .field .what { color: #94a3b8; display: block; font-size: 11.5px; }
  .field.f { border-left-color: #22c55e; }
  .field.r { border-left-color: #f59e0b; }
  .field.b { border-left-color: #ef4444; }
  .chat { flex: 0 0 auto; border-top: 1px solid rgba(148,163,184,.18); padding: 8px; }
  .msgs { max-height: 220px; overflow-y: auto; margin-bottom: 8px; }
  .msg { margin-bottom: 8px; white-space: pre-wrap; }
  .msg.me { color: #e2e8f0; }
  .msg.me::before { content: "you  "; color: #64748b; }
  .msg.it { color: #cbd5e1; }
  .msg.it::before { content: "claude  "; color: #38bdf8; }
  .row { display: flex; gap: 6px; }
  textarea {
    flex: 1; resize: none; background: rgba(15,23,42,.9); color: #e2e8f0;
    border: 1px solid rgba(148,163,184,.25); border-radius: 8px; padding: 7px 9px;
    font-size: 12.5px; min-height: 34px; max-height: 110px; outline: none;
  }
  textarea:focus { border-color: #38bdf8; }
  .send {
    background: #38bdf8; color: #0f172a; border: none; border-radius: 8px;
    padding: 0 12px; font-weight: 600; cursor: pointer; font-size: 12.5px;
  }
  .send:disabled { opacity: .5; cursor: default; }
  .tools { display: flex; gap: 6px; margin-bottom: 8px; }
  .tool {
    flex: 1; background: rgba(148,163,184,.12); color: #e2e8f0;
    border: 1px solid rgba(148,163,184,.25); border-radius: 8px;
    padding: 6px 8px; cursor: pointer; font-size: 12px;
  }
  .tool.primary { background: #22c55e; border-color: #22c55e; color: #052e16; font-weight: 600; }
  .tool:disabled { opacity: .5; cursor: default; }
  .ai {
    flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
    background: rgba(148,163,184,.12); border: 1px solid rgba(148,163,184,.25);
    border-radius: 8px; padding: 6px 8px; cursor: pointer; font-size: 12px; user-select: none;
  }
  .ai input { margin: 0; cursor: pointer; accent-color: #38bdf8; }
  .learned-row { color: #cbd5e1; font-size: 12px; margin-bottom: 3px; word-break: break-word; }
  .learned-row .arrow { color: #64748b; }
`;

function _panelFlash(el) {
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  const previous = el.style.boxShadow;
  el.style.boxShadow = "0 0 0 4px rgba(56,189,248,.6)";
  setTimeout(() => {
    el.style.boxShadow = previous;
  }, 1400);
}

function createPanel() {
  document.getElementById(JA_PANEL_ID)?.remove();

  const host = document.createElement("div");
  host.id = JA_PANEL_ID;
  const root = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = _PANEL_CSS;
  root.appendChild(style);

  const wrap = document.createElement("div");
  wrap.className = "wrap";
  wrap.innerHTML = `
    <header>
      <strong>Autofill</strong>
      <button class="min" title="Collapse">&minus;</button>
      <button class="close" title="Close">&times;</button>
    </header>
    <div class="body"></div>
    <div class="chat">
      <div class="msgs"></div>
      <div class="tools">
        <button class="tool primary fill" title="Fill this page again from your profile">Autofill</button>
        <label class="ai" title="Let Claude answer the questions your profile can't"><input type="checkbox" class="aibox"> AI assist</label>
      </div>
      <div class="row">
        <textarea placeholder="Ask about this form&hellip;" rows="1"></textarea>
        <button class="send">Ask</button>
      </div>
    </div>`;
  root.appendChild(wrap);
  document.documentElement.appendChild(host);

  const body = wrap.querySelector(".body");
  const msgs = wrap.querySelector(".msgs");
  const input = wrap.querySelector("textarea");
  const send = wrap.querySelector(".send");
  const fillBtn = wrap.querySelector(".fill");
  const aiBox = wrap.querySelector(".aibox");
  let learnedList = null;

  wrap.querySelector(".close").onclick = () => host.remove();
  wrap.querySelector(".min").onclick = () => wrap.classList.toggle("min");

  const scroll = (el) => {
    el.scrollTop = el.scrollHeight;
  };

  const api = {
    // A step of the fill, as it happens -- the panel exists so this is
    // visible rather than inferred from a number at the end.
    log(text, tone = "muted") {
      const line = document.createElement("div");
      line.className = "line";
      line.innerHTML = `<span class="dot ${tone}">&#9679;</span><span class="${tone}"></span>`;
      line.lastChild.textContent = text;
      body.appendChild(line);
      scroll(body);
      return line;
    },

    // Claude's own reasoning for this page, when the API returned a summary
    // of it. Collapsed: it is there to be opened when something looks wrong,
    // not to be read every time.
    showThinking(text) {
      if (!text) return;
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "What Claude was thinking";
      const pre = document.createElement("div");
      pre.className = "thinking";
      pre.textContent = text;
      details.append(summary, pre);
      body.appendChild(details);
      scroll(body);
    },

    // Every field, grouped by what happened to it. Clicking one scrolls to
    // it and flashes it, so "what went wrong" is something you can point at
    // rather than something you have to hunt for.
    showResults(report) {
      const groups = [
        ["Filled", "f", (r) => r.action === "filled"],
        ["Left for you", "r", (r) => r.action === "needs_review"],
        ["Not filled", "b", (r) =>
          r.action === "skipped_no_match" || r.action === "skipped_no_data" || r.action === "error"],
      ];
      for (const [title, cls, match] of groups) {
        const rows = report.results.filter(match);
        if (!rows.length) continue;
        const h = document.createElement("h4");
        h.textContent = `${title} (${rows.length})`;
        body.appendChild(h);
        for (const r of rows) {
          const btn = document.createElement("button");
          btn.className = `field ${cls}`;
          btn.textContent = r.label || r.canonical || "(unlabelled field)";
          if (r.detail) {
            const what = document.createElement("span");
            what.className = "what";
            what.textContent = r.detail.length > 90 ? r.detail.slice(0, 90) + "…" : r.detail;
            btn.appendChild(what);
          }
          btn.onclick = () => _panelFlash(_displayEl(_el(r.ja_id)));
          body.appendChild(btn);
        }
      }
      scroll(body);
    },

    // Something kept for next time, shown the moment it is kept -- "it says
    // it learns" is only believable if you can read what.
    learn(label, value) {
      if (!learnedList) {
        const h = document.createElement("h4");
        h.textContent = "Learned on this page";
        learnedList = document.createElement("div");
        body.append(h, learnedList);
      }
      const row = document.createElement("div");
      row.className = "learned-row";
      const l = document.createElement("span");
      l.textContent = label;
      const arrow = document.createElement("span");
      arrow.className = "arrow";
      arrow.textContent = "  \u2192  ";
      const v = document.createElement("span");
      v.className = "ok";
      v.textContent = value;
      row.append(l, arrow, v);
      learnedList.appendChild(row);
      scroll(body);
    },

    // handler() for the Autofill button.
    onFill(handler) {
      fillBtn.onclick = () => {
        fillBtn.disabled = true;
        fillBtn.textContent = "Filling\u2026";
        handler();
      };
    },

    // The AI assist switch, showing the saved setting; handler(on) is called
    // when it is flipped.
    onAiToggle(initial, handler) {
      aiBox.checked = !!initial;
      aiBox.onchange = () => handler(aiBox.checked);
    },

    say(text, who) {
      const div = document.createElement("div");
      div.className = `msg ${who}`;
      div.textContent = text;
      msgs.appendChild(div);
      scroll(msgs);
      return div;
    },

    // handler(text) -> Promise<string>, whatever it resolves to is shown.
    onAsk(handler) {
      const ask = async () => {
        const text = input.value.trim();
        if (!text) return;
        input.value = "";
        send.disabled = true;
        api.say(text, "me");
        const pending = api.say("…", "it");
        try {
          pending.textContent = (await handler(text)) || "(no reply)";
        } catch (exc) {
          pending.textContent = String(exc);
        }
        scroll(msgs);
        send.disabled = false;
      };
      send.onclick = ask;
      input.onkeydown = (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          ask();
        }
      };
    },
  };

  return api;
}
