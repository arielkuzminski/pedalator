"""The whole program, started as a user would start it (``python -m pedalator ...``) on free ports."""
import http.client
import json
import ssl
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from .conftest import free_port

ROOT = Path(__file__).resolve().parent.parent


def fields(line: str) -> dict:
    return dict(p.split("=") for p in line.strip().split(";"))


def wait_for(fn, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.2)
    raise AssertionError("timed out")


@pytest.fixture()
def bridge(tmp_path):
    ports = {k: free_port() for k in ("dash", "game", "phone", "ca")}
    state_file = tmp_path / "state.txt"
    state_file.write_text("")
    log_file = tmp_path / "openmw.log"
    log_file.write_text("")
    proc = subprocess.Popen(
        [sys.executable, "-m", "pedalator", "--remote", "--target", "openmw", "--ip", "127.0.0.1",
         "--data-dir", str(tmp_path / "data"), "--openmw-state", str(state_file), "--openmw-log", str(log_file),
         "--dashboard-port", str(ports["dash"]), "--game-port", str(ports["game"]),
         "--phone-port", str(ports["phone"]), "--ca-port", str(ports["ca"]), "--mode", "real"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        token_file = tmp_path / "data" / "token.txt"
        token = wait_for(lambda: token_file.read_text().strip())
        yield {"ports": ports, "state": state_file, "log": log_file, "token": token, "ca": tmp_path / "data" / "ca.pem"}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_phone_to_game_and_back(bridge):
    p = bridge["ports"]
    ctx = ssl.create_default_context(cafile=str(bridge["ca"]))
    c = http.client.HTTPSConnection("127.0.0.1", p["phone"], context=ctx, timeout=5)

    def post(path, body):
        c.request("POST", f"{path}?t={bridge['token']}", body=json.dumps(body))
        r = c.getresponse()
        r.read()
        return r.status

    # the phone says: 200 W, and the Click's B and UP buttons are held
    pkt = struct.pack("<HHHh", 0x0044, 2000, 160, 200).hex()
    assert wait_for(lambda: post("/phone/data", {"hex": pkt}) == 200)
    assert post("/phone/buttons", {"pressed": [], "raw": ["B", "UP"]}) == 200
    got = wait_for(lambda: (f := fields(bridge["state"].read_text())) and f["atk"] == "1" and f)
    assert got["power"] == "200" and got["look"] == "-1" and got["move"] == "0.800"      # realistic: 200 W of 250

    # the game writes its gradient into the log; the dashboard shows it
    with open(bridge["log"], "a") as f:
        f.write("PEDALATOR grade=6.50\n")

    def dash_grade():
        d = http.client.HTTPConnection("127.0.0.1", p["dash"], timeout=5)
        d.request("GET", "/state")
        s = json.loads(d.getresponse().read())
        return s if s["game_grade"] == 6.5 else None

    snap = wait_for(dash_grade)
    assert snap["grade"] == 6.5 and snap["connected"] is True and snap["power"] == 200
