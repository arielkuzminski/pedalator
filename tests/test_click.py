"""The Zwift Click over the PC's Bluetooth: the decoder (against vectors shared with the JavaScript one), the
device finder, and a whole session against a fake ``bleak``."""
import asyncio
import json
import sys
import time
import types
from pathlib import Path

import pytest

from pedalator import click
from pedalator.state import state

VECTORS = json.loads((Path(__file__).parent / "vectors" / "click_frames.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_decoder_agrees_with_the_shared_vectors(v):
    frame = bytes.fromhex(v["hex"])
    raw, act = click.raw_buttons(frame), click.actions(frame)
    if v["raw"] is None:
        assert raw is None and act is None
    else:
        assert sorted(raw) == v["raw"] and sorted(act) == v["actions"]


def test_apply_frame_fills_the_state_and_ignores_other_frames():
    assert click.apply_frame(bytes.fromhex("23 08 df ff ff ff 0f")) is True          # B pressed
    assert state["raw"] == ["B"] and state["buttons"] == ["brake"] and state["t_buttons"] > 0
    assert click.apply_frame(bytes.fromhex("19 10 64")) is False                      # battery: no change
    assert state["raw"] == ["B"]
    click.apply_frame(bytes.fromhex("23 08 ff ff ff ff 0f"))
    assert state["raw"] == [] and state["buttons"] == []


def test_a_controller_is_recognised_by_its_service_not_by_its_name():
    assert click.is_zwift_controller(["00000001-19CA-4651-86E5-FA29DCDD09D1"], {}, None)
    assert click.is_zwift_controller(["0000fc82-0000-1000-8000-00805f9b34fb"], {}, "anything")
    assert click.is_zwift_controller([], {0x094A: b"\x09"}, "Zwift Click")           # the name only counts with Zwift's data
    assert not click.is_zwift_controller([], {}, "Zwift Click")
    assert not click.is_zwift_controller([], {0x094A: b"\x01"}, "Zwift Hub")          # a Zwift trainer is not a controller
    assert not click.is_zwift_controller(["0000180f-0000-1000-8000-00805f9b34fb"], {}, "Kettle")


# ----------------------------------------------------------------------------- a fake bleak
class FakeAdv:
    def __init__(self, service_uuids=(), manufacturer_data=None, local_name=None, rssi=-60):
        self.service_uuids, self.manufacturer_data, self.local_name = list(service_uuids), manufacturer_data or {}, local_name
        self.rssi = rssi


class FakeDev:
    def __init__(self, name):
        self.name = name


class FakeClient:
    instances: list = []
    fail_connect = False

    def __init__(self, address, disconnected_callback=None):
        self.address, self.on_disconnect = address, disconnected_callback
        self.callbacks, self.writes = {}, []
        self.services = [types.SimpleNamespace(uuid=click.SERVICES[0].upper(), characteristics=[])]
        FakeClient.instances.append(self)

    async def __aenter__(self):
        if FakeClient.fail_connect:
            raise OSError("connection refused")
        return self

    async def __aexit__(self, *a):
        return False

    async def start_notify(self, char, cb):
        self.callbacks[char] = cb

    async def write_gatt_char(self, char, data, response=True):
        self.writes.append((char, bytes(data), response))

    def push(self, hexstr, char=click.ASYNC_CHAR):
        self.callbacks[char](None, bytearray.fromhex(hexstr))


@pytest.fixture()
def fake_bleak(monkeypatch):
    FakeClient.instances.clear()
    FakeClient.fail_connect = False
    devices = {}

    class FakeScanner:
        @staticmethod
        async def discover(timeout=5.0, return_adv=False, **kw):
            return dict(devices)

    mod = types.ModuleType("bleak")
    mod.BleakScanner, mod.BleakClient = FakeScanner, FakeClient
    monkeypatch.setitem(sys.modules, "bleak", mod)
    return devices


def test_find_click_picks_the_controller_among_other_devices(fake_bleak):
    fake_bleak["AA:01"] = (FakeDev("Mi Kettle"), FakeAdv())
    fake_bleak["AA:02"] = (FakeDev("Zwift Hub"), FakeAdv(manufacturer_data={0x094A: b"\x01"}))
    fake_bleak["AA:03"] = (FakeDev("Zwift Click"), FakeAdv(service_uuids=[click.SERVICES[1]]))
    assert asyncio.run(click.find_click(0.1)) == ("AA:03", "Zwift Click")
    del fake_bleak["AA:03"]
    assert asyncio.run(click.find_click(0.1)) is None


def test_a_session_does_the_handshake_and_follows_the_buttons(fake_bleak):
    async def scenario():
        task = asyncio.create_task(click.click_session("AA:03", "Zwift Click"))
        await asyncio.sleep(0.2)
        c = FakeClient.instances[-1]
        assert (click.SYNC_RX, b"RideOn", False) in c.writes                          # the handshake
        assert click.ASYNC_CHAR in c.callbacks and click.SYNC_TX in c.callbacks
        assert state["click_connected"] is True and state["click_name"] == "Zwift Click"
        c.push("23 08 fe ff ff ff 0f")                                                # LEFT held
        assert state["raw"] == ["LEFT"] and state["buttons"] == ["left"]
        state["t_buttons"] = time.time() - 5                                          # the frames stop while the button is held
        await asyncio.sleep(0.6)
        assert time.time() - state["t_buttons"] < 1.0                                 # ... and the bridge keeps it fresh
        c.push("23 08 ff ff ff ff 0f", click.SYNC_TX)                                 # released (arrives on the other channel)
        assert state["raw"] == []
        c.on_disconnect(c)
        with pytest.raises(ConnectionError):
            await task

    asyncio.run(scenario())


def test_a_controller_without_the_zwift_service_is_reported(fake_bleak):
    async def scenario():
        orig = FakeClient.__init__

        def init(self, *a, **k):
            orig(self, *a, **k)
            self.services = []

        FakeClient.__init__ = init
        try:
            with pytest.raises(RuntimeError, match="locked"):
                await click.click_session("AA:03", "Zwift Click")
        finally:
            FakeClient.__init__ = orig

    asyncio.run(scenario())


def test_the_loop_reconnects_and_clears_the_buttons(fake_bleak):
    fake_bleak["AA:03"] = (FakeDev("Zwift Click"), FakeAdv(service_uuids=[click.SERVICES[0]]))

    async def scenario():
        task = asyncio.create_task(click.click_loop(retry=0.1))
        await asyncio.sleep(0.4)
        first = FakeClient.instances[-1]
        first.push("23 08 fb ff ff ff 0f")
        assert state["raw"] == ["RIGHT"]
        first.on_disconnect(first)                                                    # the Click goes to sleep
        await asyncio.sleep(0.8)
        assert len(FakeClient.instances) >= 2 and state["click_connected"] is True    # found and connected again
        assert state["raw"] == []                                                     # nothing stays "held"
        task.cancel()

    asyncio.run(scenario())


def test_the_trainer_and_the_click_are_never_scanned_for_at_the_same_time(monkeypatch):
    from pedalator import ble
    running, peak = [0], [0]

    class Scanner:
        @staticmethod
        async def discover(timeout=5.0, return_adv=False, **kw):
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.15)
            running[0] -= 1
            return {}

    mod = types.ModuleType("bleak")
    mod.BleakScanner = Scanner
    monkeypatch.setitem(sys.modules, "bleak", mod)

    async def scenario():
        await asyncio.gather(ble.find_trainer(None), click.find_click(0.1), ble.find_trainer(None))

    asyncio.run(scenario())
    assert peak[0] == 1


def test_the_signal_strength_is_noted_when_a_device_is_found(fake_bleak):
    state.update(click_rssi=None)
    fake_bleak["AA:03"] = (FakeDev("Zwift Click"), FakeAdv(service_uuids=[click.SERVICES[1]], rssi=-77))
    asyncio.run(click.find_click(0.1))
    assert state["click_rssi"] == -77


def test_the_range_check_reports_the_strongest_trainer_and_click(fake_bleak):
    from pedalator.ftms import FTMS
    fake_bleak["AA:01"] = (FakeDev("Mi Kettle"), FakeAdv(rssi=-40))
    fake_bleak["AA:02"] = (FakeDev("KICKR"), FakeAdv(service_uuids=[FTMS.upper()], rssi=-90))
    fake_bleak["AA:04"] = (FakeDev("KICKR 2"), FakeAdv(service_uuids=[FTMS], rssi=-60))
    fake_bleak["AA:03"] = (FakeDev("Zwift Click"), FakeAdv(service_uuids=[click.SERVICES[1]], rssi=-94))
    assert asyncio.run(click.check_range(0.1)) == {"trainer": {"name": "KICKR 2", "rssi": -60},
                                                   "click": {"name": "Zwift Click", "rssi": -94}}
    fake_bleak.clear()
    assert asyncio.run(click.check_range(0.1)) == {"trainer": None, "click": None}
