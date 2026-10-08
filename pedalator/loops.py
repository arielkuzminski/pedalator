"""Small background loops: gradient from a game over UDP, session statistics, console status."""
from __future__ import annotations

import asyncio
import socket
import time

from .state import clamp_grade, effective_grade, history, state, stats

UDP_PORT = 27100          # games / plugins send "grade=<percent>;speed=<km/h>" here (localhost only)
POWER_PORT = 27101        # the current rider power goes out here, for a game plugin that can listen


class GameUdp(asyncio.DatagramProtocol):
    """``grade=4.2;speed=18`` from a game plugin (the openOMSI Lua plugin sends this)."""

    def datagram_received(self, data, addr):
        try:
            kv = dict(p.split("=") for p in data.decode().split(";"))
            state["game_grade"] = clamp_grade(float(kv["grade"]))
            state["game_speed"] = float(kv.get("speed", 0))
            state["t_udp"] = time.time()
        except Exception:
            pass


async def sampler() -> None:
    """Once a second: the power history and the session's average/max."""
    while True:
        await asyncio.sleep(1.0)
        history.append(state["power"])
        if state["power"] > 5:
            stats["sum"] += state["power"]
            stats["n"] += 1
            stats["max"] = max(stats["max"], state["power"])


async def console_status() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        effective_grade()
        print(f"grade {state['grade']:5.1f}%  P {state['power']:4d} W  cad {state['cadence']:5.1f}"
              f"  v {state['speed']:5.1f} km/h", flush=True)
        try:
            sock.sendto(f"power={state['power']}".encode(), ("127.0.0.1", POWER_PORT))
        except OSError:
            pass
        await asyncio.sleep(1.0)
