# Security

## What Pedalator exposes

| What | Where | Protection |
|---|---|---|
| The dashboard | `127.0.0.1:8765` | this PC only; it also rejects a foreign `Host` header (DNS rebinding) and any `POST` that is not `application/json`, so a web page you visit cannot change your keys or settings |
| The phone page and API (only with `--remote`) | `0.0.0.0:8766` over HTTPS | a secret token in the URL, and your local network |
| The certificate download (only with `--remote`) | `0.0.0.0:8767` over HTTP | it serves only the public certificate |
| Game channels | UDP on `127.0.0.1` | this PC only |

Pedalator has no accounts, no cloud and sends no telemetry. In `--remote` mode anyone on your local network who knows the URL (with its token) can send fake trainer data or button presses to your PC, which can press keys in the window in front. Use phone mode only on a network you trust, and do not share the URL.

## The certificate authority

Phone mode creates a **private certificate authority** on your PC (`ca.pem`, `ca.key`) and a server certificate for your PC's LAN address. You install the CA's public certificate (`ca.crt`) on your phone or laptop.

- Anyone who gets `ca.key` can issue certificates that **your phone will trust**. Keep the folder (`%LOCALAPPDATA%\Pedalator` on Windows, or `--data-dir`) private. It is not inside the repository and `.gitignore` excludes `*.key`, `*.pem`, `*.crt` and `token.txt` anyway.
- The CA is limited to signing certificates (`pathlen=0`); it is valid for 10 years and the server certificate for one year.
- When you stop using phone mode, **remove the profile from the phone** (iPhone: *Settings → General → VPN & Device Management*; Windows: certificate manager) and delete the data folder.

## Key output

With `--keys` (and OpenMW's *use* key) Pedalator sends keystrokes to **whichever window is in front**. Keep the game in front, and do not type elsewhere while it runs. Pedalator releases every key it holds when it stops or when updates stop arriving.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's *Report a vulnerability* (Security tab) on this repository, or contact the maintainer through the email on their GitHub profile. We will answer as soon as we can.
