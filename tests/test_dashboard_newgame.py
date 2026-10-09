"""The Game page's API: making a game, editing its files, and the live values of the test panel."""
import http.client
import json

import pytest

from pedalator import dashboard_server, keys, profiles
from pedalator.dashboard_server import start_dashboard
from pedalator.state import state

from .conftest import free_port


@pytest.fixture()
def dash(tmp_path):
    profiles.set_user_dir(tmp_path / "profiles")
    state["target"] = "udp"
    state["session"] = {"status": "running"}   # a bridge is riding: the target is fixed
    port = free_port()
    srv = start_dashboard(port)

    class Client:
        def request(self, method, path, body=None, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
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

    client = Client()
    client.port = port
    yield client
    srv.shutdown()
    srv.server_close()
    profiles.set_user_dir(None)
    keys.apply_keys({"throttle": "Numpad8", "brake": "Numpad2", "left": "Numpad4", "right": "Numpad6", "use": "KeyE"})


def test_a_udp_game_gets_its_profile_and_files(dash, tmp_path):
    code, r = dash.post("/newgame", {"name": "My Game", "how": "udp", "slope": True})
    assert code == 200 and r["id"] == "my-game" and r["usable_now"] is True
    assert set(r["files"]) == {"my-game.json", "listen.py", "mod_sketch.lua", "README.md"}
    assert (tmp_path / "games" / "my-game" / "listen.py").is_file()
    assert "my-game" in profiles.user_ids()
    assert "report_slope" in (tmp_path / "games" / "my-game" / "mod_sketch.lua").read_text(encoding="utf-8")


def test_a_keys_game_with_its_own_keys(dash):
    code, r = dash.post("/newgame", {"name": "Bikes", "how": "keys", "keys": {"throttle": "ArrowUp"}})
    assert code == 200 and r["files"] == ["bikes.json", "README.md"] and r["usable_now"] is False
    assert profiles.load("bikes")["keys"]["throttle"] == "ArrowUp"


@pytest.mark.parametrize("body, text", [
    ({"name": "", "how": "keys"}, "name"),
    ({"name": "X", "how": "carrier-pigeon"}, "how"),
    ({"name": "X", "how": "keys", "keys": {"throttle": "NotAKey"}}, "key"),
    ({"name": "X", "how": "keys", "keys": ["a"]}, "keys"),
])
def test_bad_input_is_refused_and_nothing_is_written(dash, tmp_path, body, text):
    code, r = dash.post("/newgame", body)
    assert code == 400 and text in " ".join(r["errors"]).lower()
    assert not (tmp_path / "games").exists() and profiles.user_ids() == []


def test_an_existing_game_is_not_replaced_unless_asked(dash):
    assert dash.post("/newgame", {"name": "Dup", "how": "keys"})[0] == 200
    code, r = dash.post("/newgame", {"name": "Dup", "how": "keys"})
    assert code == 400 and "already exists" in r["errors"][0]
    assert dash.post("/newgame", {"name": "Dup", "how": "keys", "overwrite": True})[0] == 200


def test_the_editor_lists_reads_and_saves_the_generated_files(dash, tmp_path):
    dash.post("/newgame", {"name": "Edit Me", "how": "udp"})
    code, r = dash.get("/games")
    assert r["games"] == [{"id": "edit-me", "files": ["edit-me.json", "README.md", "listen.py", "mod_sketch.lua"]}]
    code, r = dash.get("/games/file?id=edit-me&name=listen.py")
    assert code == 200 and "27200" in r["text"]
    assert dash.post("/games/file", {"id": "edit-me", "name": "listen.py", "text": "print('hi')\n"})[0] == 200
    assert (tmp_path / "games" / "edit-me" / "listen.py").read_text(encoding="utf-8") == "print('hi')\n"


@pytest.mark.parametrize("gid, name", [("edit-me", "../../profiles/edit-me.json"), ("edit-me", "evil.py"),
                                        ("..", "listen.py"), ("edit-me", "a%5Cb"), ("nope", "listen.py")])
def test_the_editor_only_opens_the_generated_files(dash, gid, name):
    dash.post("/newgame", {"name": "Edit Me", "how": "udp"})
    assert dash.get(f"/games/file?id={gid}&name={name}")[0] == 404
    assert dash.post("/games/file", {"id": gid, "name": name, "text": "x"})[0] == 404


def test_the_games_profile_must_stay_valid_and_saving_it_updates_your_profile(dash):
    dash.post("/newgame", {"name": "Prof", "how": "udp"})
    text = dash.get("/games/file?id=prof&name=prof.json")[1]["text"]
    assert dash.post("/games/file", {"id": "prof", "name": "prof.json", "text": "{oops"})[0] == 400
    bad = json.loads(text)
    bad["id"] = "other"
    assert dash.post("/games/file", {"id": "prof", "name": "prof.json", "text": json.dumps(bad)})[0] == 400
    good = json.loads(text)
    good["ride"]["gain"] = 3.0
    assert dash.post("/games/file", {"id": "prof", "name": "prof.json", "text": json.dumps(good)})[0] == 200
    assert profiles.load("prof")["ride"]["gain"] == 3.0


def test_open_folder_only_for_a_known_game(dash, monkeypatch):
    opened = []
    monkeypatch.setattr(dashboard_server, "open_folder", opened.append)
    dash.post("/newgame", {"name": "Open", "how": "keys"})
    assert dash.post("/games/open", {"id": "../x"})[0] == 404 and opened == []
    assert dash.post("/games/open", {"id": "open"})[0] == 200 and opened[0].name == "open"


def test_the_test_panel_values(dash):
    state.update(power=150, simulate=True, gain=2.0, pmax=250, raw=["LEFT", "DOWN"], t_buttons=__import__("time").time())
    code, body = dash.get("/state")
    assert code == 200 and body["gas"] == pytest.approx(1.0)
    assert body["turn"] == -1 and body["look"] == 1 and body["packet"]["buttons"] == ["DOWN", "LEFT"]


def test_other_sites_cannot_use_it(dash):
    assert dash.post("/newgame", {"name": "X", "how": "keys"}, {"Host": "evil.example"})[0] == 403
    assert dash.request("POST", "/newgame", None, {"Content-Type": "text/plain"})[0] == 415


def test_the_live_stream_carries_the_test_panel_values_too(dash):
    c = http.client.HTTPConnection("127.0.0.1", dash.port, timeout=5)
    c.request("GET", "/events")
    line = c.getresponse().readline().decode()
    assert line.startswith("data: ") and {"gas", "turn", "look", "packet"} <= set(json.loads(line[6:]))
    c.close()
