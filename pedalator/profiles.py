"""Profiles: one JSON file per game or setup — what the Zwift Click buttons do, which keys are pressed, how it rides.

A profile is plain JSON that you can edit by hand, share, import and export (the dashboard's *Controls* page does all
of it). Built-in profiles ship in ``data/profiles``; yours are saved in the user data folder and win over a built-in
with the same id.

.. code-block:: json

    {"version": 1, "id": "morrowind", "name": "Morrowind (OpenMW)", "target": "openmw",
     "ride": {"mode": "easy"},
     "bindings": {"LEFT": "turn_left", "B": "attack", "PLUS": "difficulty_up"},
     "keys": {"use": "KeyE"},
     "options": {"turn_rate": 1.7}}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import keynames
from .paths import DATA_DIR, user_data_dir
from .state import PRESETS, apply_preset, state

VERSION = 1
TARGETS = ("keys", "openmw", "udp")
DEFAULT_ID = {"keys": "omsi", "openmw": "morrowind", "udp": "generic-udp"}

# The ten physical buttons of a Zwift Click v2, with where they are (a v1 has two buttons, reported as LEFT and RIGHT).
BUTTONS = (
    ("UP", "Left puck: ▲"), ("DOWN", "Left puck: ▼"), ("LEFT", "Left puck: ◀"), ("RIGHT", "Left puck: ▶"),
    ("MINUS", "Left puck: −"),
    ("Y", "Right puck: Y (top)"), ("B", "Right puck: B (bottom)"), ("Z", "Right puck: Z (left)"),
    ("A", "Right puck: A (right)"), ("PLUS", "Right puck: +"),
)
BUTTON_NAMES = tuple(n for n, _ in BUTTONS)

ACTIONS = {
    "keys": ("steer_left", "steer_right", "brake", "difficulty_down", "difficulty_up"),
    "openmw": ("turn_left", "turn_right", "look_up", "look_down", "attack", "jump", "draw_weapon", "use",
               "difficulty_down", "difficulty_up"),
    "udp": ("difficulty_down", "difficulty_up"),
}
ACTION_LABELS = {
    "steer_left": "Steer left", "steer_right": "Steer right", "brake": "Brake",
    "turn_left": "Turn left", "turn_right": "Turn right", "look_up": "Look up", "look_down": "Look down",
    "attack": "Attack", "jump": "Jump", "draw_weapon": "Draw / sheathe weapon", "use": "Use / open / take / talk",
    "difficulty_down": "Easier hills (−)", "difficulty_up": "Harder hills (+)",
}
# the keys a target presses, by slot
KEY_SLOTS = {"keys": ("throttle", "brake", "left", "right"), "openmw": ("use",), "udp": ()}
KEY_SLOT_LABELS = {"throttle": "Throttle (pedalling)", "brake": "Brake", "left": "Steer left", "right": "Steer right",
                   "use": "Use / open / take"}
# numeric options of a target: name -> (type, minimum, maximum, default)
OPTIONS = {
    "openmw": {"turn_rate": (float, 0.2, 6.0, 1.7), "pitch_rate": (float, 0.2, 6.0, 1.2),
               "run_above": (float, 0.0, 1.0, 0.55), "use_speed_attribute": (bool, 0, 1, False),
               "speed_boost": (float, 0.0, 200.0, 60.0)},
    "keys": {}, "udp": {},
}
RIDE_FIELDS = {"gain": (0.5, 4.0), "difficulty": (0.0, 1.0), "pmax": (50.0, 1000.0), "ftp": (50.0, 600.0)}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_user_dir: Path | None = None


# ---------------------------------------------------------------------------------------------------- storage
def set_user_dir(path: Path | None) -> None:
    global _user_dir
    _user_dir = path


def user_dir() -> Path:
    return _user_dir or (user_data_dir() / "profiles")


def builtin_dir() -> Path:
    return DATA_DIR / "profiles"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:40] or "profile"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def builtin_ids() -> list[str]:
    return sorted(p.stem for p in builtin_dir().glob("*.json"))


def user_ids() -> list[str]:
    return sorted(p.stem for p in user_dir().glob("*.json")) if user_dir().is_dir() else []


def load(pid: str) -> dict:
    """The profile with this id (yours first, then the built-in), validated."""
    if not ID_RE.match(pid or ""):
        raise KeyError(pid)
    for path in (user_dir() / f"{pid}.json", builtin_dir() / f"{pid}.json"):
        if path.is_file():
            profile, errors = validate(_read(path), fill_keys=True)
            if errors:
                raise ValueError(f"profile {pid!r} is invalid: " + "; ".join(errors))
            return profile
    raise KeyError(pid)


def list_profiles() -> list[dict]:
    out = {}
    for pid in builtin_ids():
        data = _read(builtin_dir() / f"{pid}.json")
        out[pid] = {"id": pid, "name": data.get("name", pid), "target": data.get("target"), "builtin": True, "user": False}
    for pid in user_ids():
        try:
            data = _read(user_dir() / f"{pid}.json")
        except (OSError, ValueError):
            continue
        entry = out.setdefault(pid, {"id": pid, "builtin": False})
        entry.update(name=data.get("name", pid), target=data.get("target"), user=True)
    return sorted(out.values(), key=lambda e: (e["target"] or "", e["name"].lower()))


def save_user(profile: dict) -> Path:
    path = user_dir() / f"{profile['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_text(profile), encoding="utf-8")
    return path


def delete_user(pid: str) -> bool:
    path = user_dir() / f"{pid}.json"
    if ID_RE.match(pid or "") and path.is_file():
        path.unlink()
        return True
    return False


def export_text(profile: dict) -> str:
    return json.dumps(profile, indent=2, ensure_ascii=False) + "\n"


def import_text(text: str, new_id: str | None = None, overwrite: bool = False) -> tuple[dict | None, list[str]]:
    """Parse, validate and save a profile someone gave you. Returns (profile, errors)."""
    try:
        data = json.loads(text)
    except ValueError as e:
        return None, [f"not valid JSON: {e}"]
    if new_id:
        data["id"] = new_id
    profile, errors = validate(data, fill_keys=True)
    if errors:
        return None, errors
    if not overwrite and (user_dir() / f"{profile['id']}.json").exists():
        return None, [f"a profile with the id '{profile['id']}' already exists (give it another id, or overwrite)"]
    save_user(profile)
    return profile, []


# ---------------------------------------------------------------------------------------------------- validation
def validate(data: object, fill_keys: bool = False) -> tuple[dict, list[str]]:
    """Check a profile and return it normalised with a list of problems (empty when it is fine).

    ``fill_keys`` fills missing key slots from the target's built-in default, so a hand-written file stays usable.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return {}, ["a profile must be a JSON object"]
    version = data.get("version", VERSION)
    if not isinstance(version, int) or version < 1:
        errors.append("version must be a positive integer")
    elif version > VERSION:
        errors.append(f"this profile is version {version}; this Pedalator understands up to {VERSION}")
    target = data.get("target")
    if target not in TARGETS:
        errors.append(f"target must be one of {', '.join(TARGETS)}")
        return {}, errors
    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        errors.append("name must be text of 1-60 characters")
        name = "Unnamed"
    pid = data.get("id") or slugify(name)
    if not isinstance(pid, str) or not ID_RE.match(pid):
        errors.append("id must be lowercase letters, digits, - or _ (up to 40 characters)")
        pid = slugify(name)

    ride: dict = {}
    raw_ride = data.get("ride", {})
    if not isinstance(raw_ride, dict):
        errors.append("ride must be an object")
        raw_ride = {}
    if raw_ride.get("smooth") is not None:
        if isinstance(raw_ride["smooth"], bool):
            ride["smooth"] = raw_ride["smooth"]
        else:
            errors.append("ride.smooth must be true or false")
    if "mode" in raw_ride:
        if raw_ride["mode"] in PRESETS:
            ride["mode"] = raw_ride["mode"]
        else:
            errors.append(f"ride.mode must be one of {', '.join(PRESETS)}")
    for field, (lo, hi) in RIDE_FIELDS.items():
        if raw_ride.get(field) is not None:
            v = raw_ride[field]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                errors.append(f"ride.{field} must be a number from {lo:g} to {hi:g}")
            else:
                ride[field] = v

    bindings: dict[str, str] = {}
    raw_bindings = data.get("bindings", {})
    if not isinstance(raw_bindings, dict):
        errors.append("bindings must be an object (button -> action)")
        raw_bindings = {}
    for button, action in raw_bindings.items():
        if button not in BUTTON_NAMES:
            errors.append(f"bindings: unknown button '{button}' (use {', '.join(BUTTON_NAMES)})")
        elif action in (None, "none"):
            continue
        elif action not in ACTIONS[target]:
            errors.append(f"bindings.{button}: '{action}' is not an action of the {target} target "
                          f"({', '.join(ACTIONS[target])})")
        else:
            bindings[button] = action

    keys: dict[str, str] = {}
    raw_keys = data.get("keys", {})
    if not isinstance(raw_keys, dict):
        errors.append("keys must be an object (slot -> key)")
        raw_keys = {}
    for slot, key in raw_keys.items():
        if slot not in KEY_SLOTS[target]:
            errors.append(f"keys: '{slot}' is not a key of the {target} target ({', '.join(KEY_SLOTS[target]) or 'none'})")
        elif not keynames.is_key(key):
            errors.append(f"keys.{slot}: '{key}' is not a known key name (for example KeyW, Numpad8, ArrowUp, Space)")
        else:
            keys[slot] = key
    if fill_keys and KEY_SLOTS[target] and not errors:
        default = _builtin_default(target)
        for slot in KEY_SLOTS[target]:
            keys.setdefault(slot, default["keys"][slot])

    options: dict = {}
    raw_options = data.get("options", {})
    if not isinstance(raw_options, dict):
        errors.append("options must be an object")
        raw_options = {}
    spec = OPTIONS[target]
    for opt, value in raw_options.items():
        if opt not in spec:
            errors.append(f"options: '{opt}' is not an option of the {target} target ({', '.join(spec) or 'none'})")
            continue
        kind, lo, hi, _default = spec[opt]
        if kind is bool:
            if isinstance(value, bool):
                options[opt] = value
            else:
                errors.append(f"options.{opt} must be true or false")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
            errors.append(f"options.{opt} must be a number from {lo:g} to {hi:g}")
        else:
            options[opt] = value
    for opt, (_kind, _lo, _hi, default) in spec.items():
        options.setdefault(opt, default)

    return {"version": VERSION, "id": pid, "name": name.strip(), "target": target, "ride": ride,
            "bindings": bindings, "keys": keys, "options": options}, errors


