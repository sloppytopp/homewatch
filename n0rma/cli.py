import argparse
import sys
import threading
import time

from .core import DOMAINS, DB, Engine, load_config, save_config, new_token, clean

ICON = {"ok": "OK   ", "watch": "WATCH", "alert": "ALERT", "off": "off  "}


def cmd_run(a):
    from . import det_ble, det_host, det_lan, det_sdr, det_wifi, web
    eng = Engine()
    det_ble.BLEDetector(eng).start()
    if not a.no_wifi:
        det_wifi.WifiDetector(eng).start()
        det_lan.LanDetector(eng).start()
    det_host.HostDetector(eng, own_port=a.port).start()
    det_sdr.SdrDetector(eng).start()
    from . import oui
    if oui.table_size() == 0:
        print("WARNING: no MAC vendor database found - camera/drone vendor detection is OFF.\n"
              "         Install it:  sudo apt install ieee-data nmap", flush=True)
    eng.db.prune()
    cfg = load_config()
    if not cfg.get("my_ssids"):  # learn which Wi-Fi is yours (first run) - never hardcoded
        import subprocess
        out = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], capture_output=True, text=True).stdout
        mine = sorted({l.split(":", 1)[1] for l in out.splitlines() if l.startswith("yes:") and l.split(":", 1)[1]})
        if mine:
            cfg["my_ssids"] = mine
            save_config(cfg)
            print(f"Learned your Wi-Fi name(s): {', '.join(mine)}  (edit my_ssids in {__import__('n0rma.core', fromlist=['x']).CONFIG_PATH})")
    token = None
    if a.lan:
        token = cfg.setdefault("dashboard_key", new_token())
        save_config(cfg)
    web.serve(eng, "0.0.0.0" if a.lan else "127.0.0.1", a.port, token)
    print(f"N0RMA running. Dashboard: http://127.0.0.1:{a.port}")
    if a.lan:
        import subprocess
        ip = subprocess.run("hostname -I", shell=True, capture_output=True, text=True).stdout.split()[0]
        print(f"Phone (same Wi-Fi): http://{ip}:{a.port}/?k={token}   <- keep this link private")
    if a.lan:
        print("NOTE: --lan is plain HTTP. Anyone sniffing your Wi-Fi could see the link/token. Use only on a network you trust.")
    print(f"Phone alerts: {'ON' if cfg.get('ntfy', {}).get('enabled') else 'off (see: n0rma ntfy setup)'}\n"
          "Type  b + Enter  when the sensor beeps.  Ctrl-C to stop.", flush=True)

    def keys():
        for line in sys.stdin:
            if line.strip().lower() in ("b", "beep"):
                eng.beep("keyboard")
                print("  -> beep logged", flush=True)
    if sys.stdin.isatty():
        threading.Thread(target=keys, daemon=True).start()
    try:
        while True:
            time.sleep(60)
            line = " | ".join(f"{d}:{eng.state[d]['level']}" for d in DOMAINS)
            print(f"[{time.strftime('%H:%M')}] {line}", flush=True)
    except KeyboardInterrupt:
        eng.stop.set()


def cmd_beep(a):
    db = DB()
    ts = time.time() - a.ago * 60
    db.exec("INSERT INTO beeps(ts,note) VALUES(?,?)", (ts, " ".join(a.note)))
    print(f"Beep logged at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}")


