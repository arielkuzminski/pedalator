"""The driver session: everything that runs while you ride (trainer, Click, the game's loops), started and stopped
on demand.

The dashboard lives for as long as the program does. A *session* is what you start from its Start page (or at once from
the command line): it picks the profile, reads the trainer and the Click, and runs the loops of the game's target.
Stopping it releases the Bluetooth devices, the game's port, the phone servers and any held keys, so another game can
be started without restarting the program.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from . import profiles
from .state import apply_preset, log, reset_session, start_clock, state

TRAINER_SOURCES = ("pc", "phone")
CLICK_SOURCES = ("auto", "pc", "phone", "off")


class SessionError(Exception):
    """A session could not start; ``errors`` are plain sentences for the person at the screen."""

    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


@dataclass
class SessionConfig:
    profile: str | None = None            # a profile id, or the path of a .json profile
    target: str | None = None             # keys | openmw | udp; None = the profile's own target
    trainer: str | None = None            # pc | phone (None: phone with ``remote``, else pc)
    click: str = "auto"
    remote: bool = False
    simulate: bool = False
    address: str | None = None
    ip: str | None = None
    data_dir: Path | None = None
    phone_port: int = 8766
    ca_port: int = 8767
    keys: bool = False                    # (keys target) really press keys
    keyset: str | None = None
    openmw_state: Path | None = None
    openmw_log: Path | None = None
    openmw_use_key: str | None = None
    udp_out: str = "127.0.0.1:27200"
    game_port: int = 27100
    mode: str | None = None
    gain: float | None = None
    difficulty: float | None = None
    pmax: float | None = None
    ftp: int | None = None

    @classmethod
    def from_args(cls, args) -> SessionConfig:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in vars(args).items() if k in names})

    def merged(self, **changes) -> SessionConfig:
        """This config with the fields the launcher chose (None means 'keep what the command line said')."""
        return dataclasses.replace(self, **{k: v for k, v in changes.items() if v is not None})


def resolve_sources(trainer: str | None, click: str, remote: bool, simulate: bool) -> tuple[str, str]:
    """Who reads the trainer ('pc' or 'phone') and who reads the Click ('pc', 'phone' or 'off').

    ``--remote`` means the phone reads the trainer; ``--click auto`` follows the trainer (and is off for a
    simulated rider unless a phone is in play).
    """
    t = trainer or ("phone" if remote else "pc")
    if click == "auto":
        click = "phone" if t == "phone" else ("off" if simulate else "pc")
    return t, click


def resolve_profile(cfg: SessionConfig) -> dict:
    """The profile to ride with: a .json file, a profile id, ``keyset``, or the default of the target."""
    choice = cfg.profile
    if choice and choice.lower().endswith(".json") and Path(choice).is_file():
        try:
            profile, errors = profiles.validate(json.loads(Path(choice).read_text(encoding="utf-8")), fill_keys=True)
        except (OSError, ValueError) as e:
            raise SessionError(f"{choice}: {e}") from e
        if errors:
            raise SessionError([f"{choice}: {e}" for e in errors])
    else:
        target = cfg.target or "keys"
        choice = choice or ("generic-wasd" if target == "keys" and cfg.keyset == "wasd" else profiles.DEFAULT_ID[target])
        try:
            profile = profiles.load(choice)
        except KeyError:
            raise SessionError(f"no profile '{choice}'. Available: " +
                               ", ".join(p["id"] for p in profiles.list_profiles())) from None
        except ValueError as e:
            raise SessionError(str(e)) from e
    if cfg.target and profile["target"] != cfg.target:
        raise SessionError(f"profile '{profile['id']}' is for the '{profile['target']}' target; "
                           f"use --target {profile['target']}")
    return profile


def check_udp_out(text: str) -> tuple[str, int]:
    host, _, port = text.rpartition(":")
    if not port.isdigit() or not 0 < int(port) < 65536:
        raise SessionError(f"'{text}' is not a HOST:PORT address (for example 127.0.0.1:27200)")
    return host or "127.0.0.1", int(port)


class Runtime:
    """Starts and stops the one session of this program. All its coroutines run on the program's event loop."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.base = SessionConfig()           # what the command line said; the Start page's choices go on top of it
        self.cfg: SessionConfig | None = None
        self._lock: asyncio.Lock | None = None
        self._tasks: list[asyncio.Task] = []
        self._transport = None
        self._servers: list = []
        self._outputs: dict = {}

    # ------------------------------------------------------------------ plumbing
    def attach(self, loop: asyncio.AbstractEventLoop, base: SessionConfig | None = None) -> None:
        self.loop = loop
        self.base = base or SessionConfig()
        self._lock = asyncio.Lock()

    @property
    def status(self) -> str:
        return state["session"]["status"]

    def _set(self, status: str, error: str | None = None, **info) -> None:
        keep = {k: v for k, v in state["session"].items() if k not in ("status", "error")} if status != "idle" else {}
        state["session"] = {"status": status, "error": error, **keep, **info}

    def call(self, coro, timeout: float = 30.0):
        """Run ``coro`` on the program's loop from another thread (the dashboard's) and wait for the result."""
        if self.loop is None:
            coro.close()
            raise SessionError("the driver is not running in this process")
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    # ------------------------------------------------------------------ start
    async def start(self, cfg: SessionConfig) -> None:
        async with self._lock:
            if self.status in ("starting", "running", "stopping", "error"):
                raise SessionError("a session is already running; stop it first")
            self._set("starting")
            try:
                await self._start(cfg)
            except BaseException:
                await self._release()
                self._set("idle")
                raise

    async def _start(self, cfg: SessionConfig) -> None:
        from . import keys as keyout
        from .certs import lan_ip
        from .difficulty import difficulty_loop
        from .loops import GameUdp, console_status, sampler
        from .paths import find_openmw_log, find_openmw_state, user_data_dir
        from .phone_server import start_phone_servers

        if cfg.trainer not in (None, *TRAINER_SOURCES) or cfg.click not in CLICK_SOURCES:
            raise SessionError("the trainer must be 'pc' or 'phone' and the Click 'auto', 'pc', 'phone' or 'off'")
        profile = resolve_profile(cfg)
        target = cfg.target or profile["target"]
        trainer, click = resolve_sources(cfg.trainer, cfg.click, cfg.remote, cfg.simulate)
        openmw_state = openmw_log = None
        if target == "openmw":
            openmw_state = cfg.openmw_state or find_openmw_state()
            openmw_log = cfg.openmw_log or find_openmw_log()
            if not openmw_state or not openmw_log:
                raise SessionError("OpenMW: cannot find the mod's state file or openmw.log. Install the mod first "
                                   "(pedalator install openmw) or give --openmw-state and --openmw-log.")
        udp_host = udp_port = None
        if target == "udp":
            udp_host, udp_port = check_udp_out(cfg.udp_out)

        self.cfg = cfg
        reset_session()
        start_clock(True)
        state["target"] = target
        if cfg.openmw_use_key:
            profile["keys"]["use"] = {"e": "KeyE", "f": "KeyF", "space": "Space", "enter": "Enter"}[cfg.openmw_use_key]
        state["profile"] = None                       # so the profile's own ride settings apply afresh
        profiles.apply(profile)
        state.update(keys=cfg.keys, keyset=profile["id"])
        if cfg.mode:
            apply_preset(cfg.mode)
        if cfg.pmax is not None:
            state["pmax"] = cfg.pmax
        if cfg.ftp is not None:
            state["ftp"] = cfg.ftp
        if cfg.gain is not None:
            state["gain"], state["preset"] = cfg.gain, "custom"
        if cfg.difficulty is not None:
            state["difficulty"], state["preset"] = cfg.difficulty, "custom"
        log(f"profile: {profile['name']} ({profile['id']})")

        if trainer == "phone":
            state.update(trainer_name="(phone)", simulate=False)
        if "phone" in (trainer, click):
            _, self._servers = start_phone_servers(cfg.ip or lan_ip(), cfg.data_dir or user_data_dir(), cfg.phone_port,
                                                   cfg.ca_port, accept={"trainer": trainer == "phone",
                                                                        "click": click == "phone"})
        log(f"trainer: {trainer if not cfg.simulate else 'simulated'} · Zwift Click: {click}")
        try:
            self._transport, _ = await self.loop.create_datagram_endpoint(
                GameUdp, local_addr=("127.0.0.1", cfg.game_port))
        except OSError as e:
            raise SessionError(f"cannot listen for the game on UDP {cfg.game_port}: {e}") from e

        coros = [sampler(), console_status(), difficulty_loop()]
        if target == "openmw":
            from .targets import openmw
            log(f"OpenMW: state file {openmw_state}, log {openmw_log}")
            self._outputs["openmw_state"] = openmw_state
            coros += [openmw.state_loop(openmw_state), openmw.config_loop(openmw_state.with_name("config.txt")),
                      openmw.use_key(), openmw.log_tail(openmw_log)]
        elif target == "udp":
            from .targets import udp
            log(f"UDP target: JSON datagrams to {udp_host}:{udp_port}; the game answers on UDP {cfg.game_port}")
            self._outputs["udp"] = (udp_host, udp_port)
            coros.append(udp.send_loop(udp_host, udp_port))
        elif cfg.keys:
            log("driving keys go to the window in front: throttle by power, steering/brake by Zwift Click "
                f"(profile {profile['id']})")
            coros += [keyout.throttle_loop(), keyout.buttons_loop()]
        if click == "pc":
            from .click import click_loop
            coros.append(click_loop())
        if cfg.simulate:
            from .simulate import simulate
            coros.append(simulate())
        elif trainer == "pc":
            from .ble import trainer_loop
            coros.append(trainer_loop(cfg.address))

        self._tasks = [asyncio.create_task(c) for c in coros]
        for t in self._tasks:
            t.add_done_callback(self._task_done)
        self._set("running", None, profile_id=profile["id"], profile_name=profile["name"], target=target,
                  trainer="simulated" if cfg.simulate else trainer, click=click, started=time.time())

    def _task_done(self, task: asyncio.Task) -> None:
        if task.cancelled() or task.exception() is None:
            return
        e = task.exception()
        log(f"a part of the session stopped: {type(e).__name__}: {e}")
        if self.status == "running":
            self._set("error", f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------ stop
    async def stop(self) -> None:
        async with self._lock:
            if self.status == "idle":
                return
            self._set("stopping")
            await self._release()
            self._set("idle")
            log("session stopped")

    async def _release(self) -> None:
        """Give everything back: tasks (and with them Bluetooth and held keys), ports, servers, the game's outputs."""
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)       # wait for bleak to disconnect
        self._tasks = []
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            await asyncio.sleep(0)                                          # let the socket really close
        servers, self._servers = self._servers, []
        for srv in servers:
            await self.loop.run_in_executor(None, _close_server, srv)
        self._zero_outputs()
        reset_session()
        start_clock(False)

    def _zero_outputs(self) -> None:
        """Tell the game that nobody is pedalling any more (the last message would otherwise stay in force)."""
        outputs, self._outputs = self._outputs, {}
        if "openmw_state" in outputs:
            from .targets import openmw
            try:
                Path(outputs["openmw_state"]).write_text(openmw.state_line(0, 0, set()))
            except OSError:
                pass
        if "udp" in outputs:
            from .targets import udp
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.sendto(udp.packet(0, 0, set()), outputs["udp"])
            except OSError:
                pass


def _close_server(srv) -> None:
    try:
        srv.shutdown()
        srv.server_close()
    except OSError:
        pass


runtime = Runtime()
