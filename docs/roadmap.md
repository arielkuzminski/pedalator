# Roadmap

Pedalator works today with [OpenMW](games/openmw.md), [openOMSI](games/openomsi.md) and, through keys or UDP, a good range of other things. This page lists the **next five milestones** and then a wider collection of **ideas** — especially other games. Nothing here is promised; pick something and send a pull request, or open an issue to say you are working on it.

## Next up

The five milestones the maintainer plans to build first, in the order of the suggested path. They are the best places to help, too: open an issue to say you are on one.

> Suggested order: **5 → 1 → 2 → 3 → 4**. (5 is small and useful at once; 1 and 2 finish "ride with just a USB adapter or a laptop"; 3 is the biggest piece and 4 builds on it.)

### 1. Zwift Click over the PC's Bluetooth (no phone)

**Why.** With a USB Bluetooth 5 adapter the PC reads the trainer itself, but today the Click is read only by the phone/laptop page. One device, no browser, no certificates.

**How.** A new `pedalator/click.py`: a Python port of the decoder in `phone.html` (same `ButtonMap` bits, same `0x23` / `0x37` frames) and a `bleak` loop that finds the Click (Zwift service UUIDs or manufacturer data `0x094A`), writes `RideOn`, subscribes, fills `state["raw"]`, `state["buttons"]` and `state["t_buttons"]`, and reconnects. A flag `--click auto|off` (auto when the PC reads the trainer over Bluetooth). The decoder gets the same test vectors as the JavaScript tests (`tests/js`), so the two stay in step.

**Risks.** Needs a BLE-central adapter; a Click accepts one connection (so not the phone page at the same time); the first run on real hardware.

**Done when.** `pedalator --target openmw` with a USB adapter reads the trainer *and* the Click, every button works, and no phone is involved.

### 2. Hybrid mode: trainer on the PC, Click on a laptop or phone

**Why.** The PC's adapter may reach the trainer but not the Click's corner of the room, or you want the phone free for filming.

**How.** Replace the all-or-nothing `--remote` by `--trainer pc|phone` and `--click pc|phone|off` (`--remote` stays as "both from the phone"). The phone page learns `?only=click` and `?only=trainer`, hides the other connect button and sends only its own data.

**Done when.** `pedalator --trainer pc --click phone` runs, with the laptop connecting only the Click.

### 3. Profiles: import and export of a game's configuration, remappable keys in the dashboard

**Why.** Someone else may want other keys for Morrowind, a different attack button, different tuning — without editing source.

**What a profile is.** One JSON file (versioned and validated) per game or setup:

- the target;
- the **Click button → action** map;
- **key bindings** for the `keys` target and OpenMW's *use* key (key names and scan codes);
- the riding mode and the default gain, difficulty and `pmax`;
- game-specific options (OpenMW: turning and looking speed, the run threshold, the speed-attribute mode).

Built-in profiles ship in the package (`morrowind`, `omsi`, `generic-wasd`); yours live in the user data folder.

**A note on Lua.** The profile is JSON, not Lua, and a game's Lua mod must not need hand-editing: Pedalator writes the relevant part of the active profile to a small config file that the mod reads the same way it reads the state file today (`vfs.open`, no new permissions). So **export** is a profile file you can share, and **import** is dropping it in or uploading it in the dashboard.

**Dashboard.** A new **Controls** page: a table of Click buttons with an action dropdown for each; "press a key" capture for key bindings; a profile picker; *Save*, *Save as…*, *Reset*, **Export** (download) and **Import** (upload) with validation errors shown; changes apply immediately. API: `GET/POST /profile`, `GET /profiles`, `POST /profiles/import`.

**Command line.** `--profile morrowind`, `pedalator profile list|export|import`.

**Done when.** Changing the OpenMW attack button in the dashboard works without restarting, survives a restart, and a friend can import the exported file.

### 4. A wizard for a new game

**Why.** Today, adding a game means reading the architecture notes. A wizard makes "support my game" a ten-minute job.

**How.** `pedalator new-game` (later also a dashboard page). It asks the game's name; how the game can be reached (keyboard only / a mod with UDP / a mod without sockets, so a file and the log / telemetry); and whether it can report the slope of the ground. It then generates a **profile** (milestone 3), a **starter mod** from templates (Lua for an engine without sockets, a UDP stub, or a keys-only profile), a docs stub in `docs/games/` and a test stub, and prints the exact steps to try it. A **test panel** in the dashboard shows what Pedalator is sending (gas, turning, buttons) and lets you capture the game's own keys.

**Depends on** milestone 3.

**Done when.** A new keys-only game can be added through the wizard without touching Python.

### 5. Click + and − change the trainer's difficulty

**Why.** Hills too hard on a long climb? Change it without leaving the saddle.

**How.** A loop that watches the physical `PLUS` and `MINUS` buttons for every target: each press moves the **share of the game's hills the trainer simulates** by ±10 percentage points (0–100 %), holding repeats after 0.5 s, and the riding mode becomes "custom". Feedback on the dashboard and the phone page, and optionally in the game (the OpenMW mod can show a message from a `diff=` field of the state line). A possible extension: also move the *power gain*.

**To settle.** On a Click v2 − and + currently steer in the `keys` target and are free in OpenMW; they would move to difficulty, while the arrows on the left puck keep steering. On a Click v1 (two buttons) steering stays, unless a profile says otherwise (milestone 3).

**Done when.** Pressing + or − changes `state["difficulty"]`, the dashboard and the trainer's resistance follow, and the value is remembered in the profile.

## What makes a game easy to connect

Pedalator needs two things from a game:

