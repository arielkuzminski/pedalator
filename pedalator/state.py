"""The one shared state of a running bridge, its log, and the riding modes.

Everything that talks to the outside (the trainer, the phone, the game, the dashboard) reads and writes
this module's ``state`` dict; the dashboard serves a snapshot of it.
"""
from __future__ import annotations

import collections
import time

state: dict = {
    "power": 0, "cadence": 0.0, "speed": 0.0, "distance": 0, "resistance": None, "hr": None,
    "grade": 0.0,            # what is sent to the trainer
    "game_grade": 0.0,       # last gradient reported by the game (before the riding mode scales it)
    "manual_grade": 0.0,     # the dashboard's slider
    "mode": "game",          # where the trainer's gradient comes from: "game" | "manual"
    "connected": False, "trainer_name": "-", "simulate": False, "ftp": 200,
    "t_packet": 0.0, "t_udp": 0.0, "t_cp": 0.0, "raw_hex": "", "cp_last": "-",
    "game_speed": 0.0, "pmax": 250, "keys": False, "keyset": "numpad",
    "buttons": [], "raw": [], "t_buttons": 0.0,
    "click_connected": False, "click_name": "-",   # the Zwift Click: read by the PC or by the phone page
    "trainer_rssi": None, "click_rssi": None,      # signal strength (dBm) when the PC last found each over Bluetooth
    "gain": 2.0,             # game throttle = rider power x gain / pmax  (easier riding)
    "difficulty": 0.4,       # share of the game's gradient the trainer is told
    "preset": "easy",
    "smooth": True,          # keep the gas for SMOOTH_HOLD s when the power dips under the floor (pedal strokes, a soft patch)
    "target": "keys",                # which game target runs: keys | openmw | udp
    "profile": None, "profile_id": None,   # the active profile (see profiles.py)
    "notice": "", "t_notice": 0.0,   # a short message for the rider, e.g. "difficulty:60" (shown for 3 s)
    "session": {"status": "idle"},   # the driver session (session.py): idle | starting | running | stopping | error
}

# riding mode -> (power gain, share of the game's gradient sent to the trainer)
PRESETS = {"easy": (2.0, 0.4), "medium": (1.4, 0.7), "real": (1.0, 1.0)}

MAX_GRADE = 15.0             # the D500 simulates up to 15 %; most smart trainers do about the same

history: collections.deque = collections.deque(maxlen=120)   # rider power, one sample a second
log_lines: collections.deque = collections.deque(maxlen=80)
stats = {"sum": 0.0, "n": 0, "max": 0}
t_start: float | None = None      # when the running session began (None: no session, so no elapsed time)


def reset_session() -> None:
    """Forget the last ride: live values, history and statistics. Called when a session starts and when it ends."""
    state.update(power=0, cadence=0.0, speed=0.0, distance=0, resistance=None, hr=None, grade=0.0, game_grade=0.0,
                 manual_grade=0.0, mode="game", connected=False, trainer_name="-", simulate=False,
                 t_packet=0.0, t_udp=0.0, t_cp=0.0, raw_hex="", cp_last="-", game_speed=0.0,
                 buttons=[], raw=[], t_buttons=0.0, click_connected=False, click_name="-", notice="", t_notice=0.0,
                 trainer_rssi=None, click_rssi=None)
    history.clear()
    stats.update(sum=0.0, n=0, max=0)
    forget_gas()


def start_clock(running: bool) -> None:
    global t_start
    t_start = time.time() if running else None


_tap = None


def set_tap(fn) -> None:
    """Install (or, with None, remove) a listener for the flow check (diag.py): ``fn(kind, t, *values)``."""
    global _tap
    _tap = fn


def tap(kind: str, *values) -> None:
    """Report an event to the flow check, with a monotonic timestamp. Costs one comparison when nobody listens."""
    if _tap is not None:
        _tap(kind, time.perf_counter(), *values)


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')}  {msg}"
    log_lines.append(line)
    print(line, flush=True)


def apply_preset(name: str) -> None:
    state["gain"], state["difficulty"] = PRESETS[name]
    state["preset"] = name


def set_notice(text: str) -> None:
    state["notice"] = text
    state["t_notice"] = time.time()


def current_notice() -> str:
    return state["notice"] if time.time() - state["t_notice"] < 3.0 else ""


def clamp_grade(g: float) -> float:
    return max(-MAX_GRADE, min(MAX_GRADE, g))


def effective_grade() -> float:
    """The gradient the trainer should simulate right now (also stored in ``state['grade']``)."""
    g = state["manual_grade"] if state["mode"] == "manual" else state["game_grade"] * state["difficulty"]
    g = clamp_grade(g)
    state["grade"] = g
    return g


SMOOTH_HOLD = 0.8            # seconds the gas outlasts a dip of the power under the floor, with ``state['smooth']``
_last_gas = {"power": 0.0, "t": -1e9}


def forget_gas() -> None:
    """Drop the held gas: after this, no power means no gas (a ride is over, so nothing may keep the game moving)."""
    _last_gas.update(power=0.0, t=-1e9)


def throttle_for(power: float, floor: float = 15.0) -> float:
    """0..1 'gas' for a rider power: coasting below ``floor`` watts, full at pmax / gain.

    A trainer reports the power of the moment, which dips to nothing between pedal strokes and when you ease off.
    With ``state['smooth']`` a dip shorter than SMOOTH_HOLD keeps the last gas; a longer one (you stopped) lets go.
    """
    if state["smooth"]:
        now = time.monotonic()
        if power >= floor:
            _last_gas.update(power=power, t=now)
        elif now - _last_gas["t"] < SMOOTH_HOLD:
            power = _last_gas["power"]
    if power < floor:
        return 0.0
    return min(1.0, power * state["gain"] / state["pmax"])


def snapshot() -> dict:
    """What the dashboard shows: the state plus ages, history and the log."""
    effective_grade()                      # the grade shown is the one in force right now, not a second ago
    now = time.time()
    s = dict(state)
    s["age_packet"] = round(now - s["t_packet"], 1) if s["t_packet"] else None
    s["age_udp"] = round(now - s["t_udp"], 1) if s["t_udp"] else None
    s["age_cp"] = round(now - s["t_cp"], 1) if s["t_cp"] else None
    s["notice"] = current_notice()
    s["profile"] = None                    # (the Controls page asks /profile for it)
    for k in ("t_packet", "t_udp", "t_cp", "t_notice"):
        s.pop(k)
    s["history"] = list(history)
    s["log"] = list(log_lines)
    s["avg_power"] = round(stats["sum"] / stats["n"]) if stats["n"] else 0
    s["max_power"] = stats["max"]
    s["elapsed"] = int(now - t_start) if t_start else 0
    s["distance"] = int(s["distance"])
    return s
