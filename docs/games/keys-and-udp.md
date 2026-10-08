# Any other game: keys and UDP

Pedalator has two generic ways to drive a game that it has no special support for.

## The `keys` target — press keys

```bash
python -m pedalator --keys                      # numpad keys (OMSI's layout)
python -m pedalator --keys --keyset wasd        # W A S D
```

(`--target keys` is the default target; without `--keys` Pedalator does not type anything into your game.)

| What you do | Key (numpad set) | Key (wasd set) |
|---|---|---|
| pedal | **8** — held in pulses: the share of time it is down is your "gas" | **W** |
| brake (Click ▼ / B) | **2** | **S** |
| steer left (Click ◀ / Z) | **4** | **A** |
| steer right (Click ▶ / A) | **6** | **D** |

Keys are sent as hardware scan codes (`SendInput`) to the window in front — keep the game in front. Windows only for now.

Because a key is on or off, "gas" is encoded by switching it on and off 20 times a second (PWM). Games that treat a held key as a ramp (most do) simply feel analog. Games that read the *number of presses* will not like it — use the UDP target.

The gradient of the game's ground can come back to Pedalator through UDP — see below. Without it the trainer gets no hills; use the dashboard's **Manual** slider for resistance.

## The `udp` target — talk to a mod

For any game with a mod or script that can use UDP sockets.

```bash
python -m pedalator --target udp --udp-out 127.0.0.1:27200
```

**Pedalator → game.** One JSON object per datagram, about 20 per second, sent to `--udp-out`:

```json
{"n": 1234, "power": 143, "move": 0.57, "cadence": 88.0, "speed": 24.1,
 "turn": -1, "look": 0, "buttons": ["B", "LEFT"], "grade_in_use": 2.4}
```

| Field | Meaning |
|---|---|
| `n` | counter: stops increasing if Pedalator stops |
| `power` | rider power, watts (0 when the trainer's data is stale) |
| `move` | 0..1 "gas": 0 below 15 W, 1 at full throttle for the current [riding mode](../../README.md#riding-modes) |
| `cadence`, `speed` | rpm and km/h from the trainer |
| `turn` | −1 / 0 / 1: Zwift Click ◀ / ▶ |
| `look` | −1 / 0 / 1: Click ▲ / ▼ (down is +1) |
| `buttons` | physical Click buttons held: `LEFT RIGHT UP DOWN A B Y Z PLUS MINUS` |
| `grade_in_use` | the gradient the trainer is simulating now, % |

**Game → Pedalator.** The game's mod sends the gradient of the ground under the player to UDP **`127.0.0.1:27100`** (change with `--game-port`), as plain text:

```
grade=4.2;speed=18.5
```

`grade` is in percent (rise over run × 100, −15…+15 are used), `speed` is optional (km/h, shown on the dashboard). Send it a few times a second. If the game stops sending, the last gradient stays in effect and the dashboard shows "game: silent".

### A minimal listener (Python)

```python
import json, socket
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); rx.bind(("127.0.0.1", 27200))
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
while True:
    pkt = json.loads(rx.recv(2048))
    print(f"gas {pkt['move']:.2f}  turn {pkt['turn']}  buttons {pkt['buttons']}")
    tx.sendto(b"grade=3.0;speed=20", ("127.0.0.1", 27100))   # pretend the road climbs 3 %
```

Games whose scripting cannot open sockets (like OpenMW's Lua) need a different channel; see how [OpenMW](openmw.md) does it with a state file and the game's log.

Want a ready-made adapter for a game? See the [roadmap](../roadmap.md) and [Development](../development.md#adding-a-game).
