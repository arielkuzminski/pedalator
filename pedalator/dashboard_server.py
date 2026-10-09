"""The dashboard: http://127.0.0.1:2137 (this PC only). Live values, riding modes, a manual resistance slider, and the
Controls page (profiles: Click buttons, keys, options — see profiles.py).

Because it is a web page on localhost, any web page you open could try to talk to it. So every request must carry
this server's own address in its ``Host`` header (defeats DNS rebinding) and every POST must be JSON (a page on
another site cannot send that without our permission, and we give none).
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import diag, newgame, profiles
from .paths import WEB_DIR, find_openmw_log, find_openmw_state, openmw_user_dir
from .session import SessionError, runtime
from .state import PRESETS, apply_preset, clamp_grade, log, snapshot, state, throttle_for
from .targets import udp

MAX_BODY = 200_000


def live_snapshot() -> dict:
    """The snapshot plus what the Game page's test panel shows: the gas, the turning and the UDP line being sent."""
    s = snapshot()
    fresh = s["age_packet"] is not None and s["age_packet"] < 2.0 or state["simulate"]
    power = state["power"] if fresh else 0
    raw = set(state["raw"]) if time.time() - state["t_buttons"] < 1.5 else set()
    sent = json.loads(udp.packet(0, power, raw))
    s["gas"] = round(throttle_for(power), 3)
    s["turn"], s["look"], s["packet"] = sent["turn"], sent["look"], sent
    return s


