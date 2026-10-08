"""The two HTTP servers, started for real on free ports."""
import http.client
import json
import ssl
import struct
import time

import pytest

from pedalator.dashboard_server import start_dashboard
from pedalator.phone_server import start_phone_servers
from pedalator.state import apply_preset, state

from .conftest import free_port


@pytest.fixture()
def phone(tmp_path):
    pport, cport = free_port(), free_port()
    token, servers = start_phone_servers("127.0.0.1", tmp_path, phone_port=pport, ca_port=cport, host="127.0.0.1")
    ctx = ssl.create_default_context(cafile=str(tmp_path / "ca.pem"))
    yield {"token": token, "port": pport, "ca_port": cport, "ctx": ctx, "dir": tmp_path}
    for s in servers:
        s.shutdown()
        s.server_close()


def conn(phone):
    return http.client.HTTPSConnection("127.0.0.1", phone["port"], context=phone["ctx"], timeout=5)


def post(c, phone, path, body, token=None):
    c.request("POST", f"{path}?t={token or phone['token']}", body=json.dumps(body))
    r = c.getresponse()
    r.read()
    return r.status


def test_certificate_chain_is_trusted_by_a_strict_client(phone):
    c = conn(phone)
    c.request("GET", f"/phone?t={phone['token']}")
    r = c.getresponse()
    page = r.read()
    assert r.status == 200 and b"Pedal" in page


def test_a_client_that_does_not_trust_the_ca_is_refused(phone):
    c = http.client.HTTPSConnection("127.0.0.1", phone["port"], context=ssl.create_default_context(), timeout=5)
    with pytest.raises(ssl.SSLError):
        c.request("GET", f"/phone?t={phone['token']}")


def test_wrong_token_is_rejected_and_does_not_poison_the_next_request(phone):
    c = conn(phone)
    assert post(c, phone, "/phone/data", {"hex": "00"}, token="wrong") == 403
    c2 = conn(phone)
    assert post(c2, phone, "/phone/data", {"hex": struct.pack("<HHhh", 0x0044, 0, 0, 120)[:8].hex()}) == 200


def test_trainer_data_from_the_phone_updates_the_state(phone):
    c = conn(phone)
    pkt = struct.pack("<HHHh", 0x0044, 2500, 180, 175).hex()
    assert post(c, phone, "/phone/data", {"hex": pkt}) == 200
    assert state["power"] == 175 and state["cadence"] == 90.0 and state["connected"] is True
    assert post(c, phone, "/phone/status", {"kind": "connected", "name": "Some Trainer"}) == 200
    assert state["trainer_name"] == "Some Trainer"
    assert post(c, phone, "/phone/status", {"kind": "cp", "hex": "801101"}) == 200
    assert state["cp_last"] == "op 0x11: ok"


def test_buttons_are_filtered_to_known_names(phone):
    c = conn(phone)
    assert post(c, phone, "/phone/buttons", {"pressed": ["left", "bogus"], "raw": ["LEFT", "B", "BOGUS"]}) == 200
    assert state["buttons"] == ["left"] and sorted(state["raw"]) == ["B", "LEFT"] and state["t_buttons"] > 0


def test_many_requests_share_one_connection(phone):
    c = conn(phone)
    t0 = time.time()
    for _ in range(30):
        assert post(c, phone, "/phone/status", {"kind": "log", "msg": "x"}) == 200
    assert time.time() - t0 < 3 and c.sock is not None          # keep-alive: no new handshake each time


def test_click_frames_are_counted_not_logged(phone):
    c = conn(phone)
    post(c, phone, "/phone/status", {"kind": "log", "msg": "Click: 23 08 fe ff ff ff 0f"})
    post(c, phone, "/phone/status", {"kind": "log", "msg": "Click: 2a 08 03"})
    from pedalator.state import log_lines
    assert state["click_frames"] == 1
    assert any("Click: 2a 08 03" in line for line in log_lines) and not any("23 08" in line for line in log_lines)


def test_gradient_stream_sends_the_effective_grade(phone):
    apply_preset("real")
    state["game_grade"] = 5.0
    c = conn(phone)
    c.request("GET", f"/phone/events?t={phone['token']}")
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type") == "text/event-stream"
    msg = json.loads(r.fp.readline().decode().split("data: ")[1])
    assert msg["grade"] == 5.0 and msg["difficulty"] == 1.0 and msg["notice"] == ""
    c.close()


def test_ca_is_served_over_plain_http_and_is_a_der_certificate(phone):
    c = http.client.HTTPConnection("127.0.0.1", phone["ca_port"], timeout=5)
    c.request("GET", "/ca.crt")
    r = c.getresponse()
    body = r.read()
    assert r.status == 200 and r.getheader("Content-Type") == "application/x-x509-ca-cert" and body[:1] == b"\x30"
    c.request("GET", "/")
    page = c.getresponse().read()
    assert b"Pedalator" in page


def test_token_survives_a_restart(tmp_path):
    from pedalator.certs import load_token
    assert load_token(tmp_path) == load_token(tmp_path)


def test_dashboard_controls_change_the_riding_mode(tmp_path):
    port = free_port()
    srv = start_dashboard(port)
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)

        def send(path, body):
            c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
            r = c.getresponse()
            r.read()
            return r.status

        assert send("/preset", {"name": "real"}) == 200 and state["difficulty"] == 1.0
        assert send("/gain", {"gain": 99}) == 200 and state["gain"] == 4.0 and state["preset"] == "custom"
        assert send("/mode", {"mode": "manual"}) == 200 and send("/grade", {"grade": 7}) == 200
        assert send("/mode", {"mode": "nonsense"}) == 400
        c.request("GET", "/state")
        snap = json.loads(c.getresponse().read())
        assert snap["manual_grade"] == 7 and snap["mode"] == "manual"
        c.request("GET", "/")
        r = c.getresponse()
        assert r.status == 200 and b"Pedal" in r.read()
        c.request("GET", "/?lang=pl")                     # a query string must not turn the page into a 404
        r = c.getresponse()
        assert r.status == 200 and b"Pedal" in r.read()
    finally:
        srv.shutdown()
        srv.server_close()
