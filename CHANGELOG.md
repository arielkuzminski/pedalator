# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Changed
- **Newest toolchain:** Python **3.13 or newer** is required (3.13 and 3.14 are tested, 3.15 is tried and may fail), `bleak` 3, `cryptography` 50, pytest 9 and ruff 0.16, and CI runs on the newest GitHub actions with the current Node LTS (the JavaScript tests failed on Node 20).
- A ride in a UDP game no longer leaves two UDP sockets open after it ends.

### Added
- **A single-file Windows program** (`pedalator-<version>-windows.exe`, built with PyInstaller by `.github/workflows/release.yml` and attached to each release, with a SHA-256 file). No Python needed. It is not code-signed, so Windows SmartScreen may warn on the first run. Build it yourself with `python tools/build_exe.py`.

## [0.2.0] — the launcher

### Changed
- The throttle key's loop asks Windows for 1 ms timer ticks, so it runs every 50 ms instead of 62.5 ms (a finer "gas").
- The dashboard's default port is now **2137** (was 8765); `--dashboard-port` still sets it.

### Added
- **"No gas below" setting** (Ride tab slider, profile field `ride.floor`, 15 W by default as before): a trainer that estimates power from its wheel keeps showing some power while the wheel spins down after you stop, so the game kept moving; raise the floor to cut that tail.
- **Smooth the gas** (Ride tab checkbox, profile field `ride.smooth`, on by default): a trainer reports the power of the moment, which dips under the 15 W floor between pedal strokes and when you ease off, so the gas (and a held key) flickered. With the option a dip shorter than 0.8 s keeps the gas and a real stop lets go; without it the gas follows every reading, so stopping pedalling stops at once. A ride that ends always tells the game "no gas" at once.
- **Flow check** (Ride tab, "Flow check"; also `GET /diag`, `POST /diag/start`): records 15-60 s of a ride and times four stages with one clock, the trainer's Bluetooth packets, Pedalator's throttle loop, the key presses it sends and what Windows delivers (a low-level keyboard hook), then names the first stage that is not smooth. Without a trainer, `python -m pedalator.diag` presses a harmless key (F9) with a synthetic rider.
- **Bluetooth signal strength:** the header shows the dBm the trainer and the Click had when the PC found them (red dot when weak), and the Start page has **Check signal strength**, a short scan for placing the adapter before a ride. Windows gives no signal reading for a connected device, so the header shows the value from the last discovery, not a live one.
- **Start page (launcher):** `pedalator` with no game or rider now opens only the dashboard. Choose a game, pick the trainer (simulated, this PC's Bluetooth, phone) and the Click, press **Start riding**; **Stop** releases the trainer, the Click, the game's port and the phone servers so another game can be started without restarting. Giving a game or a rider on the command line still starts riding at once; `--launcher` forces the Start page. New `pedalator/session.py`; `--target` no longer defaults to `keys` (a profile alone now brings its own target).
  The Start page explains what to do for each game (numbered steps) and can add the OpenMW mod for you with one button, showing first what will change in `openmw.cfg` (a backup is made).
- **Game tab in the dashboard:** the new-game wizard as a form, a live test panel (gas, turning, Click buttons, the UDP packet, a key tester) and an editor for the generated files. See [docs/new-game.md](docs/new-game.md).
- **`pedalator new-game`:** a wizard that sets up a new game: a saved profile, a README with the steps and, for UDP games, a listener and a Lua sketch. See [docs/new-game.md](docs/new-game.md).
- **Profiles:** one JSON file per game or setup holds the button map, the keys, the ride defaults and game options. A new **Controls** tab in the dashboard remaps buttons and keys live and saves, exports and imports profiles; `--profile` and `pedalator profile list|show|export|import|delete` on the command line; the OpenMW mod reads its tuning from a config file. See [docs/profiles.md](docs/profiles.md).
- The dashboard now refuses requests with a foreign `Host` header and non-JSON `POST`s, so another web page cannot drive it.

- **Click + and − change the trainer's difficulty** (10 points of the game's hills per press, repeating while held), with feedback on the dashboard, the phone page and in OpenMW. On a Click v2 − and + no longer steer in the `keys` target.

- **Zwift Click over the PC's own Bluetooth** (`pedalator/click.py`): with a BLE adapter, no phone is needed for the Click. Flag `--click auto|off`; the dashboard shows a *controls* light; trainer and Click scans never overlap. Not yet tested on a real controller through the PC.

- **Hybrid mode:** `--trainer pc|phone` and `--click pc|phone|off` choose who reads the trainer and the Click (`--remote` stays as the shorthand). The phone page hides what the PC reads itself, and the PC refuses data it does not want.

### Planned (see [docs/roadmap.md](docs/roadmap.md#next-up))
- A socket-less (file and log) template for the wizard.

## [0.1.0] — first public release

### Added
- Reading a **Bluetooth FTMS smart trainer**: power, cadence, speed, distance, heart rate; setting the simulated grade. Tested on a Van Rysel D500.
- **Phone mode** (`--remote`): an iPhone with Bluefy, or a laptop with Chrome, reads the trainer and the Zwift Click over Web Bluetooth and sends the data to the PC over HTTPS on the LAN; own certificate authority, token, keep-alive connections.
- **Zwift Click** support: Click v2 (tested) and v1 decoders; buttons are reported by name to the game targets.
- **Dashboard** (`127.0.0.1:8765`): power gauge with zones, cadence, speed, grade, history, debug view; riding modes *easy / medium / realistic* with fine-tuning; manual resistance. English and Polish.
- **Game targets:** `openmw` (OpenMW mod: walking, turning, looking, jumping, attacking, drawing the weapon, *use*; the ground's slope back to the trainer), `keys` (numpad or WASD key output; Windows), `udp` (JSON datagrams for any scripted game).
- **openOMSI:** Lua plugin sending the road gradient; `build-bike` creates a bicycle from the user's own HafenCity add-on.
- **Installers:** `install openmw` (copies the mod, edits `openmw.cfg` with a backup), `install openomsi`.
- `--simulate` mode, `tools/make_demo.py`, tests (Python and JavaScript) and CI.

### Known limitations
- Alpha: one trainer, one controller, two games and one PC were tested.
- Key output is Windows-only.
- Direct Bluetooth needs a BLE-central-capable adapter; otherwise use phone mode.