def open_folder(path) -> None:
    if sys.platform == "win32":
        os.startfile(path)                                      # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


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
            self._send(200, json.dumps(live_snapshot()))
        elif self.route == "/events":                      # Server-Sent Events: a snapshot ten times a second
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(f"data: {json.dumps(live_snapshot())}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.1)
            except OSError:
                pass
        elif self.route == "/profile":
            self._json(200, self._profile_view())
        elif self.route == "/profiles":
            self._json(200, {"profiles": profiles.list_profiles(), "active": state.get("profile_id")})
        elif self.route == "/session":
            self._json(200, {"session": state["session"], "available": runtime.loop is not None})
        elif self.route == "/install/openmw":              # what installing the OpenMW mod would change
            self._json(200, self._install_openmw(dry_run=True))
        elif self.route == "/session/options":
            self._json(200, self._session_options())
        elif self.route == "/diag":                         # the flow check: state and, when done, the report
            self._json(200, diag.probe.view())
        elif self.route == "/session/signal":              # a scan: how strong are the trainer and the Click here?
            self._json(*self._signal())
        elif self.route == "/games":
            self._json(200, {"games": newgame.list_games()})
        elif self.route == "/games/file":
            path = newgame.game_file_path(self.query.get("id", ""), self.query.get("name", ""))
            if path is None:
                return self._json(404, {"error": "no such file"})
            self._json(200, {"text": path.read_text(encoding="utf-8")})
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

    def _session_options(self) -> dict:
        mod, log_file = find_openmw_state(), find_openmw_log()
        base = runtime.base
        return {"openmw": {"found": bool(base.openmw_state or mod), "state": str(base.openmw_state or mod or ""),
                           "cfg": str(openmw_user_dir() or "")},
                "bluetooth": importlib.util.find_spec("bleak") is not None,
                "defaults": {"udp_out": base.udp_out, "keys": base.keys}, "openmw_log": str(log_file or "")}

    def _diag_start(self, body: dict) -> None:
        """Record the flow check (diag.py) for 5-120 s while a ride runs."""
        if runtime.loop is None:
            return self._json(503, {"error": "the driver is not running in this process"})
        if state["session"]["status"] != "running":
            return self._json(409, {"error": "start a ride first: the flow check measures a ride in progress"})
        try:
            seconds = float(body.get("seconds", 30))
        except (TypeError, ValueError):
            return self._json(400, {"error": "seconds must be a number"})
        if not 5 <= seconds <= 120:
            return self._json(400, {"error": "seconds must be between 5 and 120"})

        async def go():
            diag.start(seconds)
        try:
            runtime.call(go())
        except RuntimeError as e:
            return self._json(409, {"error": str(e)})
        self._json(200, diag.probe.view())

    def _signal(self) -> tuple[int, dict]:
        if self._session_active:
            return 409, {"error": "stop the ride first: a scan would disturb the connections"}
        if runtime.loop is None:
            return 503, {"error": "the driver is not running in this process"}
        from .click import check_range
        try:
            return 200, runtime.call(check_range(), timeout=20)
        except Exception as e:                                  # no adapter, Bluetooth switched off...
            return 200, {"trainer": None, "click": None, "error": f"{type(e).__name__}: {e}"}

    def _install_openmw(self, dry_run: bool) -> dict:
        """The same as ``pedalator install openmw`` (a backup of openmw.cfg is made); only the places it finds itself."""
        from .install import install_openmw
        lines: list[str] = []
        code = install_openmw(None, None, dry_run=dry_run, say=lines.append)
        return {"ok": code == 0, "lines": lines, "dry_run": dry_run}

    @property
    def _session_active(self) -> bool:
        return state["session"]["status"] != "idle"

    def _session_post(self, body: dict) -> None:
        if runtime.loop is None:
            return self._json(503, {"errors": ["the driver is not running in this process"]})
        try:
            if self.route == "/session/stop":
                runtime.call(runtime.stop())
                return self._json(200, {"ok": True})
            if self.route != "/session/start":
                return self._json(404, {"error": "not found"})
            trainer, click = body.get("trainer", "pc"), body.get("click", "auto")
            pid = str(body.get("profile", ""))
            if trainer not in ("simulate", "pc", "phone") or click not in ("auto", "pc", "phone", "off"):
                raise SessionError("choose a trainer (simulate, pc, phone) and a Click (auto, pc, phone, off)")
            if not profiles.ID_RE.match(pid):
                raise SessionError("choose a game")
            cfg = dataclasses.replace(
                runtime.base, profile=pid, target=None, keyset=None, remote=False, simulate=trainer == "simulate",
                trainer="pc" if trainer == "simulate" else trainer, click=click, keys=bool(body.get("keys")),
                udp_out=str(body.get("udp_out") or runtime.base.udp_out))
            runtime.call(runtime.start(cfg))
            self._json(200, {"ok": True, "session": state["session"]})
        except SessionError as e:
            self._json(400, {"errors": e.errors})

    def _profile_view(self) -> dict:
        profile = profiles.current(state["target"])
        try:
            dirty = profiles.load(profile["id"]) != profile
        except (KeyError, ValueError):
            dirty = True
        view = profiles.describe(profile)
        view.update(dirty=dirty, saved_by_you=profile["id"] in profiles.user_ids(),
                    builtin=profile["id"] in profiles.builtin_ids(), bridge_target=state["target"],
                    session_active=self._session_active)
        return view

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        if not self._allowed(post=True):
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                left = min(length, 4_000_000)                              # read what is being sent, or the client
                while left > 0:                                              # sees a reset instead of our answer
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                self.close_connection = True
                return self._json(413, {"error": "too large"})
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.route.startswith("/profile"):
                return self._profile_post(body)
            if self.route.startswith("/session"):
                return self._session_post(body)
            if self.route == "/diag/start":
                return self._diag_start(body)
            if self.route == "/install/openmw":
                if self._session_active:
                    return self._json(400, {"errors": ["stop the ride before installing"]})
                result = self._install_openmw(dry_run=False)
                log("OpenMW mod installed" if result["ok"] else "OpenMW mod: installation failed")
                return self._json(200 if result["ok"] else 400, result)
            if self.route in ("/newgame", "/games/file", "/games/open"):
                return self._game_post(body)
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
                if self._session_active:
                    errors = [f"this profile is for the '{profile['target']}' target, but Pedalator runs the '{target}' target"]
                else:
                    state["target"] = profile["target"]
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
                if self._session_active:
                    return self._json(400, {"errors": [f"'{profile['name']}' is for the '{profile['target']}' target; "
                                                       f"Pedalator runs the '{target}' target"]})
                state["target"] = profile["target"]
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


    def _game_post(self, body: dict) -> None:
        if self.route == "/newgame":
            name = str(body.get("name", "")).strip()[:60]
            how = body.get("how")
            keys = body.get("keys") or {}
            if not name:
                return self._json(400, {"errors": ["give the game a name"]})
            if how not in newgame.HOW:
                return self._json(400, {"errors": [f"'how' must be one of: {', '.join(newgame.HOW)}"]})
            if not isinstance(keys, dict) or not all(isinstance(v, str) for v in keys.values()):
                return self._json(400, {"errors": ["keys must map a slot to a key name"]})
            out = newgame.games_dir() / profiles.slugify(name)
            profile, files, errors = newgame.create(name, how, keys, bool(body.get("slope")), out,
                                                    bool(body.get("overwrite")))
            if errors:
                return self._json(400, {"errors": errors})
            log(f"new game: {profile['name']} ({profile['id']})")
            return self._json(200, {"ok": True, "id": profile["id"], "target": profile["target"],
                                    "files": [f.name for f in files], "folder": str(out),
                                    "usable_now": profile["target"] == state["target"] or not self._session_active})
        gid = str(body.get("id", ""))
        if self.route == "/games/open":
            if not newgame.game_files(gid):
                return self._json(404, {"error": "no such game"})
            open_folder(newgame.games_dir() / gid)
            return self._json(200, {"ok": True})
        path = newgame.game_file_path(gid, str(body.get("name", "")))     # /games/file: save an edited file
        text = body.get("text")
        if path is None or not isinstance(text, str):
            return self._json(404, {"errors": ["no such file"]})
        if path.suffix == ".json":                                         # the game's profile: it must stay valid
            try:
                data = json.loads(text)
            except ValueError as e:
                return self._json(400, {"errors": [f"not valid JSON: {e}"]})
            profile, errors = profiles.validate(data, fill_keys=True)
            if not errors and profile["id"] != gid:
                errors = [f"the id must stay '{gid}'"]
            if errors:
                return self._json(400, {"errors": errors})
            text = profiles.export_text(profile)
            profiles.save_user(profile)
            if state.get("profile_id") == gid and (profile["target"] == state["target"] or not self._session_active):
                state["target"] = profile["target"]
                profiles.apply(profile)
        path.write_text(text, encoding="utf-8")
        log(f"saved {gid}/{path.name}")
        self._json(200, {"ok": True})


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
