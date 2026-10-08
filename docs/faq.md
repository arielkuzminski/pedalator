# FAQ

**Which trainers work?** Anything that speaks Bluetooth FTMS (Fitness Machine Service) and accepts *Set Indoor Bike Simulation Parameters* to simulate grade. That covers most smart trainers sold in the last years. Tested: Van Rysel D500. ANT+-only trainers are not supported yet ([roadmap](roadmap.md)).

**Do I need Zwift?** No. Pedalator talks to the trainer directly. Only close Zwift (and its Companion app) while you use Pedalator, because most trainers allow one connection.

**Do I need the Zwift Click?** No. It adds steering, looking and actions. Without it you can steer with the keyboard or mouse while pedalling.

**Why would my PC not talk to a trainer?** Reading a trainer needs a Bluetooth adapter that can be a BLE *central*. Older adapters cannot. Use [phone mode](phone-mode.md) or a cheap USB Bluetooth 5 adapter.

**Is it a cheat / can I get banned?** Pedalator sends ordinary key presses (or a file/UDP message to a mod you chose). Do not use it in online games whose rules forbid input automation, and do not use `--keys` in games with anti-cheat. It is meant for single-player games and mods.

**Does it work with Zwift's own game, GTA V, Skyrim…?** Not out of the box. The `keys` and `udp` targets make a start possible for most games; see the [roadmap](roadmap.md) for ideas and how to add one.

**Can it run on Linux or macOS?** The bridge, dashboard, OpenMW file/log channel and phone mode are plain Python and should run, but key output uses the Windows API today, and nobody has tested it. Reports and patches welcome.

**Is the certificate safe?** It is a private certificate authority made on *your* PC, trusted only by the devices where *you* installed it, and used only for the page Pedalator serves on your LAN. Keep its private key (`ca.key`) to yourself and remove the profile when you are done. Details: [SECURITY.md](../SECURITY.md).

**Is the data sent anywhere?** No. Pedalator talks only to your devices and to localhost; there is no cloud, account or telemetry.

**Why do I see "game: no signal"?** The game did not report the gradient of the ground. That is normal in `--simulate`, and for games with no plugin. The trainer then keeps its last resistance; use the **Manual** slider to set it by hand.

**How hard is "Easy"?** Easy gives full throttle at ~125 W and lets you feel 40 % of the hills. Medium: ~180 W and 70 %. Realistic: 250 W and 100 %. Fine-tune on the dashboard.

**Can I change the language?** The dashboard and phone page follow the browser's language (English, Polish) — add `?lang=pl` or `?lang=en` to the address.

**Where is my data stored?** Certificates and the phone token: `%LOCALAPPDATA%\Pedalator` on Windows (`--data-dir` to change). Nothing else.