_builtin_cache: dict[str, dict] = {}


def _builtin_default(target: str) -> dict:
    pid = DEFAULT_ID[target]
    if pid not in _builtin_cache:
        profile, errors = validate(_read(builtin_dir() / f"{pid}.json"))
        if errors:                                        # a broken shipped file is a bug, not a user error
            raise RuntimeError(f"built-in profile {pid}: {errors}")
        _builtin_cache[pid] = profile
    return _builtin_cache[pid]


# ---------------------------------------------------------------------------------------------------- running
def current(target: str) -> dict:
    """The active profile if it is for ``target``, else that target's built-in default."""
    p = state.get("profile")
    return p if p and p["target"] == target else _builtin_default(target)


def action_buttons(target: str, action: str) -> list[str]:
    """The physical buttons bound to ``action``."""
    return [b for b, a in current(target)["bindings"].items() if a == action]


def held(target: str, action: str, raw) -> bool:
    """Is any button bound to ``action`` held? (``raw`` is the set of held physical buttons.)"""
    bindings = current(target)["bindings"]
    return any(bindings.get(b) == action for b in raw)


def apply(profile: dict) -> None:
    """Make ``profile`` the active one: its keys, and its ride settings when those changed."""
    from . import keys
    prev = state.get("profile")
    state["profile"] = profile
    state["profile_id"] = profile["id"]
    keys.apply_keys(profile["keys"])
    if prev is None or prev.get("ride") != profile["ride"]:
        ride = profile["ride"]
        apply_preset(ride.get("mode", "easy"))
        if "gain" in ride:
            state["gain"], state["preset"] = ride["gain"], "custom"
        if "difficulty" in ride:
            state["difficulty"], state["preset"] = ride["difficulty"], "custom"
        if "pmax" in ride:
            state["pmax"] = ride["pmax"]
        if "ftp" in ride:
            state["ftp"] = int(ride["ftp"])
        if "smooth" in ride:
            state["smooth"] = ride["smooth"]


def describe(profile: dict) -> dict:
    """What the dashboard's Controls page needs to draw itself."""
    target = profile["target"]
    return {
        "profile": profile, "target": target,
        "buttons": [{"name": n, "label": label} for n, label in BUTTONS],
        "actions": [{"name": a, "label": ACTION_LABELS[a]} for a in ACTIONS[target]],
        "key_slots": [{"name": s, "label": KEY_SLOT_LABELS[s]} for s in KEY_SLOTS[target]],
        "key_labels": {k: keynames.label(k) for k in keynames.KEYS},
        "options": {o: {"type": "bool" if spec[0] is bool else "number", "min": spec[1], "max": spec[2], "default": spec[3]}
                    for o, spec in OPTIONS[target].items()},
        "ride_fields": {f: {"min": lo, "max": hi} for f, (lo, hi) in RIDE_FIELDS.items()},
        "modes": list(PRESETS),
    }
