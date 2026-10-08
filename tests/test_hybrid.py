"""Hybrid mode: who reads the trainer and who reads the Click, and a PC that refuses data it does not want."""
import http.client
import json
import ssl
import subprocess
import sys
from pathlib import Path

import pytest

from pedalator.cli import resolve_sources
from pedalator.phone_server import start_phone_servers
from pedalator.state import state

from .conftest import free_port
from .test_e2e import fields, wait_for

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("trainer,click,remote,simulate,expected", [
    (None, "auto", False, False, ("pc", "pc")),                 # a PC with Bluetooth reads both
    (None, "auto", True, False, ("phone", "phone")),            # --remote: the phone reads both
    (None, "auto", False, True, ("pc", "off")),                 # a simulated rider needs no Click
    (None, "auto", True, True, ("phone", "phone")),
    ("pc", "phone", False, False, ("pc", "phone")),             # hybrid: trainer on the PC, Click on a laptop
    ("phone", "pc", False, False, ("phone", "pc")),             # the other way round
    ("pc", "off", False, False, ("pc", "off")),
    ("pc", "auto", True, False, ("pc", "pc")),                  # an explicit --trainer beats --remote
])
def test_who_reads_what(trainer, click, remote, simulate, expected):
    assert resolve_sources(trainer, click, remote, simulate) == expected


@pytest.fixture()
def hybrid_phone(tmp_path):
    pport, cport = free_port(), free_port()
    token, servers = start_phone_servers("127.0.0.1", tmp_path, phone_port=pport, ca_port=cport, host="127.0.0.1",
                                         accept={"trainer": False, "click": True})
    ctx = ssl.create_default_context(cafile=str(tmp_path / "ca.pem"))
    yield http.client.HTTPSConnection("127.0.0.1", pport, context=ctx, timeout=5), token
    for s in servers:
        s.shutdown()
        s.server_close()


def post(c, token, path, body):
    c.request("POST", f"{path}?t={token}", body=json.dumps(body))
    r = c.getresponse()
    r.read()
    return r.status


def test_the_pc_tells_the_page_what_it_wants(hybrid_phone):
    c, token = hybrid_phone
    c.request("GET", f"/phone/ping?t={token}")
    info = json.loads(c.getresponse().read())
    assert info == {"ok": True, "trainer": False, "click": True}


def test_trainer_data_is_refused_when_the_pc_reads_the_trainer(hybrid_phone):
    c, token = hybrid_phone
    state["power"] = 123
    assert post(c, token, "/phone/data", {"hex": "4400000000007800"}) == 409
    assert post(c, token, "/phone/status", {"kind": "connected", "name": "Another trainer"}) == 409
    assert post(c, token, "/phone/status", {"kind": "cp", "hex": "801101"}) == 409
    assert state["power"] == 123 and state["trainer_name"] == "-"             # nothing leaked into the state


def test_click_data_and_logs_are_accepted(hybrid_phone):
    c, token = hybrid_phone
    assert post(c, token, "/phone/buttons", {"pressed": ["left"], "raw": ["LEFT"]}) == 200
    assert post(c, token, "/phone/status", {"kind": "click", "connected": True, "name": "Zwift Click"}) == 200
    assert post(c, token, "/phone/status", {"kind": "log", "msg": "hello"}) == 200
    assert state["raw"] == ["LEFT"] and state["click_connected"] is True


def test_the_other_way_round_refuses_the_click(tmp_path):
    pport, cport = free_port(), free_port()
    token, servers = start_phone_servers("127.0.0.1", tmp_path, phone_port=pport, ca_port=cport, host="127.0.0.1",
                                         accept={"trainer": True, "click": False})
    try:
        ctx = ssl.create_default_context(cafile=str(tmp_path / "ca.pem"))
        c = http.client.HTTPSConnection("127.0.0.1", pport, context=ctx, timeout=5)
        assert post(c, token, "/phone/buttons", {"pressed": [], "raw": ["A"]}) == 409
        assert post(c, token, "/phone/status", {"kind": "click", "connected": True}) == 409
        assert post(c, token, "/phone/data", {"hex": "4400000000007800"}) == 200
        assert state["raw"] == []
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()


def test_the_whole_program_in_hybrid_mode(tmp_path):
    """--trainer pc (simulated here) with --click phone: the simulated rider rides, the phone's buttons arrive."""
    ports = {k: free_port() for k in ("dash", "game", "phone", "ca")}
    state_file, log_file = tmp_path / "state.txt", tmp_path / "openmw.log"
    state_file.write_text("")
    log_file.write_text("")
    proc = subprocess.Popen(
        [sys.executable, "-m", "pedalator", "--simulate", "--click", "phone", "--target", "openmw", "--ip", "127.0.0.1",
         "--data-dir", str(tmp_path / "data"), "--openmw-state", str(state_file), "--openmw-log", str(log_file),
         "--dashboard-port", str(ports["dash"]), "--game-port", str(ports["game"]),
         "--phone-port", str(ports["phone"]), "--ca-port", str(ports["ca"]), "--mode", "real"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        token = wait_for(lambda: (tmp_path / "data" / "token.txt").read_text().strip())
        ctx = ssl.create_default_context(cafile=str(tmp_path / "data" / "ca.pem"))
        c = http.client.HTTPSConnection("127.0.0.1", ports["phone"], context=ctx, timeout=5)
        c.request("GET", f"/phone/ping?t={token}")
        assert json.loads(c.getresponse().read()) == {"ok": True, "trainer": False, "click": True}
        assert wait_for(lambda: post(c, token, "/phone/buttons", {"pressed": [], "raw": ["B", "LEFT"]}) == 200)
        got = wait_for(lambda: (f := fields(state_file.read_text())) and f["atk"] == "1" and f)
        assert got["turn"] == "-1" and float(got["move"]) >= 0 and int(got["n"]) > 0      # the Click's buttons are in
        assert wait_for(lambda: int(fields(state_file.read_text())["power"]) > 0)         # and the simulated rider rides
    finally:
        proc.terminate()
        proc.wait(timeout=10)
