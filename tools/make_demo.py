"""Make the dashboard demo (docs/img/dashboard.gif and dashboard.png) without any hardware.

It starts Pedalator with a simulated rider on spare ports, takes a series of screenshots of the dashboard with
headless Chrome (changing the riding mode and the trainer resistance on the way) and assembles them into a GIF.

    pip install pillow
    python tools/make_demo.py [--frames 24] [--chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"]
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_chrome() -> str:
    for c in (shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("msedge"),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if c and Path(c).exists():
            return c
    sys.exit("Chrome/Chromium/Edge not found: pass --chrome")


def post(port: int, path: str, body: dict) -> None:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=3).read()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--chrome")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "img")
    ap.add_argument("--width", type=int, default=900, help="width of the GIF in pixels")
    args = ap.parse_args()
    from PIL import Image

    chrome = args.chrome or find_chrome()
    port, gport = free_port(), free_port()
    args.out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="pedalator-demo-"))
    bridge = subprocess.Popen(
        [sys.executable, "-m", "pedalator", "--simulate", "--dashboard-port", str(port), "--game-port", str(gport),
         "--mode", "medium"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(3)
        frames = []
        for i in range(args.frames):
            # a little story: easy -> a climb in manual mode -> realistic, back to the game's hills
            if i == args.frames // 4:
                post(port, "/preset", {"name": "easy"})
            if i == args.frames // 2:
                post(port, "/mode", {"mode": "manual"})
            if i == args.frames // 2 + 1:
                post(port, "/grade", {"grade": 7.0})
            if i == 3 * args.frames // 4:
                post(port, "/grade", {"grade": -4.0})
            if i == 7 * args.frames // 8:
                post(port, "/mode", {"mode": "game"})
                post(port, "/preset", {"name": "real"})
            png = tmp / f"f{i:02d}.png"
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1280,1010",
                            "--timeout=2500", f"--user-data-dir={tmp / 'profile'}", f"--screenshot={png}",
                            f"http://127.0.0.1:{port}/?lang={args.lang}"],
                           check=True, capture_output=True, timeout=60)
            frames.append(png)
            print(f"frame {i + 1}/{args.frames}", flush=True)
        shutil.copy(frames[(args.frames * 2) // 3], args.out / "dashboard.png")
        imgs = []
        for f in frames:
            im = Image.open(f).convert("RGB")
            h = round(im.height * args.width / im.width)
            imgs.append(im.resize((args.width, h), Image.LANCZOS).quantize(colors=96, method=Image.MEDIANCUT))
        imgs[0].save(args.out / "dashboard.gif", save_all=True, append_images=imgs[1:], duration=450, loop=0, optimize=True)
        print(f"wrote {args.out / 'dashboard.gif'} ({(args.out / 'dashboard.gif').stat().st_size // 1024} KB)")
    finally:
        bridge.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
