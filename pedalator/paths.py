"""Where things live. Nothing here is hard-coded to one machine: it asks the system, and every path can be overridden."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
DATA_DIR = PACKAGE_DIR / "data"          # the game mods and plugins that ship with Pedalator


def user_data_dir() -> Path:
    """Private runtime data (certificates, the phone token). Never inside the repository."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Pedalator"


def documents_dir() -> Path:
    """The user's Documents folder (it can be on another drive or redirected, so ask Windows)."""
    if sys.platform == "win32":
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:     # CSIDL_PERSONAL
            return Path(buf.value)
    return Path.home() / "Documents"


def openmw_user_dir() -> Path | None:
    """The folder with the user's openmw.cfg, openmw.log and saves."""
    if sys.platform == "win32":
        candidates = [documents_dir() / "My Games" / "OpenMW"]
    elif sys.platform == "darwin":
        candidates = [Path.home() / "Library" / "Preferences" / "openmw"]
    else:
        candidates = [Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "openmw"]
    for c in candidates:
        if (c / "openmw.cfg").is_file():
            return c
    return None


def cfg_values(cfg: Path, key: str) -> list[str]:
    """The values of ``key=...`` lines of an openmw.cfg (quotes removed)."""
    out = []
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        m = re.match(rf"\s*{re.escape(key)}\s*=\s*(.*?)\s*$", line)
        if m:
            v = m.group(1)
            if len(v) >= 2 and v[0] == v[-1] == '"':
                v = v[1:-1]
            out.append(v)
    return out


def find_openmw_state(user_dir: Path | None = None) -> Path | None:
    """``pedalator/state.txt`` of the installed OpenMW mod: found through the data= lines of openmw.cfg."""
    user_dir = user_dir or openmw_user_dir()
    if not user_dir:
        return None
    for d in cfg_values(user_dir / "openmw.cfg", "data"):
        p = Path(d) / "pedalator" / "state.txt"
        if p.is_file():
            return p
    return None


def find_openmw_log(user_dir: Path | None = None) -> Path | None:
    user_dir = user_dir or openmw_user_dir()
    return user_dir / "openmw.log" if user_dir else None
