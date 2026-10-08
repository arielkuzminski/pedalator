# Adding a new game with the wizard

```
pedalator new-game
```

The wizard asks for the game's name and how Pedalator can reach it, then writes a folder with everything to try it and saves a [profile](profiles.md) so `pedalator --profile <id>` works at once. It can also run without questions:

```
pedalator new-game --name "Cool Bikes" --how keys --key throttle=ArrowUp --out coolbikes
pedalator new-game --name "Space Cycle" --how udp --slope
```

| You answer | What you get |
|---|---|
| **keys**: the game reads the keyboard | a profile with your keys (`--key throttle=… brake=… left=… right=…`, default WASD) and a `README.md` with the steps. No code. |
| **udp**: the game has a mod or script that can use UDP | the same, plus `listen.py` (shows what Pedalator sends, to check that pedalling arrives), `mod_sketch.lua` (a starting point for the mod), and with `--slope` the line that sends the ground's slope back so the trainer follows the hills |

A game whose scripts cannot open sockets (like OpenMW) needs its own target: see [Development → Adding a game](development.md#adding-a-game).

Key names are the ones a browser gives: `KeyW`, `ArrowUp`, `Numpad8`, `Space`… You can change any of them later on the dashboard's **Controls** tab. The wizard never overwrites a profile, built-in or yours, unless you pass `--overwrite`.

Made it work for a game people play? Share the exported profile (`pedalator profile export <id>`) in a pull request or an issue.
