# Troubleshooting

Start with the console: Pedalator prints what it sees, and the dashboard's **Debug** section shows the last trainer packet, the last gradient from the game, the trainer's last answer, and an event log.

## Bluetooth and the trainer

| Symptom | Cause / fix |
|---|---|
| `BLE 'central' role not supported on this adapter` | The PC's Bluetooth adapter is too old. Use [phone mode](phone-mode.md) (`--remote`) or a USB Bluetooth 5 adapter. Disable the old adapter in Device Manager afterwards. |
| `no FTMS trainer found` | Wake the trainer (spin the pedals), close other apps connected to it (Zwift, Companion, a head unit), move closer. Most trainers accept one connection. |
| Connects, power is always 0 | Pedal; some trainers send data only while the flywheel turns. |
| The trainer's resistance does not change | Check the dashboard's *Control Point response*: `op 0x11: ok` means accepted. A trainer that does not support simulation mode answers `not supported`. |
| `trainer error … disconnected` repeats | Interference or a weak link; the bridge reconnects every 5 s by itself. |

## Phone mode

| Symptom | Cause / fix |
|---|---|
| Bluefy: **"Oops… we cannot complete your request"**; the PC prints `TLS/connection failed … certificate unknown` | The certificate is installed but **not trusted**. iPhone: *Settings → General → About → Certificate Trust Settings → switch Pedalator local CA on.* |
| The page opens but says *No Web Bluetooth* | Safari has none: open it in **Bluefy** (iPhone) or Chrome. The page must be `https://`. |
| Nothing opens at all | Windows Firewall blocks Python on private networks, the phone is on another network, or the address printed is a virtual adapter's (VPN, WSL, Hyper-V): pass `--ip <your LAN address>`. |
| *PC: no connection* appears after some minutes on a laptop | Fixed in recent versions (the page now has timeouts, one in-flight data request and a probe). The page's log shows the exact error; open an issue with it. |
| Data stops when you switch apps on the phone | Phones suspend background pages. Keep the page in front, or put the Bluetooth on a laptop / USB adapter. |
| *WinError 10048* (address already in use) at start | Another Pedalator is running (maybe in the background). Stop it with `Ctrl+C`. |

## Zwift Click

| Symptom | Cause / fix |
|---|---|
| The device list is empty | Press a button to wake the Click, close Zwift Companion, then use *Show all Bluetooth devices* on the page and pick the Click by name (`Zwift Click`). |
| *no Zwift service (the controller is locked…)* | Some Zwift controllers hide their service until unlocked by Zwift's own app. Unlock it there once, then retry. |
| Connected but no buttons | Press a button and look at the page's log: `Click: 23 08 …` lines should appear. If they do not, reconnect; if they do but nothing happens in the game, open an issue with those lines. |
| Left puck dead on a Click v2 | See above (locked). |
| The PC does not find the Click (`no Zwift Click found…` in the console) | Press a button to wake it, close Zwift Companion and any phone page that has the Click connected (a Click accepts one connection), and keep it within a couple of metres of the PC's adapter. `--click off` disables the search. |

## Games

| Symptom | Cause / fix |
|---|---|
| **OpenMW:** the character does not move | Is the mod enabled (*Data Files → content* in the launcher)? Is Pedalator running with `--target openmw`? Set `DEBUG = true` in `scripts/pedalator/player.lua`: `openmw.log` then shows what the mod reads every two seconds. `cannot open pedalator/state.txt` means the data folder is not in `openmw.cfg`. |
| **OpenMW:** hills do not reach the trainer | Pedalator reads `openmw.log`; the dashboard shows *Last gradient from the game*. Pass `--openmw-log` if your log is elsewhere. |
| **OpenMW:** *use* does nothing | Pedalator presses `E`; bind *use* to it or pass `--openmw-use-key f\|space\|enter`. The game window must be in front. |
| **OMSI:** "the engine is off" | Start the engine / select D. The bicycle has its own `engine_on`; if you still see the message you are on another vehicle. |
| **OMSI:** the bicycle does not move | The key output only works while the game window is in front. Check *Game keys* on the dashboard. Collisions with terrain and vehicles must be off. |
| **OMSI:** wipers switch on when pedalling | You are using the `wasd` key set in a bus: use the default `--keyset numpad`. |
| Keys are pressed in the wrong window | Pedalator sends keys to whatever window is in front. Keep the game in front, and do not use `--keys` while typing elsewhere. |
| **Any game:** pedalling does nothing | `--keys` is required for the `keys` target; without it nothing is typed. |

## Collecting information for a bug report

- The console output from the start of the run, and the dashboard's *Event log*.
- Your trainer and Click models, Windows version, phone and browser if phone mode.
- For a controller or trainer problem: the *Raw packet* line (and, for the Click, the `Click: …` lines from the phone page).
