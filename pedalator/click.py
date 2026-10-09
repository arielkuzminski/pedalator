"""Zwift Click read over the PC's own Bluetooth (the same job the phone page does with Web Bluetooth).

The decoder mirrors the one in ``web/phone.html``; both are tested against ``tests/vectors/click_frames.json``.
Protocol notes: docs/zwift-click.md.
"""
from __future__ import annotations

import asyncio
import time

from .ble import scan_lock
from .ftms import FTMS
from .state import log, state

# Zwift's custom services: Click v1 / Play, and Click v2 / Ride
SERVICES = ("00000001-19ca-4651-86e5-fa29dcdd09d1", "0000fc82-0000-1000-8000-00805f9b34fb")
ASYNC_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"      # notifications: button frames
SYNC_RX = "00000003-19ca-4651-86e5-fa29dcdd09d1"         # write: the "RideOn" handshake
SYNC_TX = "00000004-19ca-4651-86e5-fa29dcdd09d1"         # indications
RIDE_ON = b"RideOn"
ZWIFT_COMPANY_ID = 0x094A
CONTROLLER_NAMES = ("zwift click", "zwift play", "zwift ride")

# message types (first byte of a frame)
TYPE_CLICK_V1 = 0x37
TYPE_BUTTONS = 0x23

# ButtonMap bits of a Click v2 / Ride; a pressed button is a CLEARED bit
RIDE_MASK = {"LEFT": 1, "UP": 2, "RIGHT": 4, "DOWN": 8, "A": 16, "B": 32, "Y": 64, "Z": 256,
             "SHIFT_UP_L": 512, "SHIFT_DN_L": 1024, "SHIFT_UP_R": 8192, "SHIFT_DN_R": 16384}
# the physical names the game targets get ("MINUS"/"PLUS" are the shift buttons of the left/right puck)
RAW_NAMES = (("LEFT", "LEFT"), ("RIGHT", "RIGHT"), ("UP", "UP"), ("DOWN", "DOWN"), ("A", "A"), ("B", "B"),
             ("Y", "Y"), ("Z", "Z"), ("MINUS", "SHIFT_UP_L"), ("PLUS", "SHIFT_UP_R"))


