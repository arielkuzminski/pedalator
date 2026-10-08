"""The dashboard: http://127.0.0.1:8765 (this PC only). Live values, riding modes, a manual resistance slider."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .paths import WEB_DIR
from .state import PRESETS, apply_preset, clamp_grade, log, snapshot, state


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    @property
    def route(self) -> str:
        """The path without the query string (``/?lang=pl`` is still the dashboard)."""
        return self.path.split("?", 1)[0]

    def do_GET(self):
        if self.route in ("/", "/index.html"):
            try:
                self._send(200, (WEB_DIR / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(404, "dashboard.html missing", "text/plain")
        elif self.route == "/state":
            self._send(200, json.dumps(snapshot()))
        elif self.route == "/events":                      # Server-Sent Events: a snapshot ten times a second
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(f"data: {json.dumps(snapshot())}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.1)
            except OSError:
                pass
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.route == "/grade":
                state["manual_grade"] = clamp_grade(float(body["grade"]))
            elif self.route == "/mode":
                if body["mode"] not in ("game", "manual"):
                    raise ValueError("mode")
                state["mode"] = body["mode"]
                log(f"grade source: {state['mode']}")
            elif self.route == "/preset":
                apply_preset(body["name"] if body["name"] in PRESETS else "easy")
                log(f"riding mode: {state['preset']} (gain x{state['gain']}, gradient x{state['difficulty']})")
            elif self.route == "/gain":
                state["gain"] = max(0.5, min(4.0, float(body["gain"])))
                state["preset"] = "custom"
            elif self.route == "/difficulty":
                state["difficulty"] = max(0.0, min(1.0, float(body["difficulty"])))
                state["preset"] = "custom"
            elif self.route == "/ftp":
                state["ftp"] = max(50, min(600, int(body["ftp"])))
            else:
                return self._send(404, "{}")
            self._send(200, "{}")
        except Exception as e:
            self._send(400, json.dumps({"error": str(e)}))


def start_dashboard(port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer | None:
    try:
        srv = ThreadingHTTPServer((host, port), DashboardHandler)
    except OSError as e:
        log(f"dashboard NOT started (port {port}: {e})")
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"dashboard: http://{host}:{port}")
    return srv
