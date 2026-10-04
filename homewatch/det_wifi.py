"""Wi-Fi air scan: Remote ID beacons, drone/camera-looking access points, new APs."""
import re
import subprocess
import time

from . import oui, remoteid

DRONE_SSID = re.compile(r"^(DJI|TELLO|MAVIC|PHANTOM|SPARK|MAVIC|PARROT|ANAFI|BEBOP|SKYDIO|AUTEL|HOLYSTONE|"
                        r"POTENSIC|HUBSAN|FIMI|YUNEEC|RYZE|SYMA|WLT|RC-?UFO|DRONE|FPV)[-_ ]?", re.I)
CAMERA_SSID = re.compile(r"(\bIPC\b|IPCAM|IP-?CAM|HDCAM|HD-?WIFI|MINI.?CAM|SPY|^A9[-_]|^MV[-_]|V380|YOOSEE|"
                         r"ICSEE|EYE4|CLOUDEDGE|^YI-|^WYZE|^ARLO|REOLINK|HIKVISION|DAHUA|^TAPO_?CAM|"
                         r"^CAM[-_]|^CAMERA|^P2P|^GOOLINK|^HDWIFI|^BC[-_]|^IPC-|^SHD[-_]|^NVR)", re.I)


def parse_iw(text):
    """Parse `iw dev X scan dump` output into a list of BSS dicts."""
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^BSS ([0-9a-f:]{17})", line)
        if m:
            cur = {"bssid": m.group(1).lower(), "ssid": "", "signal": -100.0, "freq": 0, "rid_ies": [],
                   "seen_ms": None}
            out.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("signal:"):
            cur["signal"] = float(s.split()[1])
        elif s.startswith("freq:"):
            cur["freq"] = int(float(s.split()[1]))
        elif s.startswith("SSID:"):
            cur["ssid"] = s[5:].strip()
        elif s.startswith("last seen:"):
            m2 = re.search(r"(\d+) ms", s)
            cur["seen_ms"] = int(m2.group(1)) if m2 else None
        elif s.lower().startswith("vendor specific: oui fa:0b:bc"):
            cur["rid_ies"].append(s.split("data:")[1].strip())
    return out


def iface():
    try:
        out = subprocess.run(["iw", "dev"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"Interface (\S+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


class WifiDetector:
    def __init__(self, eng, interval=20):
        self.eng, self.interval = eng, interval
        self.known = set(eng.db.kv_get("wifi_known", []))
        self.first_pass = not self.known
        self.last_drone = 0

    def start(self):
        import threading
        threading.Thread(target=self._loop, daemon=True, name="wifi").start()

    def scan(self):
        ifc = iface()
        if not ifc:
            raise RuntimeError("no Wi-Fi interface")
        subprocess.run(["nmcli", "device", "wifi", "rescan", "ifname", ifc], capture_output=True, timeout=15)
        time.sleep(4)
        r = subprocess.run(["iw", "dev", ifc, "scan", "dump"], capture_output=True, text=True, timeout=20)
        if r.returncode:
            raise RuntimeError(r.stderr.strip() or "iw scan failed")
        return parse_iw(r.stdout)

    def _loop(self):
        while not self.eng.stop.is_set():
            try:
                self.evaluate(self.scan())
            except Exception as e:
                self.eng.status("drone", "watch", f"Wi-Fi scan unavailable: {e}", "wifi")
            self.eng.stop.wait(self.interval)

    def evaluate(self, bss_list):
        eng = self.eng
        drone_hits, cam_hits, new_aps = [], [], []
        for b in bss_list:
            ven = oui.vendor(b["bssid"], bssid=True)
            klass = oui.classify(ven, b["ssid"])
            b["vendor"], b["klass"] = ven, klass
            if b["rid_ies"]:
                for ie in b["rid_ies"]:
                    info = remoteid.from_wifi_vendor_ie(ie)
                    drone_hits.append((b, "Remote ID beacon (Wi-Fi)", info))
            elif klass == "drone" or DRONE_SSID.search(b["ssid"]):
                drone_hits.append((b, f"drone-like network ({ven})", {}))
            if klass == "camera" or CAMERA_SSID.search(b["ssid"]):
                b["klass"] = "camera"
                cam_hits.append(b)
            if b["bssid"] not in self.known:
                new_aps.append(b)
        eng.live.setdefault("drone_fixes", {})["wifi"] = [
            {"id": i.get("basic_id") or b["bssid"], "lat": i.get("lat"), "lon": i.get("lon"),
             "op_lat": i.get("operator_lat"), "op_lon": i.get("operator_lon"),
             "alt": i.get("alt_m"), "rssi": b["signal"]} for b, _w, i in drone_hits]
        # --- drones
        if drone_hits:
            b, why, info = max(drone_hits, key=lambda x: x[0]["signal"])
            loc = f" pos={info['lat']:.5f},{info['lon']:.5f}" if info.get("lat") else ""
            op = f" operator={info['operator_lat']:.5f},{info['operator_lon']:.5f}" if info.get("operator_lat") else ""
            ident = f" id={info['basic_id']}" if info.get("basic_id") else ""
            base = f"Broadcast CLAIMS a drone: {why} (unverified) ssid='{b['ssid']}' {b['bssid']} {b['signal']:.0f} dBm{ident}{loc}"
            eng.status("drone", "alert", base + op, "wifi")  # live only
            safe = {k: v for k, v in info.items() if not k.startswith("operator")}
            eng.emit("drone", "alert", "wifi_drone", b["bssid"], base, {**b, **safe}, 120)  # operator position NOT stored
        else:
            eng.status("drone", "ok", f"No drone signals ({len(bss_list)} Wi-Fi networks in range)", "wifi")
        # --- camera-looking APs (spy cams often broadcast their own AP)
        if cam_hits:
            b = max(cam_hits, key=lambda x: x["signal"])
            near = b["signal"] > -60
            msg = (f"Camera-like Wi-Fi source '{b['ssid']}' {b['bssid']} ({b['vendor']}) {b['signal']:.0f} dBm"
                   f"{' - VERY CLOSE' if near else ''}")
            eng.status("network", "alert" if near else "watch", msg, "wifi")
            eng.emit("network", "alert" if near else "watch", "wifi_camera", b["bssid"], msg, b, 1800)
        else:
            eng.status("network", "ok", "No camera-like Wi-Fi sources", "wifi")
        # --- learn / log new APs
        if self.first_pass:
            self.first_pass = False
        else:
            for b in new_aps:
                eng.emit("network", "info", "wifi_new_ap", b["bssid"],
                         f"New Wi-Fi network appeared: '{b['ssid'] or '(hidden)'}' {b['bssid']} "
                         f"{b['vendor']} {b['signal']:.0f} dBm", b, 86400)
        self.known |= {b["bssid"] for b in bss_list}
        eng.db.kv_set("wifi_known", sorted(self.known))
        eng.live["wifi"] = sorted(
            [{"ssid": b["ssid"] or "(hidden)", "bssid": b["bssid"], "signal": b["signal"],
              "vendor": b["vendor"], "klass": b["klass"]} for b in bss_list],
            key=lambda x: -x["signal"])[:25]
