"""Generic target for any game whose scripts can use UDP sockets (a mod, a plugin, a script extender).

Pedalator sends one JSON object per datagram ~20 times a second to ``host:port``::

    {"n": 1234, "power": 143, "move": 0.57, "cadence": 88.0, "speed": 24.1, "turn": -1, "look": 0,
     "buttons": ["LEFT", "B"], "grade_in_use": 2.4}

and listens on UDP 127.0.0.1:27100 for ``grade=<percent>;speed=<km/h>`` (the same line the openOMSI plugin sends).
"""
from __future__ import annotations

import asyncio
import json
import socket
import time

from ..state import state, throttle_for


def packet(n: int, power: float, raw: set[str]) -> bytes:
    held = lambda b: 1 if b in raw else 0                              # noqa: E731
    return json.dumps({
        "n": n, "power": int(power), "move": round(throttle_for(power), 3),
        "cadence": state["cadence"], "speed": state["speed"],
        "turn": held("RIGHT") - held("LEFT"), "look": held("DOWN") - held("UP"),
        "buttons": sorted(raw), "grade_in_use": round(state["grade"], 2),
    }).encode()


async def send_loop(host: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    n = 0
    while True:
        n += 1
        fresh = time.time() - state["t_packet"] < 2.0 or state["simulate"]
        raw = set(state["raw"]) if time.time() - state["t_buttons"] < 1.5 else set()
        try:
            sock.sendto(packet(n, state["power"] if fresh else 0, raw), (host, port))
        except OSError:
            pass
        await asyncio.sleep(0.05)
