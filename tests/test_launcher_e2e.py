"""``python -m pedalator`` with no game picked: only the dashboard runs until a ride is started from its page."""
import http.client
import json
import subprocess
import sys

import pytest

from .conftest import free_port
from .test_e2e import ROOT, wait_for


def call(port, method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    c.request(method, path, body=None if body is None else json.dumps(body),
              headers={"Content-Type": "application/json"} if body is not None else {})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


@pytest.fixture()
def launcher(tmp_path):
    dash, game = free_port(), free_port()
    proc = subprocess.Popen([sys.executable, "-m", "pedalator", "--dashboard-port", str(dash), "--game-port", str(game),
                             "--data-dir", str(tmp_path)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_for(lambda: call(dash, "GET", "/session")[1]["available"])
        yield dash
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_nothing_runs_until_a_ride_is_started_and_it_can_be_changed_without_a_restart(launcher):
    code, state = call(launcher, "GET", "/state")
    assert state["session"]["status"] == "idle" and state["connected"] is False and state["power"] == 0

    assert call(launcher, "POST", "/session/start", {"profile": "generic-udp", "trainer": "simulate"})[0] == 200
    live = wait_for(lambda: (lambda s: s if s["power"] > 0 else None)(call(launcher, "GET", "/state")[1]))
    assert live["session"]["status"] == "running" and live["target"] == "udp"

    assert call(launcher, "POST", "/session/stop", {})[0] == 200
    assert call(launcher, "GET", "/state")[1]["session"]["status"] == "idle"
    assert call(launcher, "POST", "/session/start", {"profile": "omsi", "trainer": "simulate"})[1]["session"]["target"] == "keys"