1. **A way in:** a way to set how fast the player or vehicle moves and to turn, jump, attack… A keyboard is enough for driving; a mod or script is better.
2. **A way out (optional but it is the best part):** the *slope under the player*, so the trainer can make climbs heavy. A mod/script that can read the player's position, or a telemetry feed, gives it.

| The game offers… | What to build | Examples in this list |
|---|---|---|
| a scripting/mod API **with sockets** | a mod that talks UDP — the [`udp` target](games/keys-and-udp.md) exists | Luanti, Minecraft (Java mods), game engines with plugins |
| a scripting API **without sockets** (but files or the log) | the OpenMW way: a state file in, log lines out | OpenMW (done), Garry's Mod, Cyberpunk 2077 |
| a **telemetry feed** (UDP or shared memory) | read the slope from telemetry; control with keys or a virtual gamepad | Euro Truck Simulator 2, Assetto Corsa, Forza, F1 |
| **nothing** | keys only; hills by hand with the *Manual* slider | most games |

## Games worth trying

Status: ✅ done · 💡 idea. "Effort" is a rough guess. APIs of these games change; check the current docs before starting.

### Walk-around and RPG games (the character's speed follows your power)

| Game | How | Hills out | Effort | Status |
|---|---|---|---|---|
| **Morrowind** (OpenMW) | Lua mod, state file in, log out | ✅ | – | ✅ |
| **Luanti** (formerly Minetest) | Lua mod; `player:set_physics_override({speed = …})` changes walking speed; UDP/HTTP through the mod environment | from the player's position | low | 💡 |
| **Skyrim SE / Fallout 4** | script-extender plugin (SKSE/F4SE) or Papyrus actor-value changes; UDP from a native plugin | from the player's position | medium | 💡 |
| **Minecraft** (Fabric/Forge) | Java mod: movement speed attribute, UDP socket | from the player's position | low–medium | 💡 |
| **Cyberpunk 2077** | Cyber Engine Tweaks (Lua) — check what I/O it allows | from the player's position | medium | 💡 |
| **Garry's Mod** | Lua; read a file in `data/`; print/console for the way out | from the player's position | low–medium | 💡 |
| **Daggerfall Unity** | Unity mod in C# (open-source engine) | from the player's position | medium | 💡 |

### Driving, riding and flying

| Game | How | Hills out | Effort | Status |
|---|---|---|---|---|
| **OMSI 2 / openOMSI** | Lua plugin + keys; a bicycle built from the HafenCity add-on | ✅ | – | ✅ |
| **BeamNG.drive** | Lua in the game (and UDP *OutGauge* telemetry); bicycles exist as community mods | vehicle pitch | medium | 💡 |
| **Euro Truck Simulator 2 / American Truck Simulator** | telemetry SDK plugin (shared memory) for slope/speed, keys or a virtual gamepad for input | telemetry | medium | 💡 |
| **Assetto Corsa** | shared-memory telemetry; Python apps in-game | telemetry | medium | 💡 |
| **Forza Horizon/Motorsport, F1 games** | UDP telemetry out ("Data Out"); virtual gamepad in | telemetry | medium | 💡 |
| **GTA V** | a script (ScriptHookV / ScriptHookVDotNet, or Lua on FiveM) reading UDP; [GTBikeV](https://www.gta5-mods.com/scripts/gt-bike-v) already does a lot of this on its own | from the vehicle | medium | 💡 |
| **Red Dead Redemption 2** | ScriptHookRDR2: pedal your horse | from the player | medium | 💡 |
| **X-Plane** | plugin or FlyWithLua (check whether sockets are available); a pedal-powered aircraft | datarefs | medium | 💡 |
| **OpenRCT2, other open-source games** | plugins (JavaScript in OpenRCT2) | – | varies | 💡 |

### Virtual reality

| Game | How | Status |
|---|---|---|
| **Half-Life: Alyx** (and other VR games with scripting) | pedal locomotion through a script that reads UDP | 💡 |

## Features

### Input and output

- 💡 **Virtual gamepad target** (ViGEm): trigger = power, sticks = Zwift Click. Makes *any* gamepad game work, with analog gas instead of key pulses.
- 💡 **Linux and macOS key output** (`uinput`, `CGEvent`).
- 💡 **ANT+ FE-C** for trainers without Bluetooth FTMS, through a USB ANT+ stick.
- 💡 **Other controllers:** Zwift Play, Zwift Ride, other Bluetooth buttons and gamepads as extra inputs.
- 💡 **Trainer extras:** resistance level mode, ERG mode for workouts, wind and surface (rough road, grass) from the game.

### Experience

- 💡 **Per-vehicle gas curves** in OMSI (bicycle vs bus): a different gas curve for each, chosen automatically from the plugin.
- 💡 **In-game overlay** of power, cadence and grade.
- 💡 **Heart-rate and zone** handling (limit effort, "stay in Z2" challenges).
- 💡 **Session export** (FIT/TCX) so a Morrowind ride counts as a ride on your training platform.
- 💡 **Hill-aware difficulty:** keep the average gradient the trainer simulates within a range.

### Project

- 💡 **`pedalator doctor`** command: checks Python, Bluetooth, ports, firewall, game installs.
- 💡 **Config file** (TOML) and remembered settings.
- 💡 **Windows installer / single-file exe** (PyInstaller), and a PyPI package.
- 💡 More dashboard languages (translations live in a small dictionary at the top of each page script).
- 💡 More tests with a fake trainer (a recorded FTMS packet replay).

## How to add a game

Read [Development → Adding a game](development.md#adding-a-game). The shortest route is the `udp` target plus a mod in your game that sends `grade=…;speed=…` to UDP 27100 and reads Pedalator's JSON.