def varint(b: bytes, i: int) -> tuple[int, int]:
    """(value, bytes used) of the protobuf varint at ``b[i:]``."""
    v = s = n = 0
    while i + n < len(b):
        x = b[i + n]
        n += 1
        v += (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            break
    return v, n


def fields(b: bytes) -> dict[int, int]:
    """Field number -> value for the varint fields of a protobuf message (enough for the keypad messages)."""
    f: dict[int, int] = {}
    i = 0
    while i < len(b):
        tag, n = varint(b, i)
        i += n
        wt, fn = tag & 7, tag >> 3
        if wt == 0:
            v, m = varint(b, i)
            i += m
            f[fn] = v
        elif wt == 2:
            length, m = varint(b, i)
            i += m + length
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
        else:
            break
    return f


def raw_buttons(frame: bytes) -> set[str] | None:
    """The physical buttons held in a frame, or None when it is not a button frame.

    A Click v1 has only − and +: they are reported as LEFT and RIGHT (they steer).
    """
    if not frame:
        return None
    msg = frame[1:]
    if frame[0] == TYPE_CLICK_V1:
        f = fields(msg)
        raw = set()
        if f.get(2, 0) == 0:
            raw.add("LEFT")
        if f.get(1, 0) == 0:
            raw.add("RIGHT")
        return raw
    if frame[0] == TYPE_BUTTONS:
        f = fields(msg)
        if 1 not in f:
            return None
        return {name for name, bit in RAW_NAMES if f[1] & RIDE_MASK[bit] == 0}
    return None


def actions(frame: bytes) -> set[str] | None:
    """The driving actions (left / right / brake) a frame means for the ``keys`` target."""
    raw = raw_buttons(frame)
    if raw is None:
        return None
    act = set()
    if frame[0] == TYPE_CLICK_V1:
        return {"left" if b == "LEFT" else "right" for b in raw}
    if raw & {"LEFT", "Z"}:
        act.add("left")
    if raw & {"RIGHT", "A"}:
        act.add("right")
    if raw & {"DOWN", "B"}:
        act.add("brake")
    return act


def apply_frame(frame: bytes) -> bool:
    """Put what a frame says into the shared state. False if it is not a button frame."""
    raw = raw_buttons(frame)
    if raw is None:
        return False
    state["raw"] = sorted(raw)
    state["buttons"] = sorted(actions(frame) or ())
    state["t_buttons"] = time.time()
    return True


def is_zwift_controller(service_uuids, manufacturer_data, name: str | None) -> bool:
    """Is this advertisement a Zwift Click / Play / Ride? The service UUID is the reliable sign, the name a fallback."""
    uuids = {u.lower() for u in (service_uuids or ())}
    if uuids & set(SERVICES):
        return True
    return bool((name or "").lower().startswith(CONTROLLER_NAMES) and ZWIFT_COMPANY_ID in (manufacturer_data or {}))


async def find_click(timeout: float = 6.0) -> tuple[str, str] | None:
    from bleak import BleakScanner
    async with scan_lock():
        devs = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for addr, (dev, adv) in devs.items():
        if is_zwift_controller(adv.service_uuids, adv.manufacturer_data, dev.name or adv.local_name):
            state["click_rssi"] = adv.rssi
            return addr, dev.name or adv.local_name or addr
    return None


async def check_range(timeout: float = 6.0) -> dict:
    """One scan, for placing the adapter before a ride: the strongest trainer and Zwift controller in range,
    each as ``{"name", "rssi"}`` (dBm; closer to 0 is stronger) or None."""
    from bleak import BleakScanner
    async with scan_lock():
        devs = await BleakScanner.discover(timeout=timeout, return_adv=True)
    found: dict = {"trainer": None, "click": None}
    for addr, (dev, adv) in devs.items():
        name = dev.name or adv.local_name or addr
        kind = ("trainer" if FTMS.lower() in {u.lower() for u in adv.service_uuids}
                else "click" if is_zwift_controller(adv.service_uuids, adv.manufacturer_data, name) else None)
        if kind and (found[kind] is None or adv.rssi > found[kind]["rssi"]):
            found[kind] = {"name": name, "rssi": adv.rssi}
    return found


async def click_session(address: str, name: str) -> None:
    """One connection: handshake, then button frames until the controller goes away."""
    from bleak import BleakClient
    gone = asyncio.Event()

    def on_frame(_sender, data: bytearray) -> None:
        apply_frame(bytes(data))

    async with BleakClient(address, disconnected_callback=lambda _c: gone.set()) as c:
        if not any(s.uuid.lower() in SERVICES for s in c.services):
            raise RuntimeError("no Zwift service: the controller may be locked (unlock it once in Zwift's own app)")
        await c.start_notify(ASYNC_CHAR, on_frame)
        await c.start_notify(SYNC_TX, on_frame)
        await c.write_gatt_char(SYNC_RX, RIDE_ON, response=False)
        state.update(click_connected=True, click_name=name)
        log(f"Zwift Click connected: {name}")
        while not gone.is_set():
            # a held button keeps the state fresh (the game side lets go of buttons it stopped hearing about)
            if state["raw"]:
                state["t_buttons"] = time.time()
            await asyncio.sleep(0.4)
    raise ConnectionError("controller disconnected")


async def click_loop(retry: float = 5.0) -> None:
    """Keep a Zwift controller connected for as long as the bridge runs."""
    last_note = 0.0
    while True:
        try:
            found = await find_click()
            if found is None:
                if time.time() - last_note > 60:
                    last_note = time.time()
                    log("no Zwift Click found - press a button to wake it and close Zwift Companion (retrying)")
            else:
                await click_session(*found)
        except Exception as e:
            log(f"Zwift Click: {type(e).__name__}: {e}")
        state.update(click_connected=False, raw=[], buttons=[])
        await asyncio.sleep(retry)
