# N0RMA

_Formerly called Homewatch._

Home counter-surveillance **detector** for **Linux** (BlueZ + NetworkManager + `iw`). Detect-only: no jamming, no spoofing.
Run: `./n0rma.sh setup` once, then `./n0rma.sh run` -> http://127.0.0.1:8777

![dashboard with made-up demo data](https://raw.githubusercontent.com/sloppytopp/n0rma/main/docs/screenshot.png)

## What's new in 0.5
- **Smart tab** on the dashboard: nearby gadgets grouped by maker (Amazon, Google, Samsung, cameras, plugs) from their network and Bluetooth names, a privacy checklist (Amazon Sidewalk, Ring/Alexa accounts, microphones, router), and a link that opens the community **DeFlock** license-plate-camera map (`maps.deflock.org`) in your browser. `n0rma smart` prints the same checklist. Names are hints, not proof.
- **Physical inspection:** `n0rma inspect <room>` is a tick-off checklist (ceiling fittings, outlets, objects facing the bed, lens-glint and infrared checks, mirrors, router device list; bedroom/bathroom/rental extras and a car list). Most real finds are physical.
- **Sweep report:** `n0rma sweep-report -o report.txt` is a TSCM-style report: which areas you inspected, every item NOT checked, what was flagged, and the methods a computer cannot perform (non-linear junction detection, wideband RF, thermal imaging, wired/cellular checks). It never says a place is "clear", and it uses the same tamper-evident hash chain (`n0rma evidence --verify report.txt`).

## What's new in 0.4
- **Evidence report:** `n0rma evidence -o report.txt` writes a plain-text, tamper-evident report of everything flagged (30 days by default) for police or an advocate. Every log line is hash-chained to the one before it; check a saved file with `n0rma evidence --verify report.txt`. Send the final CHAIN END line to someone you trust right away. The Android app makes the same format, and each can verify the other's reports.
- **Device names:** the dashboard and `n0rma devices` show a name for each device (router DNS or mDNS), and you can set your own: `n0rma name <mac> Alex iPhone`.
- Dashboard tabs (Status / Nearby / Radar / History), "this is my network" and "I know this device" buttons, and fewer false alerts for virtual bridges and loopback addresses.
- Renamed from Homewatch: the command is `n0rma` (the old `homewatch` still works), the PyPI package is **`n0rma-sec`**, and existing data is kept.

## What was new in 0.2
- Dark, muted, low-glare dashboard (no flashing alerts; every status is word + icon + color) with a **Night** switch (dim red on black)
- A plain-language banner ("All clear" / "Keeping an eye on something" / "Needs your attention") with a breathing dot and live scan ages, so you can see it is working
- **"This is mine"** on trackers: your own Tile/AirTag stops flagging and shows as yours
- Sister project: [n0rma-android](https://github.com/sloppytopp/n0rma-android) (public, with signed APKs on its Releases page) - same detection on a phone, with tap-to-find, room sweeps and survey exports

## Install
`pip install n0rma-sec` (the command it installs is `n0rma`) (or from source below). System packages are still needed:
`sudo apt install ieee-data nmap iw network-manager bluez` (the vendor database from `ieee-data`/`nmap` is required for
camera/drone vendor detection - N0RMA warns at startup if it is missing), then
`python3 -m venv .venv --system-site-packages && .venv/bin/pip install bleak`.
Optional RF module: `sudo apt install rtl-sdr` + an RTL-SDR dongle (24 MHz-1.7 GHz only; not 2.4/5.8 GHz).

## Commands
| Command | What |
|---|---|
| `setup` | first-run walkthrough: your Wi-Fi, home position, which devices are yours |
| `run [--lan]` | all detectors + dashboard (type `b`+Enter to log a sensor beep) |
| `scan` | one-shot scan |
| `beep [--ago MIN]` / `report` | log sensor beeps / line them up against detections (with background baseline) |
| `devices` / `trust all\|<mac>` | LAN inventory; the first scan auto-trusts everything - **review it** |
| `find <BLE addr>` | hot/cold locator |
| `inspect <room> [--tick id ...]` | physical-inspection checklist for a room |
| `sweep-report [-o file]` | TSCM-style report (what was and was NOT checked + everything flagged) |
| `smart` | smart-device privacy checklist and the DeFlock map link |
| `home <lat> <lon>` | home position for the drone map (west longitude is negative) |
| `ntfy setup\|test\|on\|off` | phone alerts (generic text only, via ntfy.sh) |
| `selftest` | unit tests |

## Read this first
- **This is not a guarantee of safety.** A quiet dashboard means "nothing seen by these radios", not "nothing is there".
  Blind spots: drones without Remote ID, SD-card-only cameras, cellular/GPS trackers, anything on 2.4/5.8 GHz video.
- **Remote ID is unauthenticated.** Anyone can broadcast a fake one, so a red drone alert means a broadcast *claims* a
  drone. Position and operator location are whatever the sender says. Operator coordinates are shown live and are
  **never written to disk**; events are pruned after 30 days.
- **Do not interfere with a drone** (shooting at, jamming or spoofing one is a federal crime). Report it to law
  enforcement or the FAA.
- **The radar is a rough estimate.** Signal strength gives only a crude distance, badly distorted indoors, and no direction.
- **If you find something:** don't touch or move it, photograph it where it is, note the time, and contact local law
  enforcement. A tracker you don't own: Apple/Android show unknown-tracker alerts and can help identify it.
- **`--lan` is plain HTTP.** Anyone sniffing your Wi-Fi can see the private link/token. Use it only on a network you trust.
  Localhost mode only accepts `Host: 127.0.0.1/localhost` (blocks DNS rebinding) and state-changing requests need an
  `X-Homewatch` header.
- Your Wi-Fi name, home position, tokens and the ntfy topic live in `~/.local/share/n0rma/config.json` (mode 600), never in the code.
