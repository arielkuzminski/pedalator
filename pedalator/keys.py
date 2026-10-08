"""Keyboard output: the 'keys' target presses the game's driving keys (Windows SendInput, hardware scan codes)."""
from __future__ import annotations

import asyncio
import ctypes
import sys
import time

from .state import log, state, throttle_for

# Scan codes. numpad = OMSI's own layout (Inputs/keyboard.cfg: 8 throttle, 2 brake, 4/6 steering).
# In a bus W is the wipers, so numpad is the default; wasd suits games that use it.
KEYSETS = {
    "numpad": {"throttle": 0x48, "brake": 0x50, "left": 0x4B, "right": 0x4D},
    "wasd": {"throttle": 0x11, "brake": 0x1F, "left": 0x1E, "right": 0x20},
}
SCAN = dict(KEYSETS["numpad"])

# Zwift Click action (decoded by the phone page) -> the key name in SCAN that it holds
KEYMAP = {"left": "left", "right": "right", "brake": "brake"}


class _KI(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]


class _IN(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KI), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


_warned = False


def key(name: str, down: bool) -> None:
    """Press or release the key called ``name`` in SCAN. Only Windows can inject keys for now."""
    global _warned
    if sys.platform != "win32":
        if not _warned:
            _warned = True
            log("key output works on Windows only (see docs/roadmap.md for Linux/macOS)")
        return
    flags = 0x0008 | (0 if down else 0x0002)       # KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    i = _IN(type=1, ki=_KI(0, SCAN[name], flags, 0, None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_IN))


async def throttle_loop(floor: float = 15.0) -> None:
    """~20 Hz PWM of the throttle key: the share of time it is held is the rider's 'gas'."""
    period = 0.05
    try:
        while True:
            duty = throttle_for(state["power"], floor)
            if duty > 0:
                key("throttle", True)
                await asyncio.sleep(period * duty)
            if duty < 1:
                key("throttle", False)
                await asyncio.sleep(period * (1 - duty))
    finally:
        key("throttle", False)


async def buttons_loop() -> None:
    """Holds steering and brake while the phone reports the matching Zwift Click buttons (released if it goes quiet)."""
    down: set[str] = set()
    try:
        while True:
            want = set(state["buttons"]) if time.time() - state["t_buttons"] < 1.5 else set()
            for name, k in KEYMAP.items():
                if name in want and name not in down:
                    key(k, True)
                    down.add(name)
                elif name not in want and name in down:
                    key(k, False)
                    down.discard(name)
            await asyncio.sleep(0.03)
    finally:
        for name in down:
            key(KEYMAP[name], False)
