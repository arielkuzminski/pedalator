"""OpenMW (Morrowind): the Lua mod in ``data/openmw/Pedalator`` reads ``pedalator/state.txt`` and ``config.txt``; the
gradient comes back through the game's log (the mod prints ``PEDALATOR grade=<percent>``).

What each Click button does, and the game's *use* key, come from the active profile (``profiles.py``). Pedalator's one
key press here is "use" (open / take / talk): OpenMW has no Lua call for "use what I look at".
"""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from .. import keys, profiles
from ..state import clamp_grade, log, state, throttle_for

GRADE_LINE = re.compile(rb"PEDALATOR grade=(-?[0-9.]+)")


def state_line(n: int, power: float, raw: set[str], floor: float | None = None) -> str:
    """One line for the mod's player script. ``move`` is 0..1, ``turn`` +1 is right, ``look`` +1 is down."""
    def held(action: str) -> int:
        return 1 if profiles.held("openmw", action, raw) else 0

    return (f"n={n};move={throttle_for(power, floor):.3f};turn={held('turn_right') - held('turn_left')};"
            f"look={held('look_down') - held('look_up')};atk={held('attack')};jump={held('jump')};"
            f"draw={held('draw_weapon')};power={int(power)};diff={round(state['difficulty'] * 100)}\n")


def config_line(options: dict | None = None) -> str:
    """The mod's tuning, from the active profile's options (the mod reads ``config.txt`` about once a second)."""
    o = options if options is not None else profiles.current("openmw")["options"]
    return (f"turn_rate={o['turn_rate']};pitch_rate={o['pitch_rate']};run_above={o['run_above']};"
            f"speed_attr={1 if o['use_speed_attribute'] else 0};speed_boost={o['speed_boost']}\n")


def parse_grades(chunk: bytes) -> list[float]:
    """The gradients printed by the mod in a piece of openmw.log, oldest first."""
    return [clamp_grade(float(m.group(1))) for m in GRADE_LINE.finditer(chunk)]


async def state_loop(path: Path, floor: float | None = None) -> None:
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


async def config_loop(path: Path) -> None:
    """Keep the mod's ``config.txt`` equal to the active profile's options (written when they change)."""
    written = None
    while True:
        line = config_line()
        if line != written:
            try:
                with open(path, "w") as f:
                    f.write(line)
                written = line
            except OSError as e:
                log(f"cannot write {path}: {e} (an older install without config.txt? run: pedalator install openmw)")
                written = line
        await asyncio.sleep(0.5)


async def use_key() -> None:
    """Hold the game's *use* key (the profile's ``keys.use``) while the button bound to *use* is held."""
    down = False
    try:
        while True:
            raw = state["raw"] if time.time() - state["t_buttons"] < 1.5 else ()
            want = profiles.held("openmw", "use", raw)
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
