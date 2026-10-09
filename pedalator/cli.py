"""Command line: ``python -m pedalator`` runs the bridge; ``install`` and ``build-bike`` set up the games."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import __version__
from .session import resolve_sources  # noqa: F401  (kept here: tests and callers import it from the CLI)
from .state import PRESETS, log


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pedalator",
        description="Ride games with your smart trainer. Run without a sub-command to open the dashboard and pick a game.",
        epilog="Other commands:  pedalator install openmw|openomsi   pedalator build-bike   pedalator new-game   "
               "pedalator profile list|show|export|import|delete   (see --help of each)")
    ap.add_argument("--version", action="version", version=f"pedalator {__version__}")

    src = ap.add_argument_group("where the rider data comes from")
    src.add_argument("--remote", action="store_true",
                     help="phone mode: a phone or laptop with Web Bluetooth reads the trainer and the Click "
                          "(for PCs without BLE); shorthand for --trainer phone")
    src.add_argument("--trainer", choices=("pc", "phone"),
                     help="who reads the trainer: this PC's Bluetooth, or a phone/laptop page (default: pc, "
                          "or phone with --remote)")
    src.add_argument("--click", choices=("auto", "pc", "phone", "off"), default="auto",
                     help="who reads the Zwift Click: pc, phone (a phone/laptop page), off; auto = the same as the "
                          "trainer. Mix them, e.g.  --trainer pc --click phone")
    src.add_argument("--simulate", action="store_true", help="no trainer: a made-up rider (try the dashboard or a game)")
    src.add_argument("--address", help="Bluetooth address of the trainer (default: scan for the first FTMS trainer)")
    src.add_argument("--ip", help="this PC's LAN address for the phone certificate (default: autodetect)")
    src.add_argument("--data-dir", type=Path, help="where certificates and the phone token are kept")
    src.add_argument("--phone-port", type=int, default=8766, help="(phone mode) HTTPS port for the phone page (default 8766)")
    src.add_argument("--ca-port", type=int, default=8767, help="(phone mode) HTTP port that serves the certificate (default 8767)")

    game = ap.add_argument_group("the game")
    game.add_argument("--target", choices=("keys", "openmw", "udp"),
                      help="keys: press the game's driving keys | openmw: Morrowind via the OpenMW mod | "
                           "udp: JSON datagrams for scripted games (default: the profile's, else keys)")
    game.add_argument("--launcher", action="store_true",
                      help="only open the dashboard and choose the game there (the default when no game or rider is given)")
    game.add_argument("--keys", action="store_true",
                      help="(keys target) actually press keys; without it nothing is typed into the game")
    game.add_argument("--profile",
                      help="a profile id (see `pedalator profile list`) or a .json file: what the Click buttons do, "
                           "which keys are pressed, how it rides. Default: morrowind / omsi / generic-udp by target")
    game.add_argument("--keyset", choices=("numpad", "wasd"),
                      help="(keys target) shortcut for --profile: numpad = OMSI's own keys, wasd = W A S D")
    game.add_argument("--openmw-state", type=Path, help="state.txt of the OpenMW mod (default: found in openmw.cfg)")
    game.add_argument("--openmw-log", type=Path, help="openmw.log (default: next to openmw.cfg)")
    game.add_argument("--openmw-use-key", choices=("e", "f", "space", "enter"),
                      help="the game's key for open / take / talk (overrides the profile's)")
    game.add_argument("--udp-out", default="127.0.0.1:27200", metavar="HOST:PORT",
                      help="(udp target) where the JSON datagrams go")

    feel = ap.add_argument_group("how it rides")
    feel.add_argument("--mode", choices=sorted(PRESETS),
                      help="riding mode at start: easy | medium | real (default: the profile's, else easy)")
    feel.add_argument("--gain", type=float, help="game throttle = power x gain / pmax (default: from the mode)")
    feel.add_argument("--difficulty", type=float,
                      help="share of the game's hills the trainer simulates, 0..1 (default: from the mode)")
    feel.add_argument("--pmax", type=float, help="watts that mean full throttle at gain 1 (default 250)")
    feel.add_argument("--ftp", type=int, help="your FTP in watts, for the dashboard's power zones (default 200)")
    ap.add_argument("--dashboard-port", type=int, default=2137, help="dashboard on http://127.0.0.1:PORT")
    ap.add_argument("--game-port", type=int, default=27100,
                    help="UDP port a game plugin reports the gradient to (localhost only, default 27100)")
    return ap


def choose_profile(args: argparse.Namespace) -> dict:
    """The profile to start with: --profile (an id or a file), else --keyset, else the target's default."""
    from .session import SessionConfig, SessionError, resolve_profile
    try:
        return resolve_profile(SessionConfig.from_args(args))
    except SessionError as e:
        sys.exit("\n".join(e.errors))


def wants_session(args: argparse.Namespace) -> bool:
    """Did the command line pick a game or a rider? Then start riding at once, as before; else show the Start page."""
    return not args.launcher and any([args.target, args.profile, args.keyset, args.remote, args.trainer,
                                      args.simulate, args.address, args.keys, args.click != "auto"])


async def bridge(args: argparse.Namespace) -> None:
    from . import profiles
    from .dashboard_server import start_dashboard
    from .paths import user_data_dir
    from .session import SessionConfig, SessionError, runtime

    profiles.set_user_dir((args.data_dir or user_data_dir()) / "profiles")
    cfg = SessionConfig.from_args(args)
    runtime.attach(asyncio.get_running_loop(), cfg)
    start_dashboard(args.dashboard_port)
    try:
        if wants_session(args):
            try:
                await runtime.start(cfg)
            except SessionError as e:
                sys.exit("\n".join(e.errors))
        else:
            log(f"open http://127.0.0.1:{args.dashboard_port} to choose a game and start riding")
        await asyncio.Event().wait()                     # until Ctrl+C / the process is stopped
    finally:
        await runtime.stop()


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("install", "build-bike", "profile", "new-game"):
        from . import install
        sys.exit(install.main(argv))
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(bridge(args))
    except KeyboardInterrupt:
        pass
