# Phone mode (or a laptop): when your PC cannot talk to the trainer

Reading a trainer needs a Bluetooth adapter that can act as a BLE *central*. Plenty of desktop PCs have older adapters that cannot — Windows then reports *"BLE 'central' role not supported on this adapter"*. In **phone mode** a phone or a laptop does the Bluetooth part in its browser (Web Bluetooth) and sends the data to the PC over your Wi-Fi/LAN.

The cheaper permanent fix is a USB Bluetooth 5.0 adapter (a few euros). Then you do not need any of this.

```
trainer, Zwift Click  ──Bluetooth──▶  phone / laptop browser  ──HTTPS over your LAN──▶  PC (Pedalator)  ──▶  game
                                                              ◀──────── the game's hills ────────────────
```

## What you need

| Device | Browser | Notes |
|---|---|---|
| **iPhone / iPad** | **Bluefy** (App Store) | Safari has no Web Bluetooth. Tested on iOS 18. |
| **Windows / Mac / Linux laptop** | Chrome or Edge | Tested on Windows. |
| **Android** | Chrome | Not tested, should work. |

The phone and the PC must be on the **same network**.

## Steps

### 1. Start Pedalator on the PC

```bash
python -m pedalator --remote            # add --target openmw, --keys ... as usual
```

It creates a private certificate authority, a certificate for this PC's address, and a secret token, then prints two addresses:

```
1) browser (once): http://10.0.0.5:8767/  -> install and trust the certificate
2) Bluefy (iPhone) or Chrome: https://10.0.0.5:8766/phone?t=AbCdEf12
```

Allow Python through the Windows Firewall for **private** networks when asked. If the PC's address is not the one printed (VPNs, virtual adapters), pass `--ip 192.168.x.y`.

### 2. Install the certificate on the phone — once

Web Bluetooth only works on secure (HTTPS) pages, so the phone must trust Pedalator's own certificate authority.

**iPhone (Safari, then Settings):**
1. In **Safari** open the first address (`http://…:8767/`), tap *Download the certificate*, allow.
2. *Settings → Profile Downloaded → Install.*
3. *Settings → General → About → Certificate Trust Settings →* switch **Pedalator local CA** on. *(Without this step Bluefy shows "Oops…" and the PC logs `certificate unknown`.)*

**Windows laptop (Chrome/Edge):** open the first address, download `ca.crt`, double-click it → *Install Certificate → Current User → Place all certificates in the following store → Trusted Root Certification Authorities*.

**Android:** download `ca.crt`, then *Settings → Security → Encryption & credentials → Install a certificate → CA certificate*.

Remove the certificate again whenever you like (iPhone: *Settings → General → VPN & Device Management*). The private key stays on your PC in the folder shown by `--data-dir` (see [Security](../SECURITY.md)).

### 3. Open the page and connect

Open the second address (`https://…:8766/phone?t=…`) in **Bluefy** (iPhone) or Chrome. Tap **Connect trainer** and pick it from the list; then **Connect Zwift Click controls** and pick the Click (wake it with a button press first).

The page shows power, cadence, grade and the pressed buttons. The three lights at the top show the trainer, the PC and the controls.

### 4. Ride

Keep the page open and **in front** with the screen on — phones suspend background pages, which stops the data. If you want to film yourself with the phone, use a second device for the Bluetooth, or a [USB adapter on the PC](#why-not-just-use-the-phone-camera).

## Notes

- The URL (token) stays the same after restarts. If the PC's address changes, restart Pedalator: it makes a new certificate, and the CA on the phone stays valid.
- Language follows the browser (English, Polish). Add `&lang=pl` or `&lang=en` to force one.
- Close the trainer's other apps (Zwift Companion, etc.) before connecting.

## Why not just use the phone camera?

On iOS a page in the background is suspended after a short while, so the Bluetooth data stops reaching the PC when you switch to the Camera app. Put the Bluetooth on another device (a laptop with Chrome works well) or on a USB Bluetooth adapter in the PC.

## If it does not connect

See [Troubleshooting](troubleshooting.md#phone-mode). The page has a log at the bottom and the PC prints what it sees (`phone page requested…`, `TLS/connection failed…`).
