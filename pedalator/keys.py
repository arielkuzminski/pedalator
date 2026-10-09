"""Keyboard output: the 'keys' target presses the game's driving keys (Windows SendInput, hardware scan codes).

Which keys, and which Zwift Click buttons mean what, comes from the active profile (``profiles.py``).
"""
from __future__ import annotations

import asyncio
import ctypes
import sys
import time

from . import keynames
from .state import log, state, tap, throttle_for

# slot -> (scan code, extended). Filled from the profile; these are OMSI's own keys until one is applied.
BINDINGS: dict[str, tuple[int, bool]] = {
    "throttle": keynames.scan("Numpad8"), "brake": keynames.scan("Numpad2"),
    "left": keynames.scan("Numpad4"), "right": keynames.scan("Numpad6"), "use": keynames.scan("KeyE"),
}

# what the keys target holds for each driving action of a profile
ACTION_SLOT = {"steer_left": "left", "steer_right": "right", "brake": "brake"}


def apply_keys(keymap: dict[str, str]) -> None:
    """Use these keys (slot -> key name) from now on."""
    for slot, name in keymap.items():
        BINDINGS[slot] = keynames.scan(name)


class _KI(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]


class _IN(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KI), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


_warned = False


def key(slot: str, down: bool) -> None:
    """Press or release the key in ``slot``. Only Windows can inject keys for now."""
    global _warned
    if sys.platform != "win32":
        if not _warned:
            _warned = True
            log("key output works on Windows only (see docs/roadmap.md for Linux/macOS)")
        return
    tap("key", slot, down)
    scan, extended = BINDINGS[slot]
    flags = 0x0008 | (0x0001 if extended else 0) | (0 if down else 0x0002)   # SCANCODE | EXTENDEDKEY | KEYUP
    i = _IN(type=1, ki=_KI(0, scan, flags, 0, None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_IN))


async def throttle_loop(floor: float | None = None) -> None:
    """~20 Hz PWM of the throttle key: the share of time it is down is the rider's 'gas'."""
    period = 0.05
    fine = _fine_timer(True)               # without it Windows sleeps in 15.6 ms steps and the 50 ms period becomes 62.5 ms
    try:
        while True:
            duty = throttle_for(state["power"], floor)
            tap("duty", duty)
            if duty > 0:
                key("throttle", True)
                await asyncio.sleep(period * duty)
            if duty < 1:
                key("throttle", False)
                await asyncio.sleep(period * (1 - duty))
    finally:
        key("throttle", False)
        _fine_timer(False, fine)


def _fine_timer(on: bool, was: bool = True) -> bool:
    """Ask Windows for 1 ms timer ticks (and give them back); True when it was asked."""
    if sys.platform != "win32" or not was:
        return False
    try:
        (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)
        return on
    except OSError:
        return False


def wanted_slots(raw) -> set[str]:
    """The key slots the held Click buttons ask for, by the active profile's bindings."""
    from . import profiles
    return {slot for action, slot in ACTION_SLOT.items() if profiles.held("keys", action, raw)}


async def buttons_loop() -> None:
    """Holds steering and brake while the matching Zwift Click buttons are held (let go if it goes quiet)."""
    down: set[str] = set()
    try:
        while True:
            raw = state["raw"] if time.time() - state["t_buttons"] < 1.5 else ()
            want = wanted_slots(raw)
            for slot in ("left", "right", "brake"):
                if slot in want and slot not in down:
                    key(slot, True)
                    down.add(slot)
                elif slot not in want and slot in down:
                    key(slot, False)
                    down.discard(slot)
            await asyncio.sleep(0.03)
    finally:
        for slot in down:
            key(slot, False)
