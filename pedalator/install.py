"""``pedalator install openmw|openomsi`` and ``pedalator build-bike``: put the game side in place."""
from __future__ import annotations

import argparse
import re
import shutil
import time
from pathlib import Path

from .bike import UnexpectedBike, build_bike
from .paths import DATA_DIR, openmw_user_dir

OPENMW_MOD = "Pedalator"
OPENMW_CONTENT = "Pedalator.omwscripts"
OLD_MOD_MARK = "TrainerBike"           # the name this mod had before it got its own project


def update_openmw_cfg(text: str, mod_dir: Path) -> tuple[str, list[str]]:
    """Return openmw.cfg text with the mod enabled (data path + content line), and what was changed.

    Idempotent; keeps the file's line endings; drops the old ``TrainerBike`` entries of earlier versions.
    """
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    changes: list[str] = []
    kept = []
    for line in lines:
        if OLD_MOD_MARK in line and re.match(r"\s*(data|content)\s*=", line):
            changes.append(f"removed old entry: {line.strip()}")
            continue
        kept.append(line)
    lines = kept
    data_line = f'data="{mod_dir.as_posix()}"'
    content_line = f"content={OPENMW_CONTENT}"
    while lines and lines[-1] == "":
        lines.pop()
    if data_line not in lines:
        lines.append(data_line)
        changes.append(f"added {data_line}")
    if content_line not in lines:
        lines.append(content_line)
        changes.append(f"added {content_line}")
    return nl.join(lines) + nl, changes


def install_openmw(user_dir: Path | None, dest: Path | None, dry_run: bool = False) -> int:
    user_dir = user_dir or openmw_user_dir()
    if not user_dir or not (user_dir / "openmw.cfg").is_file():
        print("Cannot find your openmw.cfg. Start OpenMW (or its launcher) once, or pass --user-dir.")
        return 2
    cfg = user_dir / "openmw.cfg"
    dest = dest or (user_dir / "mods" / OPENMW_MOD)
    src = DATA_DIR / "openmw" / OPENMW_MOD
    text = cfg.read_text(encoding="utf-8", errors="replace")
    new, changes = update_openmw_cfg(text, dest)
    print(f"mod folder : {dest}")
    print(f"config     : {cfg}")
    for c in changes:
        print(f"  - {c}")
    if dry_run:
        print("(dry run: nothing was written)")
        return 0
    shutil.copytree(src, dest, dirs_exist_ok=True)
    if changes:
        backup = cfg.with_name(f"openmw.cfg.bak-pedalator-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(cfg, backup)
        cfg.write_text(new, encoding="utf-8", newline="")
        print(f"backup     : {backup}")
    print("Done. Start OpenMW and load a save; then run:  pedalator --target openmw --remote  (or without --remote)")
    return 0


def install_openomsi(game_dir: Path) -> int:
    if not (game_dir / "openomsi.exe").exists() and not (game_dir / "Plugins").is_dir():
        print(f"{game_dir} does not look like an openOMSI folder (no openomsi.exe / Plugins).")
        return 2
    dest = game_dir / "Plugins" / "pedalator"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DATA_DIR / "openomsi" / "Plugins" / "pedalator" / "main.lua", dest / "main.lua")
    print(f"plugin installed: {dest / 'main.lua'}")
    if (game_dir / "Plugins" / "trainer").is_dir():
        print("Note: an old Plugins/trainer folder exists (an earlier version of this plugin); delete it so the "
              "gradient is not sent twice.")
    print("Done. Start the bridge with:  pedalator --remote --keys   (or without --remote)")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pedalator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    inst = sub.add_parser("install", help="install the OpenMW mod or the openOMSI plugin")
    which = inst.add_subparsers(dest="game", required=True)
    om = which.add_parser("openmw", help="copy the mod and enable it in openmw.cfg (a backup is made)")
    om.add_argument("--user-dir", type=Path, help="folder with openmw.cfg (default: autodetect)")
    om.add_argument("--dest", type=Path, help="where to put the mod folder (default: <user-dir>/mods/Pedalator)")
    om.add_argument("--dry-run", action="store_true", help="only show what would change")
    oo = which.add_parser("openomsi", help="copy the Lua plugin into an openOMSI folder")
    oo.add_argument("--game-dir", type=Path, required=True, help="the openOMSI folder (with openomsi.exe)")

    bb = sub.add_parser("build-bike", help="build the bike from your own copy of the HafenCity add-on (OMSI 2)")
    bb.add_argument("--hafencity", type=Path, required=True,
                    help="your Vehicles/HC_Fahrrad folder (from the HafenCity add-on you own)")
    bb.add_argument("--out", type=Path, help="where to write the mod (default: <game-dir>/Mods/Pedalator)")
    bb.add_argument("--game-dir", type=Path, help="the openOMSI folder, to pick the default --out")

    args = ap.parse_args(argv)
    if args.cmd == "install":
        if args.game == "openmw":
            return install_openmw(args.user_dir, args.dest, args.dry_run)
        return install_openomsi(args.game_dir)
    out = args.out or (args.game_dir / "Mods" / "Pedalator" if args.game_dir else None)
    if not out:
        ap.error("give --out or --game-dir")
    try:
        bus = build_bike(args.hafencity, out)
    except (FileNotFoundError, UnexpectedBike) as e:
        print(f"Cannot build the bike: {e}")
        return 2
    print(f"bike written: {bus}")
    print("Start the openOMSI launcher: it sorts the mod into place. Pick \"Pedalator Bike\" as the vehicle, and in "
          "the game switch off collisions with terrain and vehicles (Esc -> Options).")
    return 0
