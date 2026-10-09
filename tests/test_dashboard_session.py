"""Starting and stopping a ride from the dashboard (the Start page's API)."""
import asyncio
import http.client
import json
import threading
import time

import pytest

from pedalator import keys, profiles
from pedalator.dashboard_server import start_dashboard
from pedalator.session import SessionConfig, runtime
from pedalator.state import state

from .conftest import free_port


@pytest.fixture()
def dash(tmp_path):
    profiles.set_user_dir(tmp_path / "profiles")
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    async def attach():
        runtime.attach(loop, SessionConfig(game_port=free_port(), udp_out=f"127.0.0.1:{free_port()}"))
    asyncio.run_coroutine_threadsafe(attach(), loop).result(5)
    port = free_port()
    srv = start_dashboard(port)

    class Client:
        def request(self, method, path, body=None, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            h = {"Content-Type": "application/json", **(headers or {})} if body is not None else (headers or {})
            c.request(method, path, body=None if body is None else json.dumps(body), headers=h)
            r = c.getresponse()
            data = r.read()
            try:
                data = json.loads(data)
            except ValueError:
                pass
            return r.status, data

        def get(self, path):
            return self.request("GET", path)

        def post(self, path, body, headers=None):
            return self.request("POST", path, body, headers)

    yield Client()
    asyncio.run_coroutine_threadsafe(runtime.stop(), loop).result(10)
    srv.shutdown()
    srv.server_close()
    loop.call_soon_threadsafe(loop.stop)
    runtime.loop, runtime.base = None, SessionConfig()
    profiles.set_user_dir(None)
    keys.apply_keys({"throttle": "Numpad8", "brake": "Numpad2", "left": "Numpad4", "right": "Numpad6", "use": "KeyE"})


def test_a_game_is_started_and_stopped_from_the_page(dash):
    assert dash.get("/session")[1]["session"]["status"] == "idle"
    code, r = dash.post("/session/start", {"profile": "generic-udp", "trainer": "simulate"})
    assert code == 200 and r["session"]["status"] == "running" and r["session"]["target"] == "udp"
    time.sleep(0.5)
    live = dash.get("/state")[1]
    assert live["session"]["profile_id"] == "generic-udp" and live["connected"] and live["power"] > 0
    assert dash.post("/session/stop", {})[0] == 200
    live = dash.get("/state")[1]
    assert live["session"]["status"] == "idle" and live["connected"] is False and live["elapsed"] == 0


def test_another_game_can_be_started_after_stopping(dash):
    dash.post("/session/start", {"profile": "generic-udp", "trainer": "simulate"})
    assert dash.post("/session/start", {"profile": "omsi", "trainer": "simulate"})[0] == 400   # one at a time
    dash.post("/session/stop", {})
    code, r = dash.post("/session/start", {"profile": "omsi", "trainer": "simulate"})
    assert code == 200 and r["session"]["target"] == "keys"


@pytest.mark.parametrize("body, text", [
    ({"trainer": "simulate"}, "choose a game"),
    ({"profile": "../secret", "trainer": "simulate"}, "choose a game"),
    ({"profile": "nope", "trainer": "simulate"}, "no profile"),
    ({"profile": "generic-udp", "trainer": "carrier-pigeon"}, "choose a trainer"),
    ({"profile": "generic-udp", "trainer": "simulate", "udp_out": "nonsense"}, "HOST:PORT"),
])
def test_a_bad_start_says_why_and_leaves_the_page_idle(dash, body, text):
    code, r = dash.post("/session/start", body)
    assert code == 400 and text in " ".join(r["errors"])
    assert dash.get("/session")[1]["session"]["status"] == "idle"


def test_without_a_session_any_game_can_be_chosen_and_tuned(dash):
    state["target"] = "udp"
    assert dash.post("/profile/select", {"id": "morrowind"})[0] == 200
    assert state["target"] == "openmw" and dash.get("/profile")[1]["session_active"] is False


def test_the_target_is_fixed_while_riding(dash):
    dash.post("/session/start", {"profile": "generic-udp", "trainer": "simulate"})
    code, r = dash.post("/profile/select", {"id": "morrowind"})
    assert code == 400 and "target" in r["errors"][0]


def test_the_page_learns_what_this_computer_offers(dash):
    r = dash.get("/session/options")[1]
    assert {"openmw", "bluetooth", "defaults"} <= set(r) and r["defaults"]["udp_out"].startswith("127.0.0.1:")


def test_without_the_driver_there_is_nothing_to_start(dash):
    runtime.loop = None
    code, r = dash.post("/session/start", {"profile": "generic-udp", "trainer": "simulate"})
    assert code == 503
    assert dash.request("POST", "/session/stop", {}, {"Host": "evil.example"})[0] == 403
    assert dash.request("POST", "/session/stop", None, {"Content-Type": "text/plain"})[0] == 415


def test_the_openmw_mod_can_be_installed_from_the_page(dash, tmp_path, monkeypatch):
    user = tmp_path / "openmw"
    user.mkdir()
    (user / "openmw.cfg").write_text('data="C:/Morrowind"\r\ncontent=Morrowind.esm\r\n', encoding="utf-8", newline="")
    monkeypatch.setattr("pedalator.install.openmw_user_dir", lambda: user)
    monkeypatch.setattr("pedalator.dashboard_server.openmw_user_dir", lambda: user)
    monkeypatch.setattr("pedalator.dashboard_server.find_openmw_state", lambda: next(user.glob("mods/*/pedalator/state.txt"), None))

    opts = dash.get("/session/options")[1]["openmw"]
    assert opts["found"] is False and opts["cfg"] == str(user)
    preview = dash.get("/install/openmw")[1]
    assert preview["ok"] and any("added content=Pedalator.omwscripts" in line for line in preview["lines"])
    assert "Pedalator" not in (user / "openmw.cfg").read_text()                     # a preview writes nothing

    code, r = dash.post("/install/openmw", {})
    assert code == 200 and r["ok"]
    cfg = (user / "openmw.cfg").read_bytes().decode()
    assert "content=Pedalator.omwscripts" in cfg and "\r\n" in cfg and list(user.glob("openmw.cfg.bak-pedalator-*"))
    assert dash.get("/session/options")[1]["openmw"]["found"] is True


def test_installing_without_openmw_says_what_is_missing(dash, tmp_path, monkeypatch):
    monkeypatch.setattr("pedalator.install.openmw_user_dir", lambda: None)
    code, r = dash.post("/install/openmw", {})
    assert code == 400 and "openmw.cfg" in " ".join(r["lines"])


def test_installing_is_refused_while_riding(dash):
    dash.post("/session/start", {"profile": "generic-udp", "trainer": "simulate"})
    assert dash.post("/install/openmw", {})[0] == 400


def test_the_signal_check_scans_when_idle_and_is_refused_during_a_ride(dash, monkeypatch):
    from pedalator import click

    async def fake_range(timeout=6.0):
        return {"trainer": {"name": "KICKR", "rssi": -61}, "click": None}
    monkeypatch.setattr(click, "check_range", fake_range)
    assert dash.get("/session/signal") == (200, {"trainer": {"name": "KICKR", "rssi": -61}, "click": None})
    state["session"] = {"status": "running"}
    try:
        assert dash.get("/session/signal")[0] == 409
    finally:
        state["session"] = {"status": "idle"}
