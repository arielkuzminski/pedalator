"""Direct Bluetooth LE connection from this PC to the trainer (needs a BLE-capable adapter).

If the PC has no BLE "central" role (older adapters), use phone mode instead: ``pedalator --remote``.
"""
from __future__ import annotations

import asyncio

from .ftms import (
    BIKE_DATA,
    CONTROL,
    FTMS,
    OP_REQUEST_CONTROL,
    OP_START,
    on_bike_data,
    on_control_point,
    simulation_command,
)
from .state import effective_grade, log, state

_scan_lock: asyncio.Lock | None = None


def scan_lock() -> asyncio.Lock:
    """One Bluetooth scan at a time: the trainer and the Click are looked for by separate loops, and two scans
    running together make Windows' Bluetooth stack fail."""
    global _scan_lock
    if _scan_lock is None:
        _scan_lock = asyncio.Lock()
    return _scan_lock


async def find_trainer(address: str | None):
    """Return (address, name) of the first FTMS trainer in range, or (None, None)."""
    from bleak import BleakScanner
    if address:
        return address, address
    log("scanning for FTMS trainers (8 s)...")
    async with scan_lock():
        devs = await BleakScanner.discover(timeout=8.0, service_uuids=[FTMS], return_adv=True)
    for addr, (dev, _adv) in devs.items():
        log(f"  found {addr} {dev.name}")
    if not devs:
        return None, None
    addr, (dev, _) = next(iter(devs.items()))
    return addr, dev.name or addr


async def trainer_session(address: str, name: str) -> None:
    """One connection: notifications in, the simulated gradient out once a second."""
    from bleak import BleakClient
    gone = asyncio.Event()
    async with BleakClient(address, disconnected_callback=lambda _c: gone.set()) as c:
        state.update(connected=True, trainer_name=name)
        log(f"connected to {name}")
        await c.start_notify(BIKE_DATA, on_bike_data)
        try:
            await c.start_notify(CONTROL, on_control_point)    # indications: the trainer's answers
        except Exception as e:
            log(f"control point indications unavailable: {e}")
        await c.write_gatt_char(CONTROL, bytes([OP_REQUEST_CONTROL]), response=True)
        await c.write_gatt_char(CONTROL, bytes([OP_START]), response=True)
        while not gone.is_set():
            await c.write_gatt_char(CONTROL, simulation_command(effective_grade()), response=True)
            await asyncio.sleep(1.0)
    raise ConnectionError("trainer disconnected")


async def trainer_loop(address: str | None) -> None:
    """Keep a trainer connected for as long as the bridge runs."""
    while True:
        try:
            addr, name = await find_trainer(address)
            if addr is None:
                log("no FTMS trainer found - close other apps using it (Zwift, a phone app); retrying in 5 s")
            else:
                await trainer_session(addr, name)
        except Exception as e:
            log(f"trainer error: {type(e).__name__}: {e}")
        state["connected"] = False
        await asyncio.sleep(5)