def cmd_report(a):
    db = DB()
    since = time.time() - a.hours * 3600
    beeps = db.query("SELECT * FROM beeps WHERE ts>? ORDER BY ts", (since,))
    if not beeps:
        print("No beeps logged in that window. Log them with: n0rma beep   (or 'b' in `run`)")
    hits = 0
    for b in beeps:
        near = db.query("SELECT * FROM events WHERE ts BETWEEN ? AND ? AND level IN ('alert','watch') "
                        "AND kind!='beep' ORDER BY ts", (b["ts"] - a.window * 60, b["ts"] + a.window * 60))
        stamp = time.strftime("%a %m-%d %H:%M:%S", time.localtime(b["ts"]))
        print(f"\nBEEP {stamp}  {b['note'] or ''}")
        if near:
            hits += 1
            for e in near:
                print(f"   {time.strftime('%H:%M:%S', time.localtime(e['ts']))} {e['level']:5} {e['domain']:7} {e['msg']}")
        else:
            print(f"   nothing flagged within +/-{a.window} min")
    if beeps:
        print(f"\n== {hits}/{len(beeps)} beeps had a detection nearby. ==")
        hrs = sorted(time.localtime(b['ts']).tm_hour for b in beeps)
        print("Beep hours:", ", ".join(f"{h:02d}:xx" for h in hrs))
        if hits == 0:
            print("No drone, tracker, camera or RF event lines up with any beep -> sensor/animal/environment is the likely cause.")
    if beeps:
        span = max(1.0, (time.time() - min(since, beeps[0]["ts"])) / 60)
        wins = max(1, int(span / (2 * a.window)))
        busy = db.query("SELECT COUNT(DISTINCT CAST(ts/? AS INT)) n FROM events WHERE level IN ('alert','watch') "
                        "AND kind!='beep' AND ts>?", (a.window * 120, since))[0]["n"]
        print(f"Baseline: detections were present in {busy} of ~{wins} {2*a.window:.0f}-minute windows overall. "
              f"If that is close to {hits}/{len(beeps)}, the detections are background and prove nothing about the beeps.")
    allev = db.query("SELECT level,COUNT(*) n FROM events WHERE ts>? GROUP BY level", (since,))
    print("Events in window:", {e["level"]: e["n"] for e in allev})


def cmd_devices(a):
    rows = DB().query("SELECT * FROM devices ORDER BY trusted, klass DESC, ip")
    for d in rows:
        t = "trusted " if d["trusted"] else "UNREVIEWED"
        name = clean(d.get("label") or d.get("hostname") or "")
        print(f"{t} {d['ip']:15} {d['mac']} {name[:22]:22} {d['klass']:8} {d['vendor'][:28]:28} ports:{d['ports'] or '-'}")
    print("\nMark yours as trusted:  n0rma trust all   |   n0rma trust <mac>   |   give one a name:  n0rma name <mac> Missy iPhone")


def cmd_trust(a):
    db = DB()
    if a.mac == "all":
        db.exec("UPDATE devices SET trusted=1")
    else:
        db.exec("UPDATE devices SET trusted=1 WHERE mac=?", (a.mac.lower(),))
    print("ok")


def cmd_name(a):
    label = clean(" ".join(a.label), 40)
    DB().exec("UPDATE devices SET label=? WHERE mac=?", (label, a.mac.lower()))
    print("ok" if label else "name cleared")


def cmd_evidence(a):
    from . import evidence
    if a.verify:
        ok = evidence.verify(open(a.verify, encoding="utf-8").read())
        print("OK: the report matches its hash chain." if ok else "FAILED: the report was changed, or is not a N0RMA evidence report.")
        sys.exit(0 if ok else 1)
    rows = DB().query("SELECT ts,domain,level,msg FROM events WHERE ts>? ORDER BY ts", (time.time() - a.days * 86400,))
    text = evidence.build([dict(r, msg=clean(r["msg"], 400)) for r in rows])
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
        print(f"Wrote {a.out}. Send the CHAIN END line at the bottom to yourself or an advocate right away.")
    else:
        print(text, end="")


def cmd_ignore(a):
    db = DB()
    cur = set(db.kv_get("ble_ignore", []))
    cur.add(a.addr.upper())
    db.kv_set("ble_ignore", sorted(cur))
    print("Ignoring BLE device", a.addr, "(note: AirTags rotate addresses; this only mutes this one address)")


def cmd_find(a):
    import asyncio
    from bleak import BleakScanner
    target = a.addr.upper()
    print(f"Hot/cold finder for {target}. Walk around; stronger bar = closer. Ctrl-C to stop.")

    def cb(dev, adv):
        if dev.address.upper() == target:
            n = max(0, min(40, int((adv.rssi + 100) * 40 / 60)))
            print(f"{adv.rssi:4} dBm |{'#' * n}", flush=True)

    async def go():
        async with BleakScanner(cb):
            while True:
                await asyncio.sleep(1)
    try:
        asyncio.run(go())
    except KeyboardInterrupt:
        pass


def cmd_home(a):
    cfg = load_config()
    if a.lat is not None:
        cfg["home"] = {"lat": a.lat, "lon": a.lon}
        save_config(cfg)
    print("Home location:", cfg.get("home") or "not set",
          "\nTip: for exact position, long-press your house in Google/Apple Maps and copy the two numbers, then:"
          "\n  n0rma home <lat> <lon>")


