"""A made-up rider, for trying the dashboard and a game without a trainer: ``pedalator --simulate``."""
from __future__ import annotations

import asyncio
import math
import time

from .state import effective_grade, state


async def simulate() -> None:
    """Sprints and rests; speed follows power and the gradient."""
    state.update(connected=True, trainer_name="SIMULATED trainer", simulate=True)
    t0 = time.time()
    last = t0
    while True:
        now = time.time()
        t = now - t0
        dt, last = now - last, now
        resting = (t % 45) > 36                        # a pause every 45 s: the dashboard shows "idle"
        p = 0 if resting else max(0, 170 + 110 * math.sin(t / 7) + 25 * math.sin(t * 1.7))
        p *= max(0.35, 1 - 0.025 * effective_grade())  # harder uphill
        state["power"] = int(p)
        state["cadence"] = 0.0 if resting else round(88 + 9 * math.sin(t / 5), 1)
        target = (p / 11.0) ** 0.8 * 3.0 if p else 0.0
        state["speed"] = round(state["speed"] + (target - state["speed"]) * min(1, dt * 0.6), 2)
        state["distance"] += state["speed"] / 3.6 * dt
        state["resistance"] = int(40 + 3 * state["grade"])
        state["hr"] = int(95 + p / 3)
        state["raw_hex"] = "(simulated)"
        state["t_packet"] = now
        await asyncio.sleep(0.1)
