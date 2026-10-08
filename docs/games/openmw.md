# OpenMW / Morrowind

Ride through Vvardenfell: pedalling walks (and runs) the character, the Click turns it, and the island's real hills change your trainer's resistance.

Tested with **OpenMW 0.51** and the original Morrowind. It should work with other recent versions that have the player Lua API (0.49+).

## Install

```bash
python -m pedalator install openmw
```

This copies the mod to `<your OpenMW user folder>/mods/Pedalator` and enables it in your `openmw.cfg` (a timestamped backup is written next to it). Look first with `--dry-run`. Options: `--user-dir` (the folder that holds `openmw.cfg`), `--dest` (where to put the mod).

The installer is idempotent, and removes the entries of the mod's earlier name (`TrainerBike`). To uninstall, delete the two lines it added (`data="…/Pedalator"` and `content=Pedalator.omwscripts`).

## Run

```bash
python -m pedalator --target openmw             # PC talks to the trainer
python -m pedalator --target openmw --remote    # phone/laptop talks to the trainer
```

Start OpenMW and load a save. While Pedalator is running and the trainer sends data, the mod takes over **forward movement, turning, looking, jumping and attacking**. When Pedalator stops (or in menus and dialogues) the keyboard and mouse work as usual.

## Controls (Zwift Click)

| Button | Action |
|---|---|
| ◀ / ▶ | turn left / right |
| ▲ / ▼ | look up / down |
| **B** | attack (hold = charged blow; a spell is cast once per press) |
| **A** | jump |
| **Y** | draw / sheathe the weapon |
| **− / +** | difficulty: fewer / more of the game's hills on the trainer; the mod shows the new value on screen |
| **Z** | use — open, take, talk. Pedalator presses the game's *use* key: `E` by default, change with `--openmw-use-key f\|space\|enter` to match your OpenMW key bindings |

The mapping is the `BUTTONS` table in [`pedalator/targets/openmw.py`](../../pedalator/targets/openmw.py).

## How hills reach the trainer

The mod measures the slope of the ground under the character and prints `PEDALATOR grade=<percent>` into `openmw.log`. Pedalator reads the end of that log and sets the trainer's resistance from it (scaled by your [riding mode](../../README.md#riding-modes)). Pedalator finds the log and the mod's state file through your `openmw.cfg`; pass `--openmw-log` / `--openmw-state` if yours are elsewhere.

## Tuning

Edit `scripts/pedalator/player.lua` in the mod folder (changes apply when the game loads a save):

| Constant | Meaning |
|---|---|
| `TURN_RATE`, `PITCH_RATE` | turning and looking speed |
| `RUN_ABOVE` | how much "gas" (0–1) turns walking into running |
| `USE_SPEED_ATTRIBUTE`, `SPEED_BOOST` | alternative: raise the *Speed* attribute with power (if analog movement is not enough for you) |
| `DEBUG` | print what the mod reads every two seconds |

How hard you must pedal is set in Pedalator (`--mode`, `--gain`, `--pmax`), not in the mod.

## How it works (for modders)

Lua in OpenMW cannot open sockets or write files, so the two directions use what it *can* do:

- **Pedalator → game:** Pedalator rewrites `pedalator/state.txt` inside the mod's data folder about 20 times a second; the mod reads it with `vfs.open` every frame it needs it. The line format is in [Architecture](../architecture.md#openmw-state-file).
- **game → Pedalator:** `print()` into the log, tailed by Pedalator.
- The mod calls `I.Controls.overrideMovementControls` and `overrideCombatControls` only while the state file is fresh (< 1 s old).
- OpenMW has no Lua call for "use what I am looking at", so *use* is a real key press.

## Known limits

- The mod expects the state file to exist when the game starts (the installer creates it).
- The character walks at Morrowind's speed; "bicycle" speed needs the Speed attribute or Athletics. Tune to taste.
- Occasionally the file is read mid-write (error 32 in the log); the mod just keeps the last values.