def cmd_ntfy(a):
    import urllib.request
    cfg = load_config()
    n = cfg.setdefault("ntfy", {})
    if a.action == "setup":
        n["topic"] = n.get("topic") or "n0rma-" + new_token()
        n.setdefault("enabled", False)
        save_config(cfg)
        print(f"Topic created: {n['topic']}\n"
              "1. Install the free 'ntfy' app (iOS App Store / Android Play Store).\n"
              f"2. In the app tap + and subscribe to topic:  {n['topic']}   (server: ntfy.sh)\n"
              "3. Then run:  n0rma ntfy test   (sends one test message)\n"
              "4. Then run:  n0rma ntfy on\n"
              "Note: the topic name is the only 'password', so keep it private. Pushes are generic - never MACs or coordinates.")
        return
    if not n.get("topic"):
        sys.exit("Run first:  n0rma ntfy setup")
    if a.action in ("on", "off"):
        n["enabled"] = a.action == "on"
        save_config(cfg)
        print("Phone alerts", "ON" if n["enabled"] else "OFF")
    elif a.action == "test":
        req = urllib.request.Request(f"https://ntfy.sh/{n['topic']}", data=b"N0RMA test: phone alerts work.",
                                     headers={"Title": "N0RMA"}, method="POST")
        urllib.request.urlopen(req, timeout=10).read()
        print("Test message sent. Check your phone.")


def cmd_setup(a):
    """First-run walkthrough: your Wi-Fi, home position, and which devices on the network are yours."""
    import socket
    import subprocess
    from . import det_lan
    cfg = load_config()
    print("N0RMA setup - takes about a minute.\n")
    out = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], capture_output=True, text=True).stdout
    mine = sorted({l.split(":", 1)[1] for l in out.splitlines() if l.startswith("yes:") and l.split(":", 1)[1]})
    if mine:
        ok = input(f"1. Is your home Wi-Fi '{', '.join(mine)}'? [Y/n] ").strip().lower() != "n"
        if ok:
            cfg["my_ssids"] = mine
    if "home" not in cfg:
        print("\n2. Home position (optional, for the drone map). In Google/Apple Maps long-press your house and copy the")
        print("   two numbers. West longitude is negative (e.g. 40.7128 -74.0060). Press Enter to skip.")
        raw = input("   lat lon: ").split()
        if len(raw) == 2:
            try:
                cfg["home"] = {"lat": float(raw[0]), "lon": float(raw[1])}
            except ValueError:
                print("   (couldn't read that - skipped)")
    save_config(cfg)
    print("\n3. Scanning your network for devices...")
    eng = Engine(quiet=True)
    det_lan.LanDetector(eng).scan()
    pend = eng.db.query("SELECT * FROM devices WHERE trusted=0 ORDER BY ip")
    if not pend:
        print("   Nothing to review.")
    for d in pend:
        try:
            name = socket.gethostbyaddr(d["ip"])[0]
        except OSError:
            name = ""
        what = f"{d['ip']:15} {d['mac']}  {d['vendor']}  {name}".rstrip()
        ans = input(f"   Is this yours?  {what}  [y/N/a=all remaining] ").strip().lower()
        if ans == "a":
            eng.db.exec("UPDATE devices SET trusted=1 WHERE trusted=0")
            break
        if ans == "y":
            eng.db.exec("UPDATE devices SET trusted=1 WHERE mac=?", (d["mac"],))
    left = eng.db.query("SELECT COUNT(*) n FROM devices WHERE trusted=0")[0]["n"]
    print(f"\nDone. {left} device(s) left unreviewed - they will show amber until you identify them "
          "(your router's client list can help).\nStart with:  n0rma run")


def cmd_rebaseline(a):
    """Accept everything currently listening / plugged in as normal (after you have checked it)."""
    from . import det_host
    db = DB()
    p, u = det_host.listening(), det_host.usb_devices()
    db.kv_set("host_ports", sorted(p))
    db.kv_set("host_usb", sorted(u))
    print(f"Accepted {len(p)} listening ports and {len(u)} USB devices as normal.")


def cmd_forget_network(a):
    """Moved house / changed router: forget the saved home network and device list, then re-learn."""
    db = DB()
    db.exec("DELETE FROM devices")
    db.kv_set("lan_baseline", False)
    db.exec("DELETE FROM kv WHERE k='lan_subnet'")
    print("Forgot the home network. The next `n0rma setup` / `run` learns the current one.")


