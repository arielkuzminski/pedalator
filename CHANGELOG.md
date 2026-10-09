# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
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
