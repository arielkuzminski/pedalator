# Quick start

## What you need

- A **Bluetooth smart trainer** that speaks FTMS (almost every modern one does). Tested: Van Rysel D500.
- Optional: **Zwift Click** controllers for steering and actions.
- **Python 3.10 or newer** on a Windows PC (Windows 10/11).
- A game: [OpenMW](games/openmw.md) with Morrowind, [openOMSI](games/openomsi.md), or [any game with keyboard controls](games/keys-and-udp.md).
- Bluetooth on the PC that can talk to a trainer (a "BLE central"). If yours cannot, use [phone mode](phone-mode.md) — it takes five minutes more.

## Install

```bash
git clone https://github.com/arielkuzminski/pedalator
cd pedalator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Everything below is run from this folder with `python -m pedalator ...`.

## 0. The easy way: the Start page

```bash
python -m pedalator
```

With no options, Pedalator opens only the dashboard (<http://127.0.0.1:8765>) on its **Start** tab. Choose a game (or make one with *New game*), say how you ride (a simulated rider, this PC's Bluetooth or a phone; the Click automatic, on the PC, on the phone or off) and press **Start riding**. Only then are the trainer, the Click and the game connected. **Stop** (on the Start page or in the header) lets everything go again, so you can pick another game without restarting. The sections below do the same from the command line: giving a game or a rider (`--target`, `--profile`, `--simulate`, `--remote`, `--keys`…) starts riding at once, as before; `--launcher` forces the Start page.

## 1. Try it without hardware

```bash
python -m pedalator --simulate
```

Open <http://127.0.0.1:8765>. A made-up rider sprints and rests every 45 seconds. Switch the **riding mode**, move the **Manual** resistance slider, watch the power zones. Stop with `Ctrl+C`.

## 2. Check that your trainer is found

Close every other app that uses the trainer (Zwift, a phone app, a head unit) — most trainers accept only one connection.

```bash
python -m pedalator --target keys
```

It scans for a trainer for 8 seconds and connects; if a **Zwift Click** is awake nearby it connects to that too (`--click off` to skip it). The dashboard's lights turn green and the power gauge moves when you pedal.

- *"BLE 'central' role not supported on this adapter"* → your PC's Bluetooth is too old: use [phone mode](phone-mode.md) (`--remote`).
- *"no FTMS trainer found"* → wake the trainer by spinning the pedals, close other apps, move closer.

## 3. Pick a game

| Game | Set up once | Run |
|---|---|---|
| Morrowind (OpenMW) | `python -m pedalator install openmw` | `python -m pedalator --target openmw` |
| openOMSI | see the [openOMSI guide](games/openomsi.md) | `python -m pedalator --keys` |
| Another game | [Keys and UDP](games/keys-and-udp.md) | `python -m pedalator --keys --keyset wasd` |

Add `--remote` to any of these if the phone or laptop does the Bluetooth.

## Handy options

| Option | What it does |
|---|---|
| `--mode easy\|medium\|real` | how much power moves you and how much of the game's hills you feel (default `easy`) |
| `--ftp 220` | your FTP in watts, for the power zones on the dashboard |
| `--pmax 250` | power that means "full throttle" at gain ×1 |
| `--address AA:BB:...` | connect to this trainer instead of scanning |
| `--trainer pc\|phone`, `--click pc\|phone\|off` | who reads the trainer and the Click ([hybrid mode](phone-mode.md#hybrid-mode-the-pc-reads-one-thing-the-phone-the-other)) |
| `--dashboard-port 8765` | the dashboard's port |
| `python -m pedalator --help` | everything |

## Stopping

`Ctrl+C` in the console. Keys that Pedalator was holding are released.

Next: [phone mode](phone-mode.md) · [Zwift Click](zwift-click.md) · [Troubleshooting](troubleshooting.md)
