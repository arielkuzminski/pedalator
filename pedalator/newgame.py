"""``pedalator new-game``: a few questions in, a ready-to-try setup for a new game out.

Two ways to reach a game are covered here:

* ``keys``: the game reads the keyboard. The result is a profile and nothing else, no code is needed.
* ``udp``: the game has a mod or script that can open a UDP socket. The result is a profile, a small Python listener
  that shows what Pedalator sends, a Lua sketch of the mod, and (when the game can report the slope) the line to send
  back so the trainer follows the hills.

A game whose scripts cannot use sockets needs a new target (see docs/development.md); the wizard says so.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import keynames, profiles

HOW = {"keys": "the game reads the keyboard", "udp": "the game has a mod/script that can use UDP"}
SLOT_HINT = {"throttle": "move forward / accelerate", "brake": "brake / move back",
             "left": "steer left / turn left", "right": "steer right / turn right"}
DEFAULT_KEYS = {"throttle": "KeyW", "brake": "KeyS", "left": "KeyA", "right": "KeyD"}


def ask(prompt: str, default: str | None = None, choices: tuple[str, ...] | None = None) -> str:
    """Ask on the terminal until the answer is acceptable (an empty answer takes the default)."""
    while True:
        shown = f" [{default}]" if default else ""
        answer = input(f"{prompt}{shown}: ").strip() or (default or "")
        if answer and (choices is None or answer in choices):
            return answer
        print("  please answer" + (f" with one of: {', '.join(choices)}" if choices else " (it cannot be empty)"))


def parse_keys(spec: list[str] | None) -> tuple[dict[str, str], list[str]]:
    keys: dict[str, str] = {}
    errors: list[str] = []
    for item in spec or []:
        slot, _, name = item.partition("=")
        if slot not in DEFAULT_KEYS:
            errors.append(f"'{slot}' is not a key slot (use {', '.join(DEFAULT_KEYS)})")
        elif not keynames.is_key(name):
            errors.append(f"'{name}' is not a known key name (examples: KeyW, ArrowUp, Numpad8, Space)")
        else:
            keys[slot] = name
    return keys, errors


def make_profile(name: str, how: str, keys: dict[str, str], pmax: int | None = None) -> tuple[dict, list[str]]:
    data: dict = {"version": 1, "id": profiles.slugify(name), "name": name,
                  "target": how, "ride": {"mode": "easy"}, "options": {}}
    if pmax:
        data["ride"]["pmax"] = pmax
    if how == "keys":
        data["keys"] = {**DEFAULT_KEYS, **keys}
        data["bindings"] = {"LEFT": "steer_left", "Z": "steer_left", "RIGHT": "steer_right", "A": "steer_right",
                            "DOWN": "brake", "B": "brake", "MINUS": "difficulty_down", "PLUS": "difficulty_up"}
    else:
        data["keys"] = {}
        data["bindings"] = {"MINUS": "difficulty_down", "PLUS": "difficulty_up"}
    return profiles.validate(data)


LISTENER = '''"""Shows what Pedalator sends to a game: run it instead of the game to check that pedalling arrives.

    pedalator --target udp --udp-out 127.0.0.1:27200      (in one terminal)
    python listen.py                                       (in another)
