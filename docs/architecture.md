# Architecture

## The pieces

```
                 Bluetooth                         HTTPS on the LAN (phone mode only)
 trainer  ◀──────────────────▶  PC adapter ─┐
 Zwift Click ◀── (via phone) ──▶ phone/laptop ──────────────▶ phone_server ─┐
                                                                            ▼
                                  ble.py ────────────────────▶  state.py (one shared dict)
                                                                            │
                          dashboard_server.py  ◀── snapshot ────────────────┤
                                                                            ▼
                                       targets/keys · targets/openmw · targets/udp  ──▶  the game
                                                       ▲
                                  loops.py (UDP in: the game's gradient)
```

Everything runs in one Python process: an `asyncio` loop for Bluetooth and the game targets, and small HTTP servers in threads. All of them read and write the dict in [`pedalator/state.py`](../pedalator/state.py); nothing else is shared.

| Module | Job |
|---|---|
| `cli.py` | command line; wires the tasks together |
| `state.py` | the shared state, riding modes, `effective_grade()`, `throttle_for()` |
| `ftms.py` | FTMS constants, parser of Indoor Bike Data, the simulation command, handlers |
| `ble.py` | direct Bluetooth LE with `bleak` (scan, connect, write the gradient every second); one scan at a time |
| `click.py` | the Zwift Click over the PC's Bluetooth: decoder, device finder, session loop |
| `difficulty.py` | Click + / − change the share of the game's hills |
| `phone_server.py` | the HTTPS server for the phone page, its data and the gradient stream; the plain-HTTP CA server |
| `certs.py` | private CA, server certificate, the token, the LAN address |
| `dashboard_server.py` | the local dashboard and its JSON/SSE API |
| `keys.py` | Windows `SendInput` key output, the throttle PWM loop |
| `targets/openmw.py` | OpenMW: state file out, log tail in, the *use* key |
| `targets/udp.py` | the generic JSON-over-UDP target |
| `loops.py` | UDP listener for the game's gradient, session statistics, console status |
| `simulate.py` | the made-up rider |
| `paths.py` | where things live; finds OpenMW's config, log and the mod |
| `install.py`, `bike.py` | installers and the OMSI bicycle builder |
| `web/dashboard.html`, `web/phone.html` | the two pages (plain HTML/JS, no build step) |
| `data/` | the OpenMW mod, the openOMSI plugin, bike templates |

## Data flows

**Power → game.** The trainer's *Indoor Bike Data* notification is parsed (`ftms.parse_bike_data`) into `state["power"]`. A target turns it into "gas": `throttle_for(power) = clamp(power × gain / pmax)`, 0 below 15 W.

**Gradient → trainer.** A game reports the slope under the player; `state["game_grade"]` holds it. `effective_grade()` scales it by the riding mode's *difficulty* (or returns the dashboard's manual value) and `ble.py` (or the phone page) writes it to the trainer's Control Point as *Set Indoor Bike Simulation Parameters* once a second.

**Zwift Click → game.** The phone page decodes the notification and posts the *physical buttons* (and a few driving actions) to `/phone/buttons`; targets read `state["raw"]` / `state["buttons"]`. A target treats the buttons as released if no update arrived for 1.5 s (the page repeats the state every 0.4 s while a button is held).

## Ports and addresses

| Address | Protocol | Reachable from | Purpose |
|---|---|---|---|
| `127.0.0.1:8765` | HTTP | this PC | dashboard (`--dashboard-port`) |
| `0.0.0.0:8766` | HTTPS | your LAN | phone page and API; needs the token (`?t=…`) |
| `0.0.0.0:8767` | HTTP | your LAN | only `ca.crt`, to install on the phone |
| `127.0.0.1:27100/udp` | UDP | this PC | a game reports `grade=…;speed=…` (`--game-port`) |
| `127.0.0.1:27101/udp` | UDP | this PC | Pedalator sends `power=…` (for a plugin that can listen) |
| `--udp-out` (27200) | UDP | this PC | JSON datagrams of the `udp` target |

The LAN ports exist only with `--remote`; change them with `--phone-port` and `--ca-port`.

## Formats

### OpenMW state file

`pedalator/state.txt` in the mod folder, one line, rewritten in place ~20×/s:

```
n=1234;move=0.570;turn=-1;look=0;atk=0;jump=0;draw=0;power=143;diff=40
```

`n` counter (the mod treats the file as stale if it stops changing for 1 s) · `move` 0–1 gas · `turn` −1 left / +1 right · `look` −1 up / +1 down · `atk`, `jump` held 0/1 · `draw` 1 while the button is held (the mod toggles the weapon on the press) · `power` watts · `diff` the difficulty (percent of the game's hills the trainer simulates); the mod shows a message when it changes.

The mod prints `PEDALATOR grade=<percent>` into `openmw.log` about four times a second.

### Dashboard API (`127.0.0.1:8765`)

| Request | |
|---|---|
| `GET /` | the page (`?lang=pl` or `en`) |
| `GET /state` | one JSON snapshot |
| `GET /events` | Server-Sent Events: a snapshot ten times a second |
| `POST /preset` `{"name":"easy\|medium\|real"}` | riding mode |
| `POST /gain` `{"gain":0.5..4}`, `POST /difficulty` `{"difficulty":0..1}` | fine-tune |
| `POST /mode` `{"mode":"game\|manual"}`, `POST /grade` `{"grade":-15..15}` | manual resistance |
| `POST /ftp` `{"ftp":50..600}` | power zones |

### Phone API (`https://…:8766`, every request needs `?t=<token>`)

| Request | |
|---|---|
| `GET /phone` | the page |
| `GET /phone/events` | SSE twice a second: `{"grade": 2.4, "difficulty": 0.4, "notice": ""}` |
| `GET /phone/ping` | `{"ok":true}` |
| `POST /phone/data` `{"hex":"…"}` | a raw Indoor Bike Data packet |
| `POST /phone/buttons` `{"pressed":[…],"raw":[…]}` | Click state |
| `POST /phone/status` `{"kind":"connected\|disconnected\|cp\|log",…}` | housekeeping |

## Why these choices

- **No framework, no build step** for the pages: two HTML files you can read and edit.
- **A state dict instead of classes:** the bridge is small and every part (a target, a server) only needs to read a few keys.
- **Keep-alive HTTPS, coalesced requests, short timeouts** on the phone page: a Wi-Fi laptop clogged when every packet opened a new TLS connection.
- **Fresh-or-stale everywhere:** the game side treats missing updates as "nothing pressed", so a crashed bridge never leaves a key held or the character running.
