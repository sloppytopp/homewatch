# homewatch
Home counter-surveillance **detector** for **Linux** (BlueZ + NetworkManager + `iw`). Detect-only: no jamming, no spoofing.
Run: `./homewatch.sh setup` once, then `./homewatch.sh run` -> http://127.0.0.1:8777

![dashboard with made-up demo data](https://raw.githubusercontent.com/sloppytopp/homewatch/main/docs/screenshot.png)

## What's new in 0.2
- Dark, muted, low-glare dashboard (no flashing alerts; every status is word + icon + color) with a **Night** switch (dim red on black)
- A plain-language banner ("All clear" / "Keeping an eye on something" / "Needs your attention") with a breathing dot and live scan ages, so you can see it is working
- **"This is mine"** on trackers: your own Tile/AirTag stops flagging and shows as yours
- Sister project: [homewatch-android](https://github.com/sloppytopp/homewatch-android) (public, with signed APKs on its Releases page) - same detection on a phone, with tap-to-find, room sweeps and survey exports

## Install
`pip install homewatch` (or from source below). System packages are still needed:
`sudo apt install ieee-data nmap iw network-manager bluez` (the vendor database from `ieee-data`/`nmap` is required for
camera/drone vendor detection - Homewatch warns at startup if it is missing), then
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
- Your Wi-Fi name, home position, tokens and the ntfy topic live in `~/.local/share/homewatch/config.json` (mode 600), never in the code.
