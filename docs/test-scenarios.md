# Test scenarios

Manual scenarios for what automated tests cannot reach: real Bluetooth, real games, a real browser.
Automated checks first: `python -m ruff check .`, `python -m pytest -q`, `node --test`.

Mark each scenario **PASS / FAIL** with a note. Start with part A (no hardware), then B (hardware).
Close any old `pedalator.exe` first: an old instance may still hold its port (8765 in older builds).

## A. No hardware (simulated rider)

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| A1 | Launcher opens idle | Run `pedalator`; open http://127.0.0.1:2137 | Start tab is shown, header chip "No ride", Ride tab says no ride is running |
| A2 | Autostart still works | `pedalator --simulate --target keys` | Dashboard opens on Ride, data flows, chip "Riding" |
| A3 | Start and stop (keys) | Start tab → pick a keyboard game → trainer *Simulated* → Start riding | Moves to Ride, power/cadence/speed change; Stop returns to Start, values reset to 0 |
| A4 | Switch game without restart | After A3 pick OpenMW or a UDP game → Start | Starts cleanly, no "port in use" error, no leftover values |
| A5 | Start twice | Double-click Start riding; press Start in a second browser tab | Only one session; the second gets a clear error |
| A6 | Stop idempotent | Press Stop twice quickly | No error, state idle |
| A7 | OpenMW mod missing | Pick OpenMW with the mod not installed | Setup box with steps; Start disabled with the reason shown |
| A8 | Mod install preview | Open "What exactly will change" | Shows the lines to be removed/added; nothing is written yet |
| A9 | Mod install | Click Install the mod (OpenMW closed) | Backup `openmw.cfg.*` created, CRLF kept, ✓ status, Start enabled |
| A10 | OpenMW ride | Start OpenMW, load a save, Start riding (simulated) | The character moves; Stop → the character stops (zero line written) |
| A11 | UDP game | Pick a UDP game, set address, Start; listen with the game's `listen.py` | Packets arrive; after Stop a zero packet arrives and the port is free |
| A12 | Keys safety | Keyboard game riding, then Stop | No key stays pressed |
| A13 | Crash is reported | Start UDP with an unreachable address format (`abc`) | Inline error, no session started |
| A14 | New-game wizard | Game tab → name, keys → Create | Files appear in the editor; game appears on Start |
| A15 | Test panel | Game tab during a ride | Gas bar, turn, look and last packet move with the simulated rider |
| A16 | Editor | Edit `README.md`, Save, reload | Change persists; saving invalid JSON in `<id>.json` is refused with a message |
| A17 | Controls greying | Idle: Controls lists all profiles; during a ride: other-target ones are greyed | As described |
| A18 | Import/export | Export a profile, delete it, import it back; import twice | Second import asks about replacing |
| A19 | Polish | Open with `?lang=pl` | Start, steps, errors and chip are translated |
| A20 | Narrow window | Resize to phone width | No horizontal scroll, buttons reachable |
| A21 | Security | `curl -X POST -H "Host: evil.com" …/session/stop`; POST with `text/plain` | Both refused |
| A22 | Restart persistence | Pick settings, reload page | Last game/trainer/Click choices remembered |

## B. Hardware

Needs a Bluetooth 5 adapter on the PC (not used by other apps), the trainer and a Zwift Click.
Unplug/disable the phone's connection to the trainer first (a trainer takes one connection per source).

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| B1 | Adapter detected | Start tab | "This PC's Bluetooth" enabled |
| B2 | Trainer over PC | Trainer: This PC, Click: None → Start | Trainer found, power/cadence real, chip "Riding" |
| B3 | Click over PC | Trainer: Simulated, Click: This PC | Click found; button presses show on Ride and act in the game |
| B4 | Trainer + Click on one adapter | Both: This PC | Both stay connected for 10 min of riding |
| B5 | Hybrid | Trainer: This PC, Click: Phone (and the reverse) | Each source read by the right device, no duplicates |
| B6 | Slope to trainer | OpenMW, ride up/down hill | Trainer resistance follows the game's slope; difficulty buttons change it |
| B7 | Clean Stop | Stop during a ride | Trainer and Click disconnect (their LED/pairing indicator drops); resistance released |
| B8 | Start again | Right after B7 start another game | Reconnects without restarting Pedalator or the devices |
| B9 | Device off | Switch the Click off mid-ride | Pedalator reconnects or shows a clear state, no crash |
| B10 | Trainer lost | Turn the trainer off mid-ride | Values go to 0, game stops moving, recovery after power on |
| B11 | Phone mode | Trainer: Phone; open the phone page, connect | Data flows; Stop closes the phone servers; Start works again |
| B12 | Long ride | 30 min with OpenMW | No drift in the clock, no memory growth, no dropped connection |
| B15 | Flow check | Riding on a keyboard game with the trainer, Ride tab → Flow check → Record 30 s while pedalling steadily | Every stage ✓ and the verdict "Smooth"; otherwise the verdict names the stage (Bluetooth, loop, key presses, Windows) |
| B14 | Signal strength | Start → Check signal strength with the Click awake; then ride | Both devices listed with dBm; the header shows dBm after connecting; a USB extension cable moves the value toward 0 |
| B13 | Game exit | Close OpenMW mid-ride | Pedalator keeps running; Stop still works |

## Reporting

For a FAIL note: scenario, what you saw, the console log (the terminal running `pedalator`), and
the session chip text. Open an issue with those or tell the assistant to fix it.
