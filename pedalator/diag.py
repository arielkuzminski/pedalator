"""The flow check: is the signal from the pedals to the game smooth, and if not, which stage breaks it?

While it records, four stages are timed with one clock:

1. ``ble``   the trainer's notifications arriving at this PC (Bluetooth),
2. ``loop``  Pedalator's own throttle loop (it should tick every 50 ms; a stalled loop makes a ragged signal),
3. ``keys``  the key presses Pedalator sends (the throttle key is pulsed: the share of time it is down is the "gas"),
4. ``os``    the same key as Windows delivers it (a low-level keyboard hook), which is what a game or a text box gets.

``analyze`` turns the recorded events into numbers and one verdict. Run it from the dashboard (Ride tab, "Flow check")
or, without a trainer, ``python -m pedalator.diag`` (a synthetic rider presses a harmless key).
"""
from __future__ import annotations

import asyncio
import bisect
import sys
import threading
import time

from . import state as st

LOOP_PERIOD = 0.05            # keys.throttle_loop's period
HOLE = 0.12                   # the key up this long while gas is wanted is a hole in the signal (s)
GAP = 0.5                     # trainer notifications further apart than this, while pedalling, are a gap (s)
WINDOW = 0.25                 # for comparing the gas that was asked for with the one that was sent (s)


# ---------------------------------------------------------------------------------------------- the OS's view
class KeyboardHook:
    """A low-level keyboard hook on its own thread: the events Windows delivers for one scan code. Windows only."""

    def __init__(self, scan: int, sink) -> None:
        self.scan, self.sink = scan, sink
        self.thread_id = 0
        self.ready = threading.Event()
        self.thread: threading.Thread | None = None
        self.error = ""

    def start(self) -> bool:
        if sys.platform != "win32":
            self.error = "key delivery can only be measured on Windows"
            return False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(3)
        return not self.error

    def stop(self) -> None:
        if self.thread is None:
            return
        import ctypes
        ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)    # WM_QUIT
        self.thread.join(2)
        self.thread = None

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        lresult = ctypes.c_ssize_t
        proc_t = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KBD(ctypes.Structure):
            _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_void_p)]

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, proc_t, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = lresult
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

        def proc(code, wparam, lparam):
            if code >= 0 and wparam in (0x100, 0x101, 0x104, 0x105):          # WM_(SYS)KEYDOWN / KEYUP
                k = ctypes.cast(lparam, ctypes.POINTER(KBD)).contents
                if k.scan == self.scan:
                    self.sink(time.perf_counter(), wparam in (0x100, 0x104), bool(k.flags & 0x10))   # LLKHF_INJECTED
            return user32.CallNextHookEx(None, code, wparam, lparam)

        cb = proc_t(proc)                                                    # (kept alive for as long as the hook is)
        self.thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(13, cb, kernel32.GetModuleHandleW(None), 0)          # WH_KEYBOARD_LL
        if not hook:
            self.error = f"could not install the keyboard hook (error {ctypes.GetLastError()})"
            self.ready.set()
            return
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)


# ------------------------------------------------------------------------------------------------ analysis
def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def spread(intervals: list[float]) -> dict:
    """Milliseconds: the usual, the bad and the worst interval."""
    return {"p50": round(pct(intervals, 0.5) * 1000), "p95": round(pct(intervals, 0.95) * 1000),
            "max": round(max(intervals, default=0.0) * 1000)}


def _value_at(series: list[tuple], t: float, default=0.0):
    """The last value of a time-ordered ``(time, value)`` series at or before ``t``."""
    i = bisect.bisect_right(series, t, key=lambda e: e[0])
    return series[i - 1][1] if i else default


def _down_share(keys: list[tuple[float, bool]], t0: float, t1: float) -> float:
    """The share of [t0, t1] during which the key was down."""
    down, last, total = _value_at(keys, t0, False), t0, 0.0
    for t, d in keys:
        if t <= t0:
            continue
        if t >= t1:
            break
        total += (t - last) if down else 0.0
        last, down = t, d
    total += (t1 - last) if down else 0.0
    return total / (t1 - t0)


