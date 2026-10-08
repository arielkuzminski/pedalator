# openOMSI (and OMSI 2): a bicycle and the buses

[openOMSI](https://github.com/openOMSI-Project/openOMSI) is an open-source engine that plays OMSI 2's maps and vehicles. With Pedalator you can ride **any vehicle** on your trainer, and ride a real **bicycle** if you own the HafenCity add-on.

Needs: openOMSI (tested 0.1.6) with an original OMSI 2 install, and for the bicycle the paid **OMSI 2 add-on HafenCity** (it ships the bicycle model; Pedalator cannot include it).

## 1. Install the plugin

```bash
python -m pedalator install openomsi --game-dir "C:\path\to\openOMSI"
```

This copies `Plugins/pedalator/main.lua` into your openOMSI folder. The plugin measures the slope under the vehicle and sends it to Pedalator (UDP `127.0.0.1:27100`), which sets the trainer's resistance. It also shows the grade on screen (set `SHOW_GRADE = false` in the file to hide it).

## 2. Build the bicycle (optional)

```bash
python -m pedalator build-bike \
    --hafencity "C:\...\OMSI 2\Vehicles\HC_Fahrrad" \
    --game-dir  "C:\path\to\openOMSI"
```

`--hafencity` is the `Vehicles/HC_Fahrrad` folder of **your** copy of the add-on. Pedalator copies its model, sounds and textures into `<openOMSI>/Mods/Pedalator` and writes three new files next to them:

| File | What it is |
|---|---|
| `fahrrad_pedalator.osc` | the add-on's AI script with the AI's random top speed removed and a drive block that turns *your power* into wheel torque and adds air and rolling drag |
| `fahrrad_pedalator_constfile.txt` / `_varlist.txt` | the add-on's lists plus our constants and variables |
| `fahrrad_pedalator.bus` | the vehicle: 100 kg physics, a steering lock that suits a bike, a rider camera |

Then start the **openOMSI launcher** once: it sorts the mod into place. Pick **Pedalator Bike** as the vehicle. In the game, switch off *collisions with terrain and vehicles* (Esc → Options) — the bicycle is an AI-type vehicle and gets stuck on kerbs otherwise.

If the build says *"expected 1 match(es), found 0"*, your HafenCity files differ from the version the builder knows; open an issue with the first lines of your `fahrrad_1.bus`.

## 3. Ride

```bash
python -m pedalator --keys                  # PC talks to the trainer
python -m pedalator --keys --remote         # phone or laptop talks to the trainer
```

`--keys` makes Pedalator press the game's driving keys in the window that is in front, so keep the game in front. OMSI's own keys are used by default (`--keyset numpad`): **numpad 8** throttle, **numpad 2** brake, **numpad 4 / 6** steering. (`W` is the wipers in a bus, which is why the default is not WASD.) With Zwift Click: ◀ / Z = left, ▶ / A = right, B or ▼ = brake.

### Riding a bus

Works too: pedalling is the throttle pedal. Start the engine, select *D*, release the parking brake as usual. A bus is not scaled to your effort the way the bicycle is, so it feels very easy; lower the *power gain* on the dashboard.

## How the bicycle's physics work

openOMSI gives every vehicle at least **500 kg**, but a rider with a bike is about 90 kg — on a climb that would be five times too hard. The bicycle's script therefore multiplies every force (drive, drag, rolling, brake) by `k_mass = 5.5`, so acceleration and hills behave like a ~90 kg bike. The constants are in `fahrrad_pedalator_constfile.txt`:

| Constant | Meaning |
|---|---|
| `pmax` | watts that mean full throttle (the key's duty cycle is scaled to it) |
| `k_mass` | the mass compensation (500 kg ÷ ~90 kg) |
| `M_max` | maximum wheel torque, N·m (before `k_mass`) |
| `drag`, `roll_real` | air resistance coefficient and rolling resistance of a real bike |
| `brake_force`, `v_limit` | brake strength and a safety speed limit (km/h) |

## Optional: exact watts instead of a key

A key press can only say "this much gas". If you build openOMSI from source with the small patch in [`pedalator/data/openomsi/engine-patch/`](../../pedalator/data/openomsi/engine-patch/omsi-receive.patch) (adds `omsi.receive(port)` to its Lua plugins), the plugin passes the rider's real power to the bike's script. This is untested because it needs a compiler toolchain; contributions welcome.
