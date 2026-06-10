"""Local web server for the simulator dashboard.

Serves the embedded single-page UI plus a small JSON API, and drives the
controller loop on a background thread. Binds to 127.0.0.1: the dashboard
is for your eyes, not the network's.
"""

from __future__ import annotations

import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .controller import BaseController, LiveController, ReplayController
from .dashboard_html import HTML


def _make_handler(controller: BaseController):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence per-request stderr spam
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, HTML.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                body = json.dumps(controller.state(), default=str).encode()
                self._send(200, body, "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path == "/api/control":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                controller.control(payload.get("action", ""), payload.get("value"))
                self._send(200, b'{"ok":true}', "application/json")
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def _drive(controller: BaseController, live_poll_seconds: float) -> None:
    if isinstance(controller, ReplayController):
        while not controller.finished:
            t0 = time.time()
            n = max(1, int(controller.speed * 0.2))
            for _ in range(n):
                if not controller.step():
                    break
            elapsed = time.time() - t0
            time.sleep(max(0.0, n / max(controller.speed, 0.2) - elapsed))
    else:
        while True:
            controller.step()
            time.sleep(live_poll_seconds)


def serve(controller: BaseController, port: int = 8765,
          live_poll_seconds: float = 60.0, open_browser: bool = True,
          block: bool = True) -> ThreadingHTTPServer:
    threading.Thread(target=_drive, args=(controller, live_poll_seconds),
                     daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(controller))
    url = f"http://127.0.0.1:{port}"
    print(f"ctabot simulator running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    if block:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    else:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def build(mode: str, preset: str, capital: float, start: str | None = None,
          end: str | None = None, state_path: str | None = None) -> BaseController:
    """Construct feed + account + controller for the requested mode."""
    from .account import PaperAccount
    from .datafeed import COMMISSION_USD, ReplayFeed, YahooFeed

    if mode == "replay":
        feed = ReplayFeed(start=start or "1982-01-01", end=end)
        account = PaperAccount(capital, feed.specs(), COMMISSION_USD)
        return ReplayController(feed, account, preset)
    feed = YahooFeed()
    specs = feed.specs()
    if state_path:
        from pathlib import Path
        if Path(state_path).exists():
            account = PaperAccount.load(state_path, specs, COMMISSION_USD)
            print(f"resumed paper account from {state_path}")
            return LiveController(feed, account, preset)
    account = PaperAccount(capital, specs, COMMISSION_USD)
    return LiveController(feed, account, preset)