def analyze(ev: dict, seconds: float, slot: str = "throttle", os_ok: bool = True) -> dict:
    """``ev``: kind -> list of tuples, all starting with a time from ``time.perf_counter``:
    ble (t, power), duty (t, duty), key (t, slot, down), os (t, down, injected)."""
    out: dict = {"seconds": round(seconds, 1)}

    # 1. Bluetooth: gaps between notifications while the rider is pedalling
    ble = ev.get("ble", [])
    gaps = [b[0] - a[0] for a, b in zip(ble, ble[1:], strict=False) if a[1] > 0 and b[1] > 0]
    out["ble"] = {"packets": len(ble), "pedalling": len(gaps), **spread(gaps), "over_500ms": sum(g > GAP for g in gaps),
                  "over_1s": sum(g > 1.0 for g in gaps), "power_max": max((p for _, p in ble), default=0)}

    # 2. Pedalator's loop: should tick every 50 ms
    duty = ev.get("duty", [])
    ticks = [b[0] - a[0] for a, b in zip(duty, duty[1:], strict=False)]
    out["loop"] = {"ticks": len(duty), **spread(ticks), "over_100ms": sum(t > 0.1 for t in ticks),
                   "over_200ms": sum(t > 0.2 for t in ticks)}

    # 3. the key presses sent: holes while gas was wanted, the longest hold, the gas sent against the gas asked for
    sent = [(e[0], e[2]) for e in ev.get("key", []) if e[1] == slot]
    t_end = max([e[0] for e in duty] + [e[0] for e in sent] or [0.0])
    holes, up_since = [], None
    for t, down in sent:
        if not down and up_since is None:
            up_since = t
        elif down and up_since is not None:
            if t - up_since > HOLE and _value_at(duty, up_since) > 0 and _value_at(duty, t) > 0:
                holes.append(t - up_since)
            up_since = None
    held, down_since = [], None
    for t, down in sent:
        if down and down_since is None:
            down_since = t
        elif not down and down_since is not None:
            held.append(t - down_since)
            down_since = None
    if down_since is not None:
        held.append(t_end - down_since)
    errs = []
    if duty and sent:
        t = duty[0][0]
        while t + WINDOW <= t_end:
            asked = sum(_value_at(duty, t + i * 0.01) for i in range(int(WINDOW / 0.01))) / int(WINDOW / 0.01)
            errs.append(abs(_down_share(sent, t, t + WINDOW) - asked))
            t += WINDOW
    out["keys"] = {"presses": sum(1 for _, d in sent if d), "holes": len(holes),
                   "worst_hole_ms": round(max(holes, default=0.0) * 1000),
                   "longest_hold_ms": round(max(held, default=0.0) * 1000),
                   "gas_error": round(sum(errs) / len(errs), 2) if errs else 0.0}

    # 4. what Windows delivered: the delay from our SendInput to the hook, and the gaps between key-down events
    delivered = ev.get("os", [])
    latency, j = [], 0
    for t, down, _injected in delivered:
        while j < len(sent) and (sent[j][1] != down or sent[j][0] > t):
            if sent[j][0] > t:
                break
            j += 1
        if j < len(sent) and sent[j][1] == down and sent[j][0] <= t:
            latency.append(t - sent[j][0])
            j += 1
    downs = [t for t, d, _ in delivered if d]
    os_gaps = [b - a for a, b in zip(downs, downs[1:], strict=False) if _value_at(duty, a) > 0 and _value_at(duty, b) > 0]
    out["os"] = {"available": os_ok, "events": len(delivered), "downs": len(downs),
                 "latency_p95_ms": round(pct(latency, 0.95) * 1000), "latency_max_ms": round(max(latency, default=0.0) * 1000),
                 "worst_gap_ms": round(max(os_gaps, default=0.0) * 1000)}
    out["verdict"] = verdict(out)
    return out


