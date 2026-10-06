"""run.js against an extension environment that is misbehaving.

The service worker is not a given. MV3 stops it when idle, reloading the
extension from chrome://extensions leaves an already-open tab talking to an
extension that no longer exists, and in both cases chrome.runtime.sendMessage
rejects. Everything run.js sends is a note for later -- a remembered label,
a row in the log -- so none of it may cost the applicant the fill itself.

These load the real run.js into a page with a stubbed `chrome`, so the whole
sequence executes the way it does on a job site.
"""

from __future__ import annotations

import json
import os

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
EXT_DIR = os.path.join(ROOT, "extension")
FIXTURES_DIR = os.path.join(_HERE, "fixtures")
RUN_SCRIPTS = [
    "field_aliases.js", "matcher.js", "extractor.js", "credentials.js",
    "filler.js", "panel.js",
]

with open(os.path.join(FIXTURES_DIR, "profile.json"), encoding="utf-8") as f:
    PROFILE = json.load(f)

FORM = """
  <form>
    <label for="a">First Name</label><input id="a" name="first_name">
    <label for="b">Email</label><input id="b" name="email">
  </form>"""

# Every message rejects, the way it does when nothing is listening.
DEAD_WORKER = """
  window.chrome = {
    storage: { local: { get: async () => ({ profile: PROFILE_JSON, settings: {} }) } },
    runtime: {
      sendMessage: async () => { throw new Error("Could not establish connection."); },
    },
  };
"""


def _run_page(browser, chrome_stub, patch=None):
    page = browser.new_page()
    page.set_content(FORM)
    for js in RUN_SCRIPTS:
        page.add_script_tag(path=os.path.join(EXT_DIR, js))
    page.add_script_tag(content=chrome_stub.replace("PROFILE_JSON", json.dumps(PROFILE)))
    if patch:
        page.evaluate(patch)
    # run.js is an IIFE: adding it is what starts the fill.
    page.add_script_tag(path=os.path.join(EXT_DIR, "run.js"))
    return page


def test_a_dead_service_worker_does_not_cost_the_fill(browser):
    """Each of these messages is fire-and-forget, so a rejection from one
    went nowhere and surfaced as an unhandled rejection on the applicant's
    job-site tab -- and the awaited ones stopped the run where they stood.
    """
    page = _run_page(
        browser,
        DEAD_WORKER,
        patch="""() => {
            window.__rejections = [];
            addEventListener("unhandledrejection",
                             (e) => window.__rejections.push(String(e.reason)));
        }""",
    )
    try:
        page.wait_for_function("() => document.getElementById('a').value !== ''", timeout=5000)
        assert page.evaluate("() => document.getElementById('b').value") == PROFILE["email"]
        # The panel is the applicant's report on what just happened, and it
        # is drawn after several of those messages are sent.
        page.wait_for_selector("#ja-autofill-panel", state="attached", timeout=5000)
        # The last line the panel writes, so the sends that come after the
        # fill -- the misses, the application row -- have all been made.
        page.wait_for_function(
            """() => (document.getElementById('ja-autofill-panel')
                        ?.shadowRoot?.textContent || '').includes('Nothing submitted')""",
            timeout=5000,
        )
        page.wait_for_timeout(500)
        assert page.evaluate("() => window.__rejections") == []
    finally:
        page.close()


def test_a_failure_anywhere_in_the_run_says_so_on_the_page(browser):
    """Silence is the worst outcome: a run that throws used to leave the
    page untouched and unmarked, which reads as an extension that did
    nothing rather than one that broke -- and the next move after that is
    submitting a form believed to be filled.
    """
    page = _run_page(
        browser,
        DEAD_WORKER,
        patch="""() => {
            window.extractFields = () => { throw new Error("page went away"); };
        }""",
    )
    try:
        page.wait_for_selector("#ja-autofill-banner", timeout=5000)
        text = page.inner_text("#ja-autofill-banner")
    finally:
        page.close()

    assert "stopped early" in text.lower()
    assert "page went away" in text
    # It has to be clear the form is not ready to send.
    assert "nothing was submitted" in text.lower()


def test_a_profile_that_was_never_set_up_still_says_what_to_do(browser):
    """The first run on a fresh install goes through the same messaging
    path, and the banner is the only instruction the applicant gets.
    """
    page = _run_page(
        browser,
        """window.chrome = {
             storage: { local: { get: async () => ({}) } },
             runtime: { sendMessage: async () => { throw new Error("no worker"); } },
           };""",
    )
    try:
        page.wait_for_selector("#ja-autofill-banner", timeout=5000)
        text = page.inner_text("#ja-autofill-banner")
    finally:
        page.close()

    assert "Set up your profile first" in text
