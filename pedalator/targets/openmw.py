"""OpenMW (Morrowind): the Lua mod in ``data/openmw/Pedalator`` reads ``pedalator/state.txt``; the gradient comes back
through the game's log (the mod prints ``PEDALATOR grade=<percent>``).

Pedalator's one key press here is "use" (open / take / talk): OpenMW has no Lua call for "use what I look at".
"""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from .. import keys
from ..state import clamp_grade, log, state, throttle_for

# what each physical Zwift Click button does (right puck: Y top, Z left, A right, B bottom)
BUTTONS = {"turn_left": "LEFT", "turn_right": "RIGHT", "look_up": "UP", "look_down": "DOWN",
           "attack": "B", "jump": "A", "draw_weapon": "Y", "use": "Z"}

USE_KEYS = {"e": 0x12, "f": 0x21, "space": 0x39, "enter": 0x1C}
GRADE_LINE = re.compile(rb"PEDALATOR grade=(-?[0-9.]+)")


def state_line(n: int, power: float, raw: set[str], floor: float = 15.0) -> str:
    """One line for the mod's player script. ``move`` is 0..1, ``turn`` +1 is right, ``look`` +1 is down."""
    held = lambda action: 1 if BUTTONS[action] in raw else 0           # noqa: E731
    return (f"n={n};move={throttle_for(power, floor):.3f};turn={held('turn_right') - held('turn_left')};"
            f"look={held('look_down') - held('look_up')};atk={held('attack')};jump={held('jump')};"
            f"draw={held('draw_weapon')};power={int(power)}\n")


def parse_grades(chunk: bytes) -> list[float]:
    """The gradients printed by the mod in a piece of openmw.log, oldest first."""
    return [clamp_grade(float(m.group(1))) for m in GRADE_LINE.finditer(chunk)]


async def state_loop(path: Path, floor: float = 15.0) -> None:
    """~20 Hz: rewrite the state file in place (the game indexes the path at start, so it must not be recreated)."""
    n = 0
    while True:
        n += 1
        fresh = time.time() - state["t_packet"] < 2.0 or state["simulate"]
        power = state["power"] if fresh else 0
        raw = set(state["raw"]) if time.time() - state["t_buttons"] < 1.5 else set()
        try:
            with open(path, "w") as f:
                f.write(state_line(n, power, raw, floor=floor))
        except OSError as e:
            if n % 100 == 1:
                log(f"cannot write {path}: {e}")
        await asyncio.sleep(0.05)


async def use_key(key_name: str) -> None:
    """Hold the game's use key while the Click's 'use' button is held."""
    keys.SCAN["use"] = USE_KEYS[key_name]
    down = False
    try:
        while True:
            want = BUTTONS["use"] in state["raw"] and time.time() - state["t_buttons"] < 1.5
            if want and not down:
                keys.key("use", True)
                down = True
            elif not want and down:
                keys.key("use", False)
                down = False
            await asyncio.sleep(0.03)
    finally:
        if down:
            keys.key("use", False)


async def log_tail(path: Path) -> None:
    """Follow openmw.log and turn the mod's gradient lines into the trainer's gradient."""
    pos = None
    warned = False
    while True:
        try:
            size = path.stat().st_size
            if pos is None or size < pos:        # first look, or the game restarted and truncated the log
                pos = size if pos is None else 0
            elif size > pos:
                with open(path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read(size - pos)
                pos = size
                grades = parse_grades(chunk)
                if grades:
                    state["game_grade"] = grades[-1]
                    state["t_udp"] = time.time()
            warned = False
        except (OSError, ValueError) as e:
            if not warned:
                log(f"openmw log {path}: {e}")
                warned = True
        await asyncio.sleep(0.2)