def verdict(r: dict) -> dict:
    """One finding, with a code the dashboard translates: the first stage that is broken, from the pedals onward."""
    ble, loop, keys, osv = r["ble"], r["loop"], r["keys"], r["os"]
    if ble["pedalling"] < 5 and loop["ticks"] < 20:
        return {"code": "no_data", "stage": "-"}
    if ble["pedalling"] >= 5 and (ble["over_1s"] > 0 or ble["over_500ms"] > 2):
        return {"code": "ble", "stage": "ble"}
    if loop["ticks"] and (loop["over_200ms"] > 0 or loop["max"] > 150):
        return {"code": "loop", "stage": "loop"}
    if keys["holes"] > 0 and keys["worst_hole_ms"] > 200:
        return {"code": "keys", "stage": "keys"}
    if osv["available"] and osv["events"] and (osv["latency_max_ms"] > 150):
        return {"code": "os_latency", "stage": "os"}
    return {"code": "ok", "stage": "-"}


# ---------------------------------------------------------------------------------------------- recording
class Probe:
    """One recording. ``status``: idle | recording | done."""

    def __init__(self) -> None:
        self.status, self.seconds, self.t0 = "idle", 0.0, 0.0
        self.report: dict | None = None
        self.error = ""
        self.ev: dict = {}
        self.task: asyncio.Task | None = None

    def view(self) -> dict:
        elapsed = min(self.seconds, time.perf_counter() - self.t0) if self.status == "recording" else self.seconds
        return {"status": self.status, "seconds": self.seconds, "elapsed": round(elapsed, 1),
                "report": self.report, "error": self.error}

    def _tap(self, kind: str, t: float, *values) -> None:
        self.ev.setdefault(kind, []).append((t, *values))

    async def record(self, seconds: float, slot: str = "throttle") -> dict:
        from . import keys
        self.status, self.seconds, self.report, self.error, self.ev = "recording", seconds, None, "", {}
        self.t0 = time.perf_counter()
        hook = KeyboardHook(keys.BINDINGS[slot][0], lambda t, down, inj: self._tap("os", t, down, inj))
        os_ok = hook.start()
        if not os_ok:
            self.error = hook.error
        st.set_tap(self._tap)
        try:
            await asyncio.sleep(seconds)
        finally:
            st.set_tap(None)
            hook.stop()
            self.report = analyze(self.ev, seconds, slot, os_ok)
            self.status = "done"
        return self.report


probe = Probe()


def start(seconds: float) -> None:
    """Begin a recording in the background (on the running loop)."""
    if probe.status == "recording":
        raise RuntimeError("a recording is already running")
    probe.status, probe.seconds, probe.t0 = "recording", seconds, time.perf_counter()
    probe.task = asyncio.get_running_loop().create_task(_background(seconds))     # (held: or it could be collected)


async def _background(seconds: float) -> None:
    try:
        await probe.record(seconds)
    except Exception as e:
        probe.error, probe.status = f"{type(e).__name__}: {e}", "done"


# -------------------------------------------------------------------------------- without a trainer: a synthetic rider
async def synthetic(seconds_per_step: float = 6.0, key: str = "F9") -> dict:
    """A rider at 60 W (part gas), 90 W (more), 140 W (the key held down) and 90 W again, pressing ``key``."""
    from . import keys
    keys.apply_keys({"throttle": key})
    steps = (60, 90, 140, 90)
    loop_task = asyncio.create_task(keys.throttle_loop())

    async def rider():
        for p in steps:
            st.state["power"] = p
            await asyncio.sleep(seconds_per_step)
    # (the ble stage is skipped: there is no trainer, so only the loop, the keys and the OS are measured)
    rid = asyncio.create_task(rider())
    p = Probe()
    try:
        return await p.record(seconds_per_step * len(steps))
    finally:
        loop_task.cancel()
        rid.cancel()
        await asyncio.gather(loop_task, rid, return_exceptions=True)
        st.state["power"] = 0


def main() -> None:
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python -m pedalator.diag",
                                 description="Measure the key pulses without a trainer (presses a harmless key, F9 by default).")
    ap.add_argument("--step", type=float, default=6.0, help="seconds per power step (60, 90, 140, 90 W)")
    ap.add_argument("--key", default="F9", help="the key to press")
    a = ap.parse_args()
    print(json.dumps(asyncio.run(synthetic(a.step, a.key)), indent=2))


if __name__ == "__main__":
    main()
