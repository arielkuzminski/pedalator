"""Key names for profiles: the same names a browser gives (``KeyboardEvent.code``), mapped to hardware scan codes.

Using the physical-key names (``KeyW``, ``Numpad8``, ``ArrowUp``…) means the dashboard can capture a key press and
store it as is, and a key means the same on every keyboard layout. Modifier keys other than Shift and Ctrl and the
Windows key are left out on purpose: a profile must not be able to press shortcuts.
"""
from __future__ import annotations

# name -> (scan code, extended?)  (set-1 scan codes; "extended" keys are sent with the E0 prefix)
KEYS: dict[str, tuple[int, bool]] = {}


def _add(name: str, scan: int, ext: bool = False) -> None:
    KEYS[name] = (scan, ext)


for _n, _s in zip("QWERTYUIOP", range(0x10, 0x1A), strict=True):
    _add(f"Key{_n}", _s)
for _n, _s in zip("ASDFGHJKL", range(0x1E, 0x27), strict=True):
    _add(f"Key{_n}", _s)
for _n, _s in zip("ZXCVBNM", range(0x2C, 0x33), strict=True):
    _add(f"Key{_n}", _s)
for _n, _s in zip("1234567890", range(0x02, 0x0C), strict=True):
    _add(f"Digit{_n}", _s)
for _n, _s in zip("0123456789", (0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49), strict=True):
    _add(f"Numpad{_n}", _s)
for _i, _s in enumerate(range(0x3B, 0x45), start=1):
    _add(f"F{_i}", _s)
_add("F11", 0x57)
_add("F12", 0x58)
for _name, _s in (("Space", 0x39), ("Enter", 0x1C), ("Tab", 0x0F), ("Backspace", 0x0E), ("Escape", 0x01),
                  ("ShiftLeft", 0x2A), ("ControlLeft", 0x1D),
                  ("Comma", 0x33), ("Period", 0x34), ("Slash", 0x35), ("Semicolon", 0x27), ("Quote", 0x28),
                  ("BracketLeft", 0x1A), ("BracketRight", 0x1B), ("Minus", 0x0C), ("Equal", 0x0D),
                  ("Backquote", 0x29), ("Backslash", 0x2B),
                  ("NumpadAdd", 0x4E), ("NumpadSubtract", 0x4A), ("NumpadMultiply", 0x37), ("NumpadDecimal", 0x53)):
    _add(_name, _s)
for _name, _s in (("ArrowUp", 0x48), ("ArrowDown", 0x50), ("ArrowLeft", 0x4B), ("ArrowRight", 0x4D),
                  ("Insert", 0x52), ("Delete", 0x53), ("Home", 0x47), ("End", 0x4F), ("PageUp", 0x49),
                  ("PageDown", 0x51), ("NumpadEnter", 0x1C), ("NumpadDivide", 0x35)):
    _add(_name, _s, ext=True)

_LABELS = {"Space": "Space", "Enter": "Enter", "Tab": "Tab", "Backspace": "Backspace", "Escape": "Esc",
           "ShiftLeft": "Left Shift", "ControlLeft": "Left Ctrl", "ArrowUp": "↑", "ArrowDown": "↓", "ArrowLeft": "←",
           "ArrowRight": "→", "NumpadAdd": "Numpad +", "NumpadSubtract": "Numpad −", "NumpadMultiply": "Numpad ×",
           "NumpadDivide": "Numpad ÷", "NumpadDecimal": "Numpad .", "NumpadEnter": "Numpad Enter",
           "Comma": ",", "Period": ".", "Slash": "/", "Semicolon": ";", "Quote": "'", "BracketLeft": "[",
           "BracketRight": "]", "Minus": "-", "Equal": "=", "Backquote": "`", "Backslash": "\\",
           "PageUp": "Page Up", "PageDown": "Page Down"}


def label(name: str) -> str:
    """A friendly name for a key, e.g. ``KeyW`` -> ``W``, ``Numpad8`` -> ``Numpad 8``."""
    if name in _LABELS:
        return _LABELS[name]
    if name.startswith("Key"):
        return name[3:]
    if name.startswith("Digit"):
        return name[5:]
    if name.startswith("Numpad"):
        return "Numpad " + name[6:]
    return name


def is_key(name: object) -> bool:
    return isinstance(name, str) and name in KEYS


def scan(name: str) -> tuple[int, bool]:
    return KEYS[name]
