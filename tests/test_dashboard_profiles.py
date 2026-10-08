"""The dashboard's profile API, and that other web pages cannot use it."""
import copy
import http.client
import json

import pytest

from pedalator import keys, profiles
from pedalator.dashboard_server import start_dashboard
from pedalator.state import state

from .conftest import free_port


@pytest.fixture()
def dash(tmp_path):
    profiles.set_user_dir(tmp_path / "profiles")
    state["target"] = "openmw"
    port = free_port()
    srv = start_dashboard(port)

    class Client:
        def __init__(self):
            self.c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            self.port = port

        def get(self, path):
            self.c.request("GET", path)
            r = self.c.getresponse()
            return r.status, r.read(), dict(r.getheaders())

        def post(self, path, body, headers=None):
            h = {"Content-Type": "application/json", **(headers or {})}
            self.c.request("POST", path, body=json.dumps(body), headers=h)
            r = self.c.getresponse()
            data = r.read()
            try:
                data = json.loads(data)
            except ValueError:
                pass
            return r.status, data

    yield Client()
    srv.shutdown()
    srv.server_close()
    profiles.set_user_dir(None)
    keys.apply_keys({"throttle": "Numpad8", "brake": "Numpad2", "left": "Numpad4", "right": "Numpad6", "use": "KeyE"})


def test_the_controls_page_gets_everything_it_needs_to_draw_itself(dash):
    code, body, _ = dash.get("/profile")
    view = json.loads(body)
    assert code == 200 and view["target"] == "openmw" and view["profile"]["id"] == "morrowind"
    assert [b["name"] for b in view["buttons"]] == ["UP", "DOWN", "LEFT", "RIGHT", "MINUS", "Y", "B", "Z", "A", "PLUS"]
    assert "attack" in [a["name"] for a in view["actions"]] and view["key_slots"] == [{"name": "use", "label": "Use / open / take"}]
    assert view["key_labels"]["KeyE"] == "E" and view["dirty"] is False and view["builtin"] is True
    assert "turn_rate" in view["options"] and view["modes"] == ["easy", "medium", "real"]


def test_an_edit_applies_at_once_and_is_marked_unsaved(dash):
    edited = copy.deepcopy(profiles.load("morrowind"))
    edited["bindings"]["B"] = "jump"
    edited["keys"]["use"] = "KeyF"
    code, data = dash.post("/profile/apply", {"profile": edited})
    assert code == 200 and profiles.current("openmw")["bindings"]["B"] == "jump" and keys.BINDINGS["use"] == (0x21, False)
    view = json.loads(dash.get("/profile")[1])
    assert view["dirty"] is True and view["profile"]["keys"]["use"] == "KeyF"


def test_bad_edits_are_refused_with_reasons_and_change_nothing(dash):
    edited = copy.deepcopy(profiles.load("morrowind"))
    edited["bindings"]["B"] = "fly"
    edited["keys"]["use"] = "MetaLeft"
    code, data = dash.post("/profile/apply", {"profile": edited})
    assert code == 400 and len(data["errors"]) == 2
    assert profiles.current("openmw")["bindings"]["B"] == "attack"
    other = profiles.load("omsi")
    code, data = dash.post("/profile/apply", {"profile": other})
    assert code == 400 and "target" in data["errors"][0]


def test_save_save_as_select_export_import_delete(dash):
    p = copy.deepcopy(profiles.load("morrowind"))
    p["bindings"]["B"] = "jump"
    dash.post("/profile/apply", {"profile": p})
    # "Save as…": a new profile of yours, which becomes the active one
    code, data = dash.post("/profile/save", {"name": "Marcin's Morrowind"})
    assert code == 200 and data["id"] == "marcin-s-morrowind"
    assert profiles.load("marcin-s-morrowind")["bindings"]["B"] == "jump"
    assert json.loads(dash.get("/profile")[1])["saved_by_you"] is True
    # the built-in is untouched, and selecting it brings back its bindings
    assert profiles.load("morrowind")["bindings"]["B"] == "attack"
    assert dash.post("/profile/select", {"id": "morrowind"})[0] == 200 and profiles.current("openmw")["bindings"]["B"] == "attack"
    # export: a download with a good name
    code, body, headers = dash.get("/profile/export?id=marcin-s-morrowind")
    assert code == 200 and 'filename="pedalator-marcin-s-morrowind.json"' in headers["Content-Disposition"]
    exported = body.decode()
    # import under another id: conflicts are reported, then allowed on request
    assert dash.post("/profile/import", {"text": exported, "id": "friend"})[0] == 200
    code, data = dash.post("/profile/import", {"text": exported, "id": "friend"})
    assert code == 400 and "already exists" in data["errors"][0]
    assert dash.post("/profile/import", {"text": exported, "id": "friend", "overwrite": True})[0] == 200
    code, data = dash.post("/profile/import", {"text": '{"target": "openmw"'})
    assert code == 400 and "not valid JSON" in data["errors"][0]
    listing = json.loads(dash.get("/profiles")[1])
    ids = [p["id"] for p in listing["profiles"]]
    assert {"morrowind", "marcin-s-morrowind", "friend"} <= set(ids)
    # delete: only yours; the built-in stays
    assert dash.post("/profile/delete", {"id": "friend"})[0] == 200
    assert dash.post("/profile/delete", {"id": "morrowind"})[0] == 404
    assert dash.post("/profile/select", {"id": "omsi"})[0] == 400          # another target


def test_a_profile_for_the_wrong_target_cannot_be_selected(dash):
    code, data = dash.post("/profile/select", {"id": "generic-wasd"})
    assert code == 400 and "keys" in data["errors"][0]


# ------------------------------------------------------------------------------ other web pages must not get in
def test_a_page_on_another_site_cannot_post(dash):
    # a cross-site "simple" request is text/plain: refused
    code, _ = dash.post("/preset", {"name": "real"}, headers={"Content-Type": "text/plain"})
    assert code == 415 and state["preset"] != "real"
    code, _ = dash.post("/profile/apply", {"profile": profiles.load("morrowind")}, headers={"Content-Type": "text/plain"})
    assert code == 415


def test_a_rebinding_attack_with_a_foreign_host_name_is_refused(dash):
    c = http.client.HTTPConnection("127.0.0.1", dash.port, timeout=5)
    c.putrequest("GET", "/state", skip_host=True)
    c.putheader("Host", f"evil.example:{dash.port}")
    c.endheaders()
    r = c.getresponse()
    r.read()
    assert r.status == 403
    code, _ = dash.post("/preset", {"name": "real"}, headers={"Host": "evil.example"})
    assert code == 403


def test_a_huge_body_is_refused(dash):
    code, data = dash.post("/profile/import", {"text": "x" * 300_000})
    assert code == 413
