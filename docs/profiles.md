# Profiles: your buttons, your keys

A **profile** is one small JSON file that says how Pedalator behaves for one game or setup: which Click button does what, which keys are pressed, how hard the ride is, and a few game-specific tunings. Everything on the dashboard's **Controls** tab edits a profile, and every change applies at once, with no restart.

Built-in profiles: `morrowind` (OpenMW), `omsi` and `generic-wasd` (keys), `generic-udp` (UDP). Yours are stored in `%LOCALAPPDATA%\Pedalator\profiles` and win over a built-in with the same id.

## In the dashboard

Open the **Controls** tab.

- **Profile picker**: switch profile (only those for the current `--target` are offered).
- **Buttons**: for each Click button choose an action from the list, or *none*. The button you press lights up, so you can find it.
- **Keys**: click a key slot, then press the key you want. Modifier keys such as Alt and the Windows key are not allowed, so a profile cannot trigger shortcuts.
- **Options**: game-specific tuning (OpenMW: turn and look speed, run threshold, speed-attribute mode).
- **Ride**: default mode, gain, difficulty, `pmax`, `ftp`, `smooth` (keep the gas through short dips of the power).
- **Save** overwrites your profile, **Save as…** makes a new one (a built-in is never changed), **Reset** returns to the saved state, **Export** downloads the JSON, **Import** loads a file and shows what is wrong with it, if anything.

Unsaved edits work in the running session but are lost on restart; the Controls tab marks them as *unsaved*.

## On the command line

```
pedalator --target openmw --profile morrowind
pedalator --profile C:\path\to\friend.json      # a file works too
pedalator profile list
pedalator profile show morrowind
pedalator profile export morrowind --out my-morrowind.json
pedalator profile import my-morrowind.json --id my-morrowind [--overwrite]
pedalator profile delete my-morrowind
```

`--keyset wasd` still works and means `--profile generic-wasd`.

## The file format

```json
{
  "version": 1,
  "id": "morrowind",
  "name": "Morrowind (OpenMW)",
  "target": "openmw",
  "bindings": { "LEFT": "turn_left", "B": "attack", "PLUS": "difficulty_up" },
  "keys":     { "use": "KeyE" },
  "options":  { "turn_rate": 1.7, "run_above": 0.55 },
  "ride":     { "mode": "easy", "pmax": 300 }
}
```

- `target`: `keys`, `openmw` or `udp`.
- `bindings`: button (`UP DOWN LEFT RIGHT A B Y Z MINUS PLUS`) to action. The actions depend on the target (`steer_left`, `brake`, `attack`, `jump`, `difficulty_up`…). Use `"none"` to leave a button free.
- `keys`: slot to a browser key name (`KeyW`, `Numpad8`, `ArrowUp`, `Space`…). Missing slots take the target's default.
- `options`: see the dashboard for the list and the allowed ranges.
- `ride`: any of `mode`, `gain`, `difficulty`, `pmax`, `ftp`, `smooth` (true/false). These are applied when you select the profile, not on every edit, so changing a button never resets the difficulty you set with the Click.

A bad file is never half-applied: the importer lists every problem (unknown button, action from another target, unknown key, number out of range…) and changes nothing.

## How the game mod gets its tuning

The game's mod is not edited. Pedalator writes the relevant options to a tiny `config.txt` next to the state file, and the OpenMW mod reads it the same way it reads the state (`turn_rate=1.7;pitch_rate=1.2;…`). Change a value in the dashboard and the next frames use it.

## Sharing

Export the JSON and send it. A friend runs `pedalator profile import file.json` or uses **Import** on the Controls tab. Profiles contain no personal data or paths.

## The dashboard API

All `POST` bodies must be `application/json`, and the dashboard only answers requests addressed to `127.0.0.1` or `localhost` (see [SECURITY.md](../SECURITY.md)).

| Request | What it does |
|---|---|
| `GET /profile` | active profile plus everything the page needs to draw the form |
| `GET /profiles` | list of available profiles |
| `GET /profile/export?id=…` | download one as a file |
| `POST /profile/apply` | try an edited profile (nothing is saved) |
| `POST /profile/select` | switch to a saved profile |
| `POST /profile/save` | save as yours (`name`, optional `id`) |
| `POST /profile/delete` | delete one of yours |
| `POST /profile/import` | `text`, optional `id`, `overwrite` |
