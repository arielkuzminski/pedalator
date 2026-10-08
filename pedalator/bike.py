"""Build the Pedalator bike for OMSI / openOMSI from *your own* copy of the HafenCity add-on.

The bike's model, sounds, textures and the original script belong to the HafenCity add-on and are not part of
Pedalator. This module reads your copy of ``Vehicles/HC_Fahrrad`` and writes a new vehicle next to it:

* a script where the pedalling rider's power (not an AI's random speed) drives the wheels,
* its constants and variable list,
* a ``.bus`` file with realistic mass, resistance, steering and a rider camera.

The pieces that are ours (the drive block, constants, camera) are in ``data/openomsi/bike/*.tmpl``.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .paths import DATA_DIR

TEMPLATES = DATA_DIR / "openomsi" / "bike"
NAME = "pedalator"
ASSET_DIRS = ("model", "sound", "texture")


class UnexpectedBike(Exception):
    """The HafenCity files are not the version this builder knows."""


def _read(path: Path) -> tuple[str, str]:
    """Read a game text file byte-exactly (latin-1 keeps every byte) and say which newline it uses."""
    text = path.read_bytes().decode("latin-1")
    return text.replace("\r\n", "\n"), ("\r\n" if "\r\n" in text else "\n")


def _write(path: Path, text: str, nl: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", nl).encode("latin-1"))


def _tmpl(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _sub1(pattern: str, repl: str, text: str, what: str, count: int = 1) -> str:
    new, n = re.subn(pattern, lambda m: m.group(1) + repl, text)
    if n != count:
        raise UnexpectedBike(f"{what}: expected {count} match(es), found {n}")
    return new


def make_script(original: str) -> str:
    """Original AI script -> script driven by the rider's power."""
    a = original.index("'\t################ Zuf")                  # the AI's random top speed, throttle and brake
    b = original.index("'\t################ Zuf", a + 10)           # ... up to the random bell
    text = original[:a] + original[b:]
    m = text.index("'\t################ Bewegung")                  # the AI's drive block ...
    end = text.rindex("{end}")
    text = text[:m] + _tmpl("movement.tmpl") + "\n" + text[end:]    # ... replaced by ours
    if "{frame}\n" not in text:
        raise UnexpectedBike("script has no {frame} block")
    return text.replace("{frame}\n", "{frame}\n\n\t1 (S.L.engine_on)\n", 1)


def make_bus(original: str, friendly_name: str) -> str:
    """Original ``fahrrad_1.bus`` -> our bike: 100 kg physics, own script files, rider camera."""
    t = original
    t = _sub1(r"(\[friendlyname\]\n[ \t]*)Fahrrad 1", friendly_name, t, "friendlyname")
    t = _sub1(r"(\[script\]\n1\nscript\\)fahrrad\.osc", f"fahrrad_{NAME}.osc", t, "script")
    t = _sub1(r"(\[constfile\]\n1\nscript\\)fahrrad_constfile\.txt", f"fahrrad_{NAME}_constfile.txt", t, "constfile")
    t = _sub1(r"(\[varnamelist\]\n1\nscript\\)fahrrad_varlist\.txt", f"fahrrad_{NAME}_varlist.txt", t, "varnamelist")
    t = _sub1(r"(\[mass\]\n)0\.3\b", "0.1", t, "mass")
    t = _sub1(r"(\[momentofintertia\]\n)50\n20\n50", "0.2\n0.08\n0.2", t, "momentofintertia")
    t = _sub1(r"(\[rollwiderstand\]\n)60\b", "1", t, "rollwiderstand")
    t = _sub1(r"(\[inv_min_turnradius\]\n)0\.7\b", "0.5", t, "inv_min_turnradius")
    t = _sub1(r"(achse_feder\n)50\b", "17", t, "achse_feder", count=2)
    t = _sub1(r"(\[sound\]\nsound\\Sound\.cfg\n)", "\n" + _tmpl("camera.tmpl"), t, "sound")
    return t


def build_bike(hafencity_bike_dir: Path, out_dir: Path, friendly_name: str = "Pedalator Bike") -> Path:
    """``hafencity_bike_dir`` is your ``Vehicles/HC_Fahrrad``; the result goes to ``out_dir/Vehicles/HC_Fahrrad``."""
    src = Path(hafencity_bike_dir)
    needed = [src / "fahrrad_1.bus", src / "script" / "fahrrad.osc", src / "script" / "fahrrad_constfile.txt",
              src / "script" / "fahrrad_varlist.txt"] + [src / d for d in ASSET_DIRS]
    missing = [str(p) for p in needed if not p.exists()]
    if missing:
        raise FileNotFoundError("this does not look like the HafenCity bike folder (Vehicles/HC_Fahrrad); missing: "
                                + ", ".join(missing))
    dest = Path(out_dir) / "Vehicles" / "HC_Fahrrad"
    for d in ASSET_DIRS:
        if (dest / d).exists():
            shutil.rmtree(dest / d)
        shutil.copytree(src / d, dest / d)

    text, nl = _read(src / "script" / "fahrrad.osc")
    _write(dest / "script" / f"fahrrad_{NAME}.osc", make_script(text), nl)
    text, nl = _read(src / "script" / "fahrrad_constfile.txt")
    _write(dest / "script" / f"fahrrad_{NAME}_constfile.txt", text.rstrip() + "\n\n" + _tmpl("constants.tmpl"), nl)
    text, nl = _read(src / "script" / "fahrrad_varlist.txt")
    _write(dest / "script" / f"fahrrad_{NAME}_varlist.txt", text.rstrip() + "\n\n" + _tmpl("varlist.tmpl"), nl)
    text, nl = _read(src / "fahrrad_1.bus")
    bus = dest / f"fahrrad_{NAME}.bus"
    _write(bus, make_bus(text, friendly_name), nl)
    return bus
