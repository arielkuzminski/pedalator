# Zwift Click

The Zwift Click is a pair of small Bluetooth controllers meant for gear shifting and in-game actions. Pedalator reads them through the same Web Bluetooth page as the trainer ([phone mode](phone-mode.md)) and turns the buttons into game actions.

> Pedalator is not affiliated with Zwift. This page describes what we observed on real controllers; the protocol is Zwift's and may change with firmware updates.

## Which Click do I have?

| | Click v1 | Click v2 |
|---|---|---|
| Buttons | two: **−** and **+** | two pucks: left (▲ ◀ ▶ ▼ and −) and right (Y Z A B and +) |
| In Pedalator | − / + steer left / right | every button, see below |
| Tested | not yet | yes, on a real controller |

Some Zwift controllers (the Ride v2, and reportedly the left puck of some Click v2 units) can be locked to Zwift's own app until they are unlocked there. On the author's controller both pucks worked as they were; if your Click does not show up, see [Troubleshooting](troubleshooting.md#zwift-click).

## Buttons in Pedalator

The phone page reports the **physical buttons** to the PC (`LEFT RIGHT UP DOWN A B Y Z PLUS MINUS`); each game target decides what they do.

**`keys` target** (OMSI and other keyboard games):

| Click v2 | Click v1 | Action |
|---|---|---|
| ◀ (left puck), Z | − | steer left |
| ▶ (left puck), A | + | steer right |
| ▼, B | – | brake |

**OpenMW target:**

| Click v2 | Action |
|---|---|
| ◀ / ▶ | turn left / right |
| ▲ / ▼ | look up / down |
| B | attack |
| A | jump |
| Y | draw / sheathe the weapon |
| Z | use (presses `E`) |
| − / + | difficulty: fewer / more of the game's hills on the trainer |

On a Click v1 the two buttons turn left / right (there are no other buttons to spare), so it has no difficulty buttons.

> **Difficulty buttons.** On a Click v2, **−** and **+** change how much of the game's hills the trainer simulates, by 10 percentage points per press (holding repeats). The dashboard, the phone page and, in OpenMW, a message in the game show the new value. **Planned:** the button mappings will become editable profiles ([roadmap, milestone 3](roadmap.md#3-profiles-import-and-export-of-a-games-configuration-remappable-keys-in-the-dashboard)).

## How the connection works

Useful if you want to support another controller or debug.

- The phone page asks the browser for a device that advertises Zwift's custom service — `00000001-19ca-4651-86e5-fa29dcdd09d1` (Click v1, Play) or `0xFC82` (Click v2, Ride) — or has manufacturer data of company `0x094A` (Zwift). The *name* is not a reliable filter.
- It then opens three characteristics of that service: **async** `00000002-…` (notifications), **sync-TX** `00000004-…` (indications), **sync-RX** `00000003-…` (write).
- It writes the six ASCII bytes `RideOn` to sync-RX. The controller starts to notify.
- Messages start with a one-byte type:

| Type | Meaning | Content |
|---|---|---|
| `0x37` | Click v1 buttons | protobuf: field 1 = `+`, field 2 = `−`; value 0 = pressed (a missing field counts as 0) |
| `0x23` | Click v2 / Ride buttons | protobuf field 1 = `ButtonMap` (varint); **a pressed button is a cleared bit** |
| `0x19` | battery | level in the 3rd byte |
| `0x15` | keep-alive | empty |
| `0x2A`, `0xFF …` | device information | ignored |

`ButtonMap` bits (v2): `LEFT 1 · UP 2 · RIGHT 4 · DOWN 8 · A 16 · B 32 · Y 64 · Z 256 · − 512 · + 8192` (the minus and plus on the left/right pucks; more bits exist for Ride). A frame with every bit set — `23 08 ff ff ff ff 0f` — means "nothing pressed". The decoder is in `pedalator/web/phone.html` (between the `<decoders>` markers) and is unit-tested in `tests/js/phone.test.js`.

## Credits

The overall shape of Zwift's Bluetooth protocol was worked out by the community; [BikeControl](https://github.com/OpenBikeControl/bikecontrol) was used as a reference. Pedalator contains none of its code, and every bit above that matters here was confirmed on a real controller.
