"""A small local web UI, so the tool can be driven without the terminal.

Runs on 127.0.0.1 only -- the server is never reachable from the network,
and nothing is ever sent anywhere. The browser it drives for applications is
a separate window from the one showing this UI.
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from typing import Any, Callable

from .browser import goto_and_settle, launch_browser, launch_error_message
from .field_aliases import OPTION_CHOICES, SELF_ID_CHOICES
from .filler import fill_form
from .profile import ProfileError, load_profile, profile_to_dict, save_profile
from .settings import launch_opts, load_settings, save_settings
from .webui_page import PAGE_HTML


class Session:
    """Owns the Playwright browser on a dedicated thread.

    Playwright's sync API is bound to the thread that created it, so every
    browser action happens on this one worker thread; HTTP handlers only ever
    push commands onto its queue and read the state snapshot.
    """

    def __init__(self, profile_path: str, launch_opts: dict[str, Any] | Callable[[], dict[str, Any]]) -> None:
        self.profile_path = profile_path
        # A callable is re-read at launch time, so a settings change in the
        # UI applies to the next application without restarting the server.
        self._launch_opts = launch_opts
        self._queue: Queue = Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = {"status": "idle", "message": "", "report": None, "url": ""}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            self._state.update(kwargs)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def open_url(self, url: str) -> None:
        if self.is_running():
            self._queue.put(("goto", url))
            return
        self._set(status="starting", message="Launching browser...", report=None, url=url)
        self._thread = threading.Thread(target=self._worker, args=(url,), daemon=True)
        self._thread.start()

    def command(self, name: str) -> None:
        if self.is_running():
            self._queue.put((name, ""))

    def _worker(self, first_url: str) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._set(status="error", message="Playwright is not installed. Run: pip install -r requirements.txt")
            return

        try:
            with sync_playwright() as p:
                opts = self._launch_opts() if callable(self._launch_opts) else self._launch_opts
                try:
                    closeable, page = launch_browser(p, headless=False, **opts)
                except Exception as exc:  # noqa: BLE001
                    self._set(status="error", message=launch_error_message(exc))
                    return

                try:
                    self._navigate_and_fill(page, first_url)
                    while True:
                        cmd, arg = self._queue.get()
                        if cmd == "close":
                            break
                        if cmd == "goto":
                            self._navigate_and_fill(page, arg)
                        elif cmd == "refill":
                            self._fill(page)
                finally:
                    closeable.close()
        except Exception as exc:  # noqa: BLE001 - surface, never crash the server
            self._set(status="error", message=str(exc))
            return

        self._set(status="idle", message="Browser closed.", report=None, url="")

    def _navigate_and_fill(self, page: Any, url: str) -> None:
        self._set(status="working", message=f"Opening {url}", url=url)
        try:
            goto_and_settle(page, url, 45000)
        except Exception as exc:  # noqa: BLE001
            self._set(status="open", message=f"Could not load that page: {exc}", report=None)
            return
        self._fill(page)

    def _fill(self, page: Any) -> None:
        self._set(status="working", message="Filling fields...")
        try:
            profile = load_profile(self.profile_path)
        except ProfileError as exc:
            self._set(status="open", message=f"Profile error: {exc}")
            return
        try:
            report = fill_form(page, profile)
        except Exception as exc:  # noqa: BLE001
            self._set(status="open", message=f"Could not fill this page: {exc}")
            return
        self._set(status="open", message="", report=_report_json(report))


def _report_json(report: Any) -> dict[str, Any]:
    return {
        "platform": report.platform,
        "results": [asdict(r) for r in report.results],
    }


def _documents(root: str) -> list[str]:
    folder = os.path.join(root, "documents")
    if not os.path.isdir(folder):
        return []
    return sorted(
        f"documents/{name}" for name in os.listdir(folder)
        if not name.startswith(".") and os.path.isfile(os.path.join(folder, name))
    )


def make_handler(session: Session, profile_path: str, root: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict[str, Any], code: int = 200) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802 - required name
            if self.path == "/":
                self._send(200, PAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._json(session.snapshot())
            elif self.path == "/api/profile":
                try:
                    data = profile_to_dict(load_profile(profile_path))
                    self._json({"ok": True, "profile": data, "documents": _documents(root),
                                "self_id_choices": SELF_ID_CHOICES, "option_choices": OPTION_CHOICES})
                except ProfileError as exc:
                    self._json({"ok": False, "error": str(exc), "documents": _documents(root),
                                "self_id_choices": SELF_ID_CHOICES, "option_choices": OPTION_CHOICES})
            elif self.path == "/api/settings":
                self._json({"ok": True, "settings": load_settings(root)})
            else:
                self._send(404, b"Not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802 - required name
            try:
                body = self._body()
            except json.JSONDecodeError:
                self._json({"ok": False, "error": "Malformed request."}, 400)
                return

            if self.path == "/api/profile":
                try:
                    save_profile(profile_path, body.get("profile", {}))
                    self._json({"ok": True})
                except (ProfileError, ValueError) as exc:
                    self._json({"ok": False, "error": str(exc)})
            elif self.path == "/api/settings":
                self._json({"ok": True, "settings": save_settings(root, body.get("settings", {}))})
            elif self.path == "/api/open":
                url = (body.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    self._json({"ok": False, "error": "Enter a full job application URL starting with https://"})
                    return
                session.open_url(url)
                self._json({"ok": True})
            elif self.path in ("/api/refill", "/api/close"):
                session.command("refill" if self.path.endswith("refill") else "close")
                self._json({"ok": True})
            else:
                self._send(404, b"Not found", "text/plain")

    return Handler


def serve(profile_path: str, root: str, port: int, browser_path: str = "",
          open_browser: bool = True) -> int:
    # Re-read on each launch so a settings change in the UI takes effect on
    # the next application rather than needing a restart.
    session = Session(profile_path, lambda: launch_opts(root, browser_path))
    handler = make_handler(session, profile_path, root)

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        print(f"Could not start on port {port}: {exc}\nTry a different one with --port.")
        return 1

    url = f"http://127.0.0.1:{port}"
    print(f"\n  Job Application Autofill is running.\n\n  Open:  {url}\n\n  Press Ctrl+C here to stop it.\n")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0
