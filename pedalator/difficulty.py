"""Zwift Click + and −: harder or easier hills without leaving the saddle."""
from __future__ import annotations

import asyncio
import time

from . import profiles
from .state import log, set_notice, state

STEP = 0.1              # share of the game's hills, per press
FIRST_REPEAT = 0.5      # s of holding before it repeats
REPEAT = 0.25           # s between repeats while held


def stepped(value: float, direction: int) -> float:
    """``value`` moved one step up (+1) or down (−1), kept between 0 and 1."""
    return round(min(1.0, max(0.0, value + direction * STEP)), 2)


def apply_step(direction: int) -> None:
    """Change the difficulty (the share of the game's hills the trainer simulates) and tell the rider."""
    old = state["difficulty"]
    new = stepped(old, direction)
    if new != old:
        state["difficulty"] = new
        state["preset"] = "custom"
        log(f"difficulty {round(new * 100)} % (Click {'+' if direction > 0 else '-'})")
    set_notice(f"difficulty:{round(new * 100)}")


async def difficulty_loop() -> None:
    """Watch the buttons the active profile binds to ``difficulty_up`` / ``difficulty_down`` (+ and − by default)."""
    due: dict[str, float | None] = {"difficulty_up": None, "difficulty_down": None}
    while True:
        now = time.time()
        raw = set(state["raw"]) if now - state["t_buttons"] < 1.5 else set()
        for name, direction in (("difficulty_up", 1), ("difficulty_down", -1)):
            if not profiles.held(state["target"], name, raw):
                due[name] = None
            elif due[name] is None or now >= due[name]:
                first = due[name] is None
                apply_step(direction)
                due[name] = now + (FIRST_REPEAT if first else REPEAT)
        await asyncio.sleep(0.05)
