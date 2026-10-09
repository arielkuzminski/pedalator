"""Build the single-file Windows program with PyInstaller: ``python tools/build_exe.py`` (needs ``pip install pyinstaller``).

Writes ``build/dist/pedalator-<version>-windows.exe`` and ``build/dist/SHA256SUMS.txt``.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    import PyInstaller.__main__ as pyinstaller
    sys.path.insert(0, str(ROOT))
    from pedalator import __version__

    dist, name = ROOT / "build" / "dist", f"pedalator-{__version__}-windows"
    data = [(ROOT / "pedalator" / "web", "pedalator/web"), (ROOT / "pedalator" / "data", "pedalator/data")]
    pyinstaller.run([
        "--noconfirm", "--clean", "--onefile", "--name", name,
        "--distpath", str(dist), "--workpath", str(ROOT / "build" / "work"), "--specpath", str(ROOT / "build"),
        *[a for src, dest in data for a in ("--add-data", f"{src}{os.pathsep}{dest}")],
        "--collect-all", "bleak", "--collect-submodules", "winrt",
        str(ROOT / "packaging" / "pedalator_entry.py"),
    ])
    exe = dist / f"{name}.exe"
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (dist / "SHA256SUMS.txt").write_text(f"{digest}  {exe.name}\n", encoding="utf-8")
    print(f"built {exe} ({exe.stat().st_size // 1024} KB)\nsha256 {digest}")


if __name__ == "__main__":
    main()