def cmd_scan(a):
    """One-shot scan of everything, print answers, exit."""
    from . import det_ble, det_host, det_lan, det_wifi
    eng = Engine(quiet=True)
    ble = det_ble.BLEDetector(eng)
    ble.start()
    print("Scanning ~25s (Bluetooth + Wi-Fi + LAN + this computer)...", flush=True)
    wd = det_wifi.WifiDetector(eng)
    try:
        wd.evaluate(wd.scan())
    except Exception as e:
        eng.status("drone", "watch", f"Wi-Fi: {e}", "wifi")
    try:
        det_lan.LanDetector(eng).scan()
    except Exception as e:
        eng.status("network", "watch", f"LAN: {e}", "lan")
    try:
        det_host.HostDetector(eng).check()
    except Exception as e:
        eng.status("host", "watch", str(e))
    from . import det_sdr
    det_sdr.SdrDetector(eng).start()
    time.sleep(20)
    ble._evaluate()
    eng.stop.set()
    for d, t in DOMAINS.items():
        s = eng.state[d]
        print(f"{ICON[s['level']]}  {t}\n         {s['msg']}")


def cmd_selftest(a):
    import os
    import unittest
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isdir(os.path.join(root, "tests")):
        sys.exit("selftest needs a source checkout (tests/ not found).")
    os.chdir(root)
    sys.exit(unittest.main(module=None, argv=["x", "discover", "-s", "tests", "-t", "."]))


def legacy():
    """Old `homewatch` command: still works, but says it was renamed."""
    print("note: homewatch is now called n0rma - use `n0rma` from now on.", file=sys.stderr)
    main()


def main():
    p = argparse.ArgumentParser(prog="n0rma", description="Home counter-surveillance detector")
    sp = p.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run", help="run all detectors + dashboard")
    r.add_argument("--lan", action="store_true", help="serve dashboard to phones on your LAN")
    r.add_argument("--port", type=int, default=8777)
    r.add_argument("--no-wifi", action="store_true")
    r.set_defaults(f=cmd_run)
    b = sp.add_parser("beep", help="log that the sensor just beeped")
    b.add_argument("--ago", type=float, default=0, help="minutes ago")
    b.add_argument("note", nargs="*")
    b.set_defaults(f=cmd_beep)
    rp = sp.add_parser("report", help="line up beeps against detections")
    rp.add_argument("--hours", type=float, default=72)
    rp.add_argument("--window", type=float, default=5, help="minutes either side of a beep")
    rp.set_defaults(f=cmd_report)
    ev = sp.add_parser("evidence", help="write a tamper-evident report of everything flagged (for police or an advocate)")
    ev.add_argument("--days", type=float, default=30)
    ev.add_argument("-o", "--out", help="write to a file instead of the screen")
    ev.add_argument("--verify", metavar="FILE", help="check a saved report against its hash chain")
    ev.set_defaults(f=cmd_evidence)
    sp.add_parser("devices", help="LAN inventory").set_defaults(f=cmd_devices)
    t = sp.add_parser("trust", help="mark LAN device(s) as yours")
    t.add_argument("mac")
    t.set_defaults(f=cmd_trust)
    nm = sp.add_parser("name", help="give a LAN device a name you will recognise")
    nm.add_argument("mac")
    nm.add_argument("label", nargs="*", help="empty clears the name")
    nm.set_defaults(f=cmd_name)
    i = sp.add_parser("ignore", help="mute a BLE address (your own tracker)")
    i.add_argument("addr")
    i.set_defaults(f=cmd_ignore)
    f = sp.add_parser("find", help="hot/cold locator for a BLE device")
    f.add_argument("addr")
    f.set_defaults(f=cmd_find)
    h = sp.add_parser("home", help="show/set home lat lon for the drone map")
    h.add_argument("lat", type=float, nargs="?")
    h.add_argument("lon", type=float, nargs="?")
    h.set_defaults(f=cmd_home)
    nt = sp.add_parser("ntfy", help="phone alerts via ntfy.sh")
    nt.add_argument("action", choices=["setup", "test", "on", "off"])
    nt.set_defaults(f=cmd_ntfy)
    sp.add_parser("rebaseline", help="accept current listening ports + USB devices as normal").set_defaults(f=cmd_rebaseline)
    sp.add_parser("forget-network", help="forget the saved home network and re-learn").set_defaults(f=cmd_forget_network)
    sp.add_parser("setup", help="first-run walkthrough").set_defaults(f=cmd_setup)
    sp.add_parser("scan", help="one-shot scan, print answers").set_defaults(f=cmd_scan)
    sp.add_parser("selftest").set_defaults(f=cmd_selftest)
    a = p.parse_args()
    a.f(a)
