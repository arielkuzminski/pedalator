"""Command line: ``python -m pedalator`` runs the bridge; ``install`` and ``build-bike`` set up the games."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import __version__
from .state import PRESETS, apply_preset, log, state

DEFAULT_TARGET = "keys"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pedalator",
        description="Ride games with your smart trainer. Run without a sub-command to start the bridge.",
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
    game.add_argument("--target", choices=("keys", "openmw", "udp"), default=DEFAULT_TARGET,
                      help="keys: press the game's driving keys | openmw: Morrowind via the OpenMW mod | "
                           "udp: JSON datagrams for scripted games (default: keys)")
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
    ap.add_argument("--dashboard-port", type=int, default=8765, help="dashboard on http://127.0.0.1:PORT")
    ap.add_argument("--game-port", type=int, default=27100,
                    help="UDP port a game plugin reports the gradient to (localhost only, default 27100)")
    return ap


def choose_profile(args: argparse.Namespace) -> dict:
    """The profile to start with: --profile (an id or a file), else --keyset, else the target's default."""
    from . import profiles
    choice = args.profile
    if choice and choice.lower().endswith(".json") and Path(choice).is_file():
        profile, errors = profiles.validate(json.loads(Path(choice).read_text(encoding="utf-8")), fill_keys=True)
        if errors:
            sys.exit(f"{choice}: " + "; ".join(errors))
    else:
        choice = choice or ("generic-wasd" if args.target == "keys" and args.keyset == "wasd"
                            else profiles.DEFAULT_ID[args.target])
        try:
            profile = profiles.load(choice)
        except KeyError:
            sys.exit(f"no profile '{choice}'. Available: " + ", ".join(p["id"] for p in profiles.list_profiles()))
        except ValueError as e:
            sys.exit(str(e))
    if profile["target"] != args.target:
        sys.exit(f"profile '{profile['id']}' is for the '{profile['target']}' target; use --target {profile['target']}")
    return profile


def resolve_sources(trainer: str | None, click: str, remote: bool, simulate: bool) -> tuple[str, str]:
    """Who reads the trainer ('pc' or 'phone') and who reads the Click ('pc', 'phone' or 'off').

    ``--remote`` means the phone reads the trainer; ``--click auto`` follows the trainer (and is off for a
    simulated rider unless a phone is in play).
    """
    t = trainer or ("phone" if remote else "pc")
    if click == "auto":
        click = "phone" if t == "phone" else ("off" if simulate else "pc")
    return t, click


async def bridge(args: argparse.Namespace) -> None:
    from . import keys as keyout
    from . import profiles
    from .certs import lan_ip
    from .dashboard_server import start_dashboard
    from .difficulty import difficulty_loop
    from .loops import GameUdp, console_status, sampler
    from .paths import find_openmw_log, find_openmw_state, user_data_dir
    from .phone_server import start_phone_servers

    state["target"] = args.target
    profiles.set_user_dir((args.data_dir or user_data_dir()) / "profiles")
    profile = choose_profile(args)
    if args.openmw_use_key:
        profile["keys"]["use"] = {"e": "KeyE", "f": "KeyF", "space": "Space", "enter": "Enter"}[args.openmw_use_key]
    profiles.apply(profile)
    state.update(keys=args.keys, keyset=profile["id"])
    if args.mode:
        apply_preset(args.mode)
    if args.pmax is not None:
        state["pmax"] = args.pmax
    if args.ftp is not None:
        state["ftp"] = args.ftp
    if args.gain is not None:
        state["gain"], state["preset"] = args.gain, "custom"
    if args.difficulty is not None:
        state["difficulty"], state["preset"] = args.difficulty, "custom"
    log(f"profile: {profile['name']} ({profile['id']})")

    trainer, click = resolve_sources(args.trainer, args.click, args.remote, args.simulate)
    start_dashboard(args.dashboard_port)
    if trainer == "phone":
        state.update(trainer_name="(phone)", simulate=False)
    if "phone" in (trainer, click):
        start_phone_servers(args.ip or lan_ip(), args.data_dir or user_data_dir(), args.phone_port, args.ca_port,
                            accept={"trainer": trainer == "phone", "click": click == "phone"})
    log(f"trainer: {trainer if not args.simulate else 'simulated'} · Zwift Click: {click}")
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
        log(f"OpenMW: state file {st}, log {lg}")
        tasks += [asyncio.create_task(openmw.state_loop(st)), asyncio.create_task(openmw.config_loop(st.with_name("config.txt"))),
                  asyncio.create_task(openmw.use_key()), asyncio.create_task(openmw.log_tail(lg))]
    elif args.target == "udp":
        from .targets import udp
        host, _, port = args.udp_out.rpartition(":")
        log(f"UDP target: JSON datagrams to {host or '127.0.0.1'}:{port}; the game answers on UDP {args.game_port}")
        tasks.append(asyncio.create_task(udp.send_loop(host or "127.0.0.1", int(port))))
    elif args.keys:
        log("driving keys go to the window in front: throttle by power, steering/brake by Zwift Click "
            f"(profile {profile['id']})")
        tasks += [asyncio.create_task(keyout.throttle_loop()), asyncio.create_task(keyout.buttons_loop())]

    if click == "pc":
        from .click import click_loop
        tasks.append(asyncio.create_task(click_loop()))

    if args.simulate:
        from .simulate import simulate
        tasks.append(asyncio.create_task(simulate()))
    elif trainer == "pc":
        from .ble import trainer_loop
        tasks.append(asyncio.create_task(trainer_loop(args.address)))
    await asyncio.gather(*tasks)


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
