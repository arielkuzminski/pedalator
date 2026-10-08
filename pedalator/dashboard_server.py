"""The dashboard: http://127.0.0.1:8765 (this PC only). Live values, riding modes, a manual resistance slider, and the
Controls page (profiles: Click buttons, keys, options — see profiles.py).

Because it is a web page on localhost, any web page you open could try to talk to it. So every request must carry
this server's own address in its ``Host`` header (defeats DNS rebinding) and every POST must be JSON (a page on
another site cannot send that without our permission, and we give none).
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import profiles
from .paths import WEB_DIR
from .state import PRESETS, apply_preset, clamp_grade, log, snapshot, state

MAX_BODY = 200_000


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", headers=None):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj, headers=None):
        self._send(code, json.dumps(obj), headers=headers)

    @property
    def route(self) -> str:
        """The path without the query string (``/?lang=pl`` is still the dashboard)."""
        return urlparse(self.path).path

    @property
    def query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _allowed(self, post: bool) -> bool:
        port = self.server.server_address[1]
        if self.headers.get("Host", "") not in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
            self._send(403, "forbidden host", "text/plain")
            return False
        if post and not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            self._send(415, "send application/json", "text/plain")
            return False
        return True

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        if not self._allowed(post=False):
            return
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
        elif self.route == "/profile":
            self._json(200, self._profile_view())
        elif self.route == "/profiles":
            self._json(200, {"profiles": profiles.list_profiles(), "active": state.get("profile_id")})
        elif self.route == "/profile/export":
            pid = self.query.get("id")
            try:
                profile = profiles.load(pid) if pid else profiles.current(state["target"])
            except (KeyError, ValueError) as e:
                return self._json(404, {"error": str(e)})
            self._send(200, profiles.export_text(profile), "application/json",
                       {"Content-Disposition": f'attachment; filename="pedalator-{profile["id"]}.json"'})
        else:
            self._send(404, "not found", "text/plain")

    def _profile_view(self) -> dict:
        profile = profiles.current(state["target"])
        try:
            dirty = profiles.load(profile["id"]) != profile
        except (KeyError, ValueError):
            dirty = True
        view = profiles.describe(profile)
        view.update(dirty=dirty, saved_by_you=profile["id"] in profiles.user_ids(),
                    builtin=profile["id"] in profiles.builtin_ids(), bridge_target=state["target"])
        return view

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        if not self._allowed(post=True):
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                return self._json(413, {"error": "too large"})
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.route.startswith("/profile"):
                return self._profile_post(body)
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
            self._json(400, {"error": str(e)})

    def _profile_post(self, body: dict) -> None:
        route = self.route
        target = state["target"]
        if route == "/profile/apply":                      # live: every edit of the Controls page lands here
            profile, errors = profiles.validate(body.get("profile"), fill_keys=True)
            if not errors and profile["target"] != target:
                errors = [f"this profile is for the '{profile['target']}' target, but Pedalator runs the '{target}' target"]
            if errors:
                return self._json(400, {"errors": errors})
            profiles.apply(profile)
            return self._json(200, {"ok": True, "profile": profile})
        if route == "/profile/select":
            try:
                profile = profiles.load(str(body.get("id")))
            except (KeyError, ValueError) as e:
                return self._json(404, {"errors": [f"no such profile: {e}"]})
            if profile["target"] != target:
                return self._json(400, {"errors": [f"'{profile['name']}' is for the '{profile['target']}' target; "
                                                   f"Pedalator runs the '{target}' target"]})
            profiles.apply(profile)
            log(f"profile: {profile['name']}")
            return self._json(200, {"ok": True})
        if route == "/profile/save":                       # save the active profile (as a new one when a name is given)
            profile = dict(profiles.current(target))
            if body.get("name"):
                profile["name"] = str(body["name"]).strip()[:60]
                profile["id"] = body.get("id") or profiles.slugify(profile["name"])
            profile, errors = profiles.validate(profile, fill_keys=True)
            if errors:
                return self._json(400, {"errors": errors})
            profiles.save_user(profile)
            profiles.apply(profile)
            log(f"profile saved: {profile['name']} ({profile['id']})")
            return self._json(200, {"ok": True, "id": profile["id"]})
        if route == "/profile/delete":
            pid = str(body.get("id"))
            if not profiles.delete_user(pid):
                return self._json(404, {"errors": ["only profiles you saved can be deleted"]})
            if state.get("profile_id") == pid:               # fall back to the built-in of that id, or the default
                try:
                    profiles.apply(profiles.load(pid))
                except (KeyError, ValueError):
                    state["profile"], state["profile_id"] = None, None
            return self._json(200, {"ok": True})
        if route == "/profile/import":
            profile, errors = profiles.import_text(str(body.get("text", "")), body.get("id"), bool(body.get("overwrite")))
            if errors:
                return self._json(400, {"errors": errors})
            log(f"profile imported: {profile['name']} ({profile['id']})")
            return self._json(200, {"ok": True, "id": profile["id"], "target": profile["target"]})
        self._send(404, "{}")


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
