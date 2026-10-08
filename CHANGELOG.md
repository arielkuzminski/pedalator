# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- **Click + and − change the trainer's difficulty** (10 points of the game's hills per press, repeating while held), with feedback on the dashboard, the phone page and in OpenMW. On a Click v2 − and + no longer steer in the `keys` target.

### Planned (see [docs/roadmap.md](docs/roadmap.md#next-up))
- Zwift Click over the PC's Bluetooth, without a phone.
- Hybrid mode: the trainer on the PC, the Click on a laptop or phone.
- Profiles: import and export of a game's configuration, remappable keys in the dashboard.
- A wizard for adding a new game.

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
