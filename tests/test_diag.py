"""The flow check: it must call a smooth ride smooth and name the stage that breaks."""
import asyncio

import pytest

from pedalator import diag, keys
from pedalator import state as st
from pedalator.state import state

from .test_dashboard_session import dash  # noqa: F401  (the fixture)


def ride(seconds=10.0, ble_every=0.25, ble_gaps=(), loop_every=0.05, loop_stalls=(), key_holes=(), os_delay=0.0, gas_off=()):
    """Events of a ride at 90 W (gas 0.72): the trainer, the loop, the keys it presses and the OS's delivery.
    ``ble_gaps`` etc. are the times at which that stage goes quiet for a while: (start, length)."""
    ev = {"ble": [], "duty": [], "key": [], "os": []}
    t = 0.0
    while t < seconds:
        if not any(a <= t < a + n for a, n in ble_gaps):
            ev["ble"].append((t, 90))
        t += ble_every
    t = 0.0
    while t < seconds:
        stall = next((n for a, n in loop_stalls if abs(t - a) < loop_every / 2), 0.0)
        off = any(a <= t < a + n for a, n in gas_off)
        ev["duty"].append((t, 0.0 if off else 0.72))
        hole = off or any(a <= t < a + n for a, n in key_holes)
        if not hole:
            ev["key"].append((t, "throttle", True))
            ev["key"].append((t + 0.036, "throttle", False))
            ev["os"] += [(t + os_delay, True, True), (t + 0.036 + os_delay, False, True)]
        t += loop_every + stall
    return ev


def verdict(ev, seconds=10.0):
    return diag.analyze(ev, seconds)["verdict"]["code"]


def test_a_smooth_ride_is_called_smooth():
    r = diag.analyze(ride(), 10.0)
    assert r["verdict"]["code"] == "ok"
    assert r["loop"]["p50"] == 50 and r["keys"]["holes"] == 0 and r["ble"]["over_500ms"] == 0
    assert r["keys"]["gas_error"] < 0.1                       # the share of time down matches the gas asked for


def test_no_ride_is_not_called_smooth():
    assert verdict({}) == "no_data"


def test_gaps_in_the_trainers_packets_are_blamed_on_bluetooth():
    assert verdict(ride(ble_gaps=[(3.0, 1.6)])) == "ble"


def test_a_stalled_loop_is_blamed_on_the_loop():
    assert verdict(ride(loop_stalls=[(4.0, 0.4)])) == "loop"


def test_holes_in_the_key_presses_are_found():
    r = diag.analyze(ride(key_holes=[(4.0, 0.5)]), 10.0)
    assert r["keys"]["holes"] == 1 and r["keys"]["worst_hole_ms"] >= 450
    assert r["verdict"]["code"] in ("keys", "loop")           # (a hole in the presses is also a quiet loop's trait)


def test_a_pause_with_no_gas_is_not_a_hole():
    r = diag.analyze(ride(gas_off=[(4.0, 0.4)]), 10.0)           # the power fell under the floor for 0.4 s
    assert r["keys"]["holes"] == 0 and r["keys"]["gas_off_pct"] >= 3 and r["verdict"]["code"] == "ok"


def test_late_delivery_by_windows_is_blamed_on_windows():
    assert verdict(ride(os_delay=0.4)) == "os_latency"


def test_the_stage_order_blames_bluetooth_first():
    assert verdict(ride(ble_gaps=[(3.0, 1.6)], loop_stalls=[(4.0, 0.4)])) == "ble"


def test_a_key_held_down_is_not_a_fault():
    ev = ride()
    ev["key"] = [(0.0, "throttle", True)] + [(t, "throttle", True) for t in (0.05 * i for i in range(1, 200))]
    ev["os"] = [(t, True, True) for t, *_ in ev["key"]]
    ev["duty"] = [(t, 1.0) for t, _ in ev["duty"]]
    r = diag.analyze(ev, 10.0)
    assert r["keys"]["longest_hold_ms"] >= 9000 and r["verdict"]["code"] == "ok"


class StubHook:
    def __init__(self, scan, sink):
        self.sink = sink

    def start(self):
        return True

    def stop(self):
        pass


def test_a_recording_collects_events_and_lets_go_of_the_tap(monkeypatch):
    monkeypatch.setattr(diag, "KeyboardHook", StubHook)
    monkeypatch.setattr(keys, "key", lambda slot, down: st.tap("key", slot, down))      # (no real key presses)

    async def scenario():
        state["power"] = 90
        task = asyncio.create_task(keys.throttle_loop())
        try:
            return await diag.Probe().record(0.6)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            state["power"] = 0
    r = asyncio.run(scenario())
    assert r["loop"]["ticks"] >= 5 and r["keys"]["presses"] >= 3
    assert st._tap is None


def test_the_trainers_packets_are_reported_to_the_tap():
    from pedalator.ftms import on_bike_data
    seen = []
    st.set_tap(lambda kind, t, *v: seen.append((kind, v)))
    try:
        on_bike_data(None, bytearray(bytes.fromhex("44 00 e8 03 00 00 5a 00")))
    finally:
        st.set_tap(None)
    assert ("ble", (90,)) in seen


def test_the_flow_check_is_refused_without_a_ride_and_with_bad_seconds(dash, monkeypatch):  # noqa: F811
    assert dash.get("/diag")[1]["status"] == "idle"
    assert dash.post("/diag/start", {"seconds": 10})[0] == 409
    state["session"] = {"status": "running"}
    started = []
    monkeypatch.setattr(diag, "start", lambda seconds: started.append(seconds))
    try:
        assert dash.post("/diag/start", {"seconds": 1})[0] == 400
        assert dash.post("/diag/start", {"seconds": "x"})[0] == 400
        assert dash.post("/diag/start", {"seconds": 12})[0] == 200
        assert started == [12.0]
    finally:
        state["session"] = {"status": "idle"}


@pytest.mark.skipif(not hasattr(__import__("sys"), "getwindowsversion"), reason="Windows keyboard hook")
def test_the_windows_hook_sees_the_keys_sent_by_the_program():
    events = []
    hook = diag.KeyboardHook(keys.BINDINGS["throttle"][0], lambda t, down, inj: events.append((down, inj)))
    old = dict(keys.BINDINGS)
    keys.apply_keys({"throttle": "F9"})
    hook.scan = keys.BINDINGS["throttle"][0]
    try:
        assert hook.start()
        keys.key("throttle", True)
        keys.key("throttle", False)
        asyncio.run(asyncio.sleep(0.3))
    finally:
        hook.stop()
        keys.BINDINGS.update(old)
    assert (True, True) in events and (False, True) in events


def test_the_gap_between_key_events_ignores_a_pause_with_no_gas():
    r = diag.analyze(ride(gas_off=[(4.0, 0.6)]), 10.0)
    assert r["os"]["worst_gap_ms"] < 150                      # the 0.6 s silence was the rider's, not Windows'