"""
import json
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", 27200))
print("waiting for Pedalator on UDP 27200 ... (Ctrl+C to stop)")
while True:
    data, _ = sock.recvfrom(2048)
    p = json.loads(data)
    print(f"move {p['move']:.2f}  power {p['power']:>4} W  turn {p['turn']:+d}  buttons {p['buttons']}")
'''

LUA_SKETCH = '''-- Sketch of a mod for {name}. Adapt the three marked places to your game's scripting API.
-- Pedalator sends JSON ~20 times a second to UDP 127.0.0.1:27200, for example:
--   {{"n":1234,"power":143,"move":0.57,"cadence":88.0,"speed":24.1,"turn":-1,"look":0,"buttons":["LEFT","B"]}}
-- "move" is 0..1 (how hard to push forward), "turn" is -1/0/1, "buttons" are the Zwift Click buttons held.

local socket = require("socket")          -- 1) your engine must offer sockets; if not, see docs/development.md
local udp = assert(socket.udp())
udp:setsockname("127.0.0.1", 27200)
udp:settimeout(0)

local latest = {{ move = 0, turn = 0 }}

local function poll()                      -- call this every frame/tick
  while true do
    local data = udp:receive()
    if not data then break end
    -- 2) decode the JSON with your engine's JSON library (or pick the fields with string patterns):
    local move = tonumber(data:match('"move":%s*([%-%d%.]+)'))
    local turn = tonumber(data:match('"turn":%s*([%-%d]+)'))
    if move then latest.move, latest.turn = move, turn or 0 end
  end
  return latest
end

-- 3) use poll().move as the player's forward input and poll().turn as the steering.
{slope}return {{ poll = poll }}
'''

SLOPE_LUA = '''
-- The game can tell the slope of the ground? Send it back so the trainer follows the hills:
local out = assert(socket.udp())
local function report_slope(percent, speed_kmh)
  out:sendto(string.format("grade=%.1f;speed=%.1f", percent, speed_kmh), "127.0.0.1", 27100)
end
'''

README = '''# {name}: Pedalator setup

Generated by `pedalator new-game`. The profile `{id}` ({target} target) is already saved, so:

```
pedalator --profile {id}{extra}
```

{steps}
Open the dashboard (http://127.0.0.1:2137) and the **Controls** tab to change buttons and keys while you ride. To
share this setup: `pedalator profile export {id} --out {id}.json`.
'''

STEPS = {
    "keys": '''1. Start the game and put its window in front.
2. Pedal. The keys {keys} are pressed for you; the Click's arrows steer, **B/↓** brakes.
3. If a key does nothing in the game, check the game's own key settings and change the key on the **Controls** tab
   (click the slot, press the key).
''',
    "udp": '''1. Check that pedalling arrives: run `python listen.py` while `pedalator --profile {id} --udp-out 127.0.0.1:27200`
   is running. You should see `move` follow your power.
2. Adapt `mod_sketch.lua` to your game's scripting API and make the game apply `move` and `turn`.
3. {slope}
''',
}


def write_files(profile: dict, out: Path, slope: bool) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def put(name: str, text: str) -> None:
        (out / name).write_text(text, encoding="utf-8")
        written.append(out / name)

    put(f"{profile['id']}.json", profiles.export_text(profile))
    if profile["target"] == "udp":
        put("listen.py", LISTENER)
        put("mod_sketch.lua", LUA_SKETCH.format(name=profile["name"], slope=SLOPE_LUA if slope else ""))
        step3 = ("Call `report_slope(percent, km/h)` every frame: Pedalator uses it as the trainer's resistance."
                 if slope else "The game cannot report the slope, so use the dashboard's **manual grade** slider for hills.")
        steps = STEPS["udp"].format(id=profile["id"], slope=step3)
        extra = " --target udp --udp-out 127.0.0.1:27200"
    else:
        steps = STEPS["keys"].format(keys=", ".join(f"`{keynames.label(k)}`" for k in profile["keys"].values()))
        extra = " --target keys"
    put("README.md", README.format(name=profile["name"], id=profile["id"], target=profile["target"], steps=steps, extra=extra))
    return written


def create(name: str, how: str, keys: dict[str, str], slope: bool, out: Path | None,
           overwrite: bool = False) -> tuple[dict | None, list[Path], list[str]]:
    """Make the profile and the files of a new game and save the profile. Shared by the CLI and the dashboard.

    ``out`` is where the files go (default ``./<id>``). Returns ``(profile, files, errors)``; on errors nothing was
    written (``profile`` is None when it could not even be made).
    """
    profile, errors = make_profile(name, how, keys)
    if errors:
        return None, [], errors
    existing = {p["id"] for p in profiles.list_profiles() if p["user"] or p["builtin"]}
    if profile["id"] in existing and not overwrite:
        return profile, [], [f"a profile '{profile['id']}' already exists; pick another name or use --overwrite"]
    files = write_files(profile, out or Path.cwd() / profile["id"], slope)
    profiles.save_user(profile)
    return profile, files, []


def games_dir() -> Path:
    """Where the dashboard puts the files of the games it makes (next to your profiles)."""
    return profiles.user_dir().parent / "games"


def game_files(gid: str) -> list[str]:
    """The files of a game made in the dashboard that the editor may open: the generated ones, if they exist."""
    if not profiles.ID_RE.match(gid or ""):
        return []
    folder = games_dir() / gid
    return [n for n in (f"{gid}.json", "README.md", "listen.py", "mod_sketch.lua") if (folder / n).is_file()]


def list_games() -> list[dict]:
    root = games_dir()
    if not root.is_dir():
        return []
    return [{"id": d.name, "files": game_files(d.name)} for d in sorted(root.iterdir())
            if d.is_dir() and game_files(d.name)]


def game_file_path(gid: str, name: str) -> Path | None:
    """The path of an editable file, or None when the game or the name is not one we made (no path tricks possible)."""
    return games_dir() / gid / name if name in game_files(gid) else None


def main(args: argparse.Namespace) -> int:
    from .paths import user_data_dir
    profiles.set_user_dir((args.data_dir or user_data_dir()) / "profiles")
    interactive = args.name is None
    if interactive:
        print("New game for Pedalator. Answer a few questions (Enter takes the value in brackets).\n")
    name = args.name or ask("Name of the game")
    how = args.how
    if how is None:
        print("How can Pedalator reach the game?")
        for k, v in HOW.items():
            print(f"  {k:<5} {v}")
        print("  (a game whose scripts cannot use sockets needs a new target: see docs/development.md)")
        how = ask("Choose", "keys", tuple(HOW))
    keys, errors = parse_keys(args.key)
    if errors:
        for e in errors:
            print(f"  - {e}")
        return 2
    if how == "keys" and interactive:
        for slot, hint in SLOT_HINT.items():
            while slot not in keys:
                choice = ask(f"Key for '{slot}' ({hint}), as a browser key name", DEFAULT_KEYS[slot])
                if keynames.is_key(choice):
                    keys[slot] = choice
                else:
                    print("  not a known key name; examples: KeyW, ArrowUp, Numpad8, Space")
    slope = args.slope if args.slope is not None else (
        ask("Can the game report the slope of the ground?", "no", ("yes", "no")) == "yes" if interactive and how == "udp" else False)
    profile, files, errors = create(name, how, keys, slope, args.out, args.overwrite)
    if errors:
        if profile is None:
            print("cannot make a profile:")
            for e in errors:
                print(f"  - {e}")
        else:
            print(errors[0])
        return 2
    out = files[0].parent
    print(f"\nProfile '{profile['id']}' saved. Files written to {out}:")
    for f in files:
        print(f"  {f.name}")
    print(f"\nNext: read {out / 'README.md'} for the exact steps, or just run:  pedalator --profile {profile['id']}")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    nw = sub.add_parser("new-game", help="a wizard that sets up Pedalator for a new game")
    nw.add_argument("--name", help="the game's name (asks if missing)")
    nw.add_argument("--how", choices=list(HOW), help="keys: keyboard only; udp: a mod that can use UDP")
    nw.add_argument("--key", action="append", metavar="SLOT=KEY", help="e.g. --key throttle=ArrowUp (repeatable)")
    nw.add_argument("--slope", action=argparse.BooleanOptionalAction, default=None, help="the game can report the slope")
    nw.add_argument("--out", type=Path, help="where to write the files (default: ./<id>)")
    nw.add_argument("--overwrite", action="store_true", help="replace a profile of yours with the same id")
    nw.add_argument("--data-dir", type=Path, help="where your profiles are kept")

