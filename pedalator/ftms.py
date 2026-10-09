"""Bluetooth FTMS (Fitness Machine Service, GATT 0x1826): what a smart trainer says and how to talk to it."""
from __future__ import annotations

import struct
import time

from .state import log, state, tap

FTMS = "00001826-0000-1000-8000-00805f9b34fb"
BIKE_DATA = "00002ad2-0000-1000-8000-00805f9b34fb"       # Indoor Bike Data (notifications)
CONTROL = "00002ad9-0000-1000-8000-00805f9b34fb"         # Fitness Machine Control Point (write + indications)

OP_REQUEST_CONTROL = 0x00
OP_START = 0x07
OP_SET_SIMULATION = 0x11

CP_RESULT = {1: "ok", 2: "not supported", 3: "invalid parameter", 4: "failed", 5: "control not permitted"}


def parse_bike_data(data: bytes) -> dict:
    """Indoor Bike Data: the fields are present in the order of the flag bits.

    Returns whatever the packet carries: speed (km/h), cadence (rpm), distance (m), resistance, power (W), hr (bpm).
    """
    flags = struct.unpack_from("<H", data, 0)[0]
    o = 2
    out: dict = {}
    if not flags & 0x1:                       # bit 0 set means "more data" and the speed is absent
        out["speed"] = struct.unpack_from("<H", data, o)[0] / 100.0
        o += 2
    if flags & 0x2:                           # average speed
        o += 2
    if flags & 0x4:
        out["cadence"] = struct.unpack_from("<H", data, o)[0] / 2.0
        o += 2
    if flags & 0x8:                           # average cadence
        o += 2
    if flags & 0x10:
        out["distance"] = int.from_bytes(data[o:o + 3], "little")
        o += 3
    if flags & 0x20:
        out["resistance"] = struct.unpack_from("<h", data, o)[0]
        o += 2
    if flags & 0x40:
        out["power"] = struct.unpack_from("<h", data, o)[0]
        o += 2
    if flags & 0x80:                          # average power
        o += 2
    if flags & 0x100:                         # energy: total, per hour, per minute
        o += 5
    if flags & 0x200:
        out["hr"] = data[o]
    return out


def simulation_command(grade_percent: float, crr: int = 40, cw: int = 51) -> bytes:
    """Set Indoor Bike Simulation Parameters: wind 0, grade in 0.01 %, rolling resistance 0.0040, drag 0.51 kg/m."""
    return struct.pack("<BhhBB", OP_SET_SIMULATION, 0, int(round(grade_percent * 100)), crr, cw)


def on_bike_data(_sender, data: bytearray) -> None:
    try:
        state.update(parse_bike_data(bytes(data)))
    except Exception as e:                     # a short or odd packet must not kill the stream
        log(f"bike data parse error: {e}")
    state["raw_hex"] = bytes(data).hex(" ")
    state["t_packet"] = time.time()
    tap("ble", state["power"])


def on_control_point(_sender, data: bytearray) -> None:
    d = bytes(data)
    if len(d) >= 3 and d[0] == 0x80:           # 0x80 = response code, then the request opcode and the result
        state["cp_last"] = f"op 0x{d[1]:02X}: {CP_RESULT.get(d[2], d[2])}"
        state["t_cp"] = time.time()
        if d[2] != 1:
            log(f"trainer answered {state['cp_last']}")
