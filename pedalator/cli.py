"""Command line: ``python -m pedalator`` runs the bridge; ``install`` and ``build-bike`` set up the games."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import __version__
from .state import PRESETS, apply_preset, log, state

DEFAULT_TARGET = "keys"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pedalator",
        description="Ride games with your smart trainer. Run without a sub-command to start the bridge.",
        epilog="Other commands:  pedalator install openmw|openomsi   pedalator build-bike   (see --help of each)")
    ap.add_argument("--version", action="version", version=f"pedalator {__version__}")

    src = ap.add_argument_group("where the rider data comes from")
    src.add_argument("--remote", action="store_true",
                     help="phone mode: a phone or laptop with Web Bluetooth reads the trainer (for PCs without BLE)")
    src.add_argument("--click", choices=("auto", "off"), default="auto",
                     help="read a Zwift Click over this PC's Bluetooth: auto = when the PC reads the trainer itself "
                          "(not with --remote, where the phone page reads it), off = never")
    src.add_argument("--simulate", action="store_true", help="no trainer: a made-up rider (try the dashboard or a game)")
    src.add_argument("--address", help="Bluetooth address of the trainer (default: scan for the first FTMS trainer)")
    src.add_argument("--ip", help="this PC's LAN address for the phone certificate (default: autodetect)")
    src.add_argument("--data-dir", type=Path, help="where certificates and the phone token are kept")
    src.add_argument("--phone-port", type=int, default=8766, help="(phone mode) HTTPS port for the phone page (default 8766)")
    src.add_argument("--ca-port", type=int, default=8767, help="(phone mode) HTTP port that serves the certificate (default 8767)")

    game = ap.add_argument_group("the game")
    game.add_argument("--target", choices=("keys", "openmw", "udp"), default=DEFAULT_TARGET,
                      help="keys: press the game's driving keys | openmw: Morrowind via the OpenMW mod | "
                           "udp: JSON datagrams for scripted games (default: keys)")
    game.add_argument("--keys", action="store_true",
                      help="(keys target) actually press keys; without it nothing is typed into the game")
    game.add_argument("--keyset", choices=("numpad", "wasd"), default="numpad",
                      help="(keys target) numpad = OMSI's own keys (8 throttle, 2 brake, 4/6 steer), or wasd")
    game.add_argument("--openmw-state", type=Path, help="state.txt of the OpenMW mod (default: found in openmw.cfg)")
    game.add_argument("--openmw-log", type=Path, help="openmw.log (default: next to openmw.cfg)")
    game.add_argument("--openmw-use-key", choices=("e", "f", "space", "enter"), default="e",
                      help="the game's key for open / take / talk; the Click's Z button presses it")
    game.add_argument("--udp-out", default="127.0.0.1:27200", metavar="HOST:PORT",
                      help="(udp target) where the JSON datagrams go")

    feel = ap.add_argument_group("how it rides")
    feel.add_argument("--mode", choices=sorted(PRESETS), default="easy",
                      help="riding mode at start: easy | medium | real (changeable on the dashboard)")
    feel.add_argument("--gain", type=float, help="game throttle = power x gain / pmax (default: from the mode)")
    feel.add_argument("--difficulty", type=float,
                      help="share of the game's hills the trainer simulates, 0..1 (default: from the mode)")
    feel.add_argument("--pmax", type=float, default=250, help="watts that mean full throttle at gain 1 (default 250)")
    feel.add_argument("--ftp", type=int, default=200, help="your FTP in watts, for the dashboard's power zones")
    ap.add_argument("--dashboard-port", type=int, default=8765, help="dashboard on http://127.0.0.1:PORT")
    ap.add_argument("--game-port", type=int, default=27100,
                    help="UDP port a game plugin reports the gradient to (localhost only, default 27100)")
    return ap


async def bridge(args: argparse.Namespace) -> None:
    from . import keys as keyout
    from .certs import lan_ip
    from .dashboard_server import start_dashboard
    from .difficulty import difficulty_loop
    from .loops import GameUdp, console_status, sampler
    from .paths import find_openmw_log, find_openmw_state, user_data_dir
    from .phone_server import start_phone_servers

    keyout.SCAN.update(keyout.KEYSETS[args.keyset])
    state.update(ftp=args.ftp, pmax=args.pmax, keys=args.keys, keyset=args.keyset)
    apply_preset(args.mode)
    if args.gain is not None:
        state["gain"], state["preset"] = args.gain, "custom"
    if args.difficulty is not None:
        state["difficulty"], state["preset"] = args.difficulty, "custom"

    start_dashboard(args.dashboard_port)
    if args.remote:
        state.update(trainer_name="(phone)", simulate=False)
        start_phone_servers(args.ip or lan_ip(), args.data_dir or user_data_dir(), args.phone_port, args.ca_port)
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(GameUdp, local_addr=("127.0.0.1", args.game_port))
    tasks = [asyncio.create_task(sampler()), asyncio.create_task(console_status()),
             asyncio.create_task(difficulty_loop())]

    if args.target == "openmw":
        from .targets import openmw
        st = args.openmw_state or find_openmw_state()
        lg = args.openmw_log or find_openmw_log()
        if not st or not lg:
            sys.exit("OpenMW: cannot find the mod's state file or openmw.log. Install the mod first "
                     "(pedalator install openmw) or give --openmw-state and --openmw-log.")
        log(f"OpenMW: state file {st}, log {lg}; only the Click's Z button presses a key ({args.openmw_use_key.upper()})")
        tasks += [asyncio.create_task(openmw.state_loop(st)), asyncio.create_task(openmw.use_key(args.openmw_use_key)),
                  asyncio.create_task(openmw.log_tail(lg))]
    elif args.target == "udp":
        from .targets import udp
        host, _, port = args.udp_out.rpartition(":")
        log(f"UDP target: JSON datagrams to {host or '127.0.0.1'}:{port}; the game answers on UDP {args.game_port}")
        tasks.append(asyncio.create_task(udp.send_loop(host or "127.0.0.1", int(port))))
    elif args.keys:
        log(f"driving keys ({args.keyset}) go to the window in front: throttle by power, steering/brake by Zwift Click")
        tasks += [asyncio.create_task(keyout.throttle_loop()), asyncio.create_task(keyout.buttons_loop())]

    if args.click == "auto" and not args.remote and not args.simulate:
        from .click import click_loop
        tasks.append(asyncio.create_task(click_loop()))

    if args.simulate:
        from .simulate import simulate
        tasks.append(asyncio.create_task(simulate()))
    elif not args.remote:
        from .ble import trainer_loop
        tasks.append(asyncio.create_task(trainer_loop(args.address)))
    await asyncio.gather(*tasks)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("install", "build-bike"):
        from . import install
        sys.exit(install.main(argv))
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(bridge(args))
    except KeyboardInterrupt:
        pass
