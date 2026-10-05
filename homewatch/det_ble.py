"""Bluetooth LE detector: Remote ID drones + AirTag/Tile/SmartTag/Chipolo trackers."""
import asyncio
import time

from . import remoteid

BASE = "-0000-1000-8000-00805f9b34fb"
TRACKER_UUIDS = {
    "feed": "Tile tracker", "fd84": "Tile tracker", "fd5a": "Samsung SmartTag",
    "fe33": "Chipolo tracker", "fe65": "Chipolo tracker", "fcb2": "Apple Find My accessory",
    "fd44": "Apple Find My accessory",
}
REMOTE_ID_UUID = "fffa"
WINDOW = 300  # seconds a sighting stays "current"


def short_uuid(u):
    u = u.lower()
    if u.endswith(BASE) and u.startswith("0000"):
        return u[4:8]
    return u


def classify_adv(manufacturer_data, service_data, service_uuids, name=""):
    """-> (kind, label, extra) where kind in 'drone' | 'tracker' | None."""
    sd = {short_uuid(k): v for k, v in (service_data or {}).items()}
    if REMOTE_ID_UUID in sd:
        return "drone", "Remote ID broadcast", remoteid.from_ble_service_data(sd[REMOTE_ID_UUID])
    mfr = manufacturer_data or {}
    apple = mfr.get(0x004C)
    if apple and len(apple) >= 2 and apple[0] == 0x12:
        if apple[1] >= 0x10:  # long payload = SEPARATED from its owner (what a planted AirTag looks like)
            return "tracker", "Apple Find My tracker SEPARATED from its owner", {}
        return "ambient", "Apple device with owner nearby (normal)", {}  # len 0x02 = owner's device in range
    for u in list(sd) + [short_uuid(u) for u in (service_uuids or [])]:
        if u in TRACKER_UUIDS:
            return "tracker", TRACKER_UUIDS[u], {}
    n = (name or "").lower()
    if any(w in n for w in ("airtag", "smarttag", "tile", "chipolo", "pebblebee", "tracker")):
        return "tracker", f"tracker by name ({name})", {}
    return None, None, {}


class BLEDetector:
    def __init__(self, eng):
        self.eng = eng
        self.seen = {}      # addr -> sighting
        self.seen_total = 0
        self.ambient = 0
        self.ignored = set(eng.db.kv_get("ble_ignore", []))

    def start(self):
        import threading
        threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True, name="ble").start()

    def _cb(self, device, adv):
        self.seen_total += 1
        try:
            kind, label, extra = classify_adv(adv.manufacturer_data, adv.service_data,
                                              adv.service_uuids, adv.local_name or device.name or "")
        except Exception:  # hostile/garbled advertisement must never kill the scanner
            return
        if not kind:
            return
        if kind == "ambient":
            self.ambient += 1
            return
        now = time.time()
        s = self.seen.get(device.address)
        if not s:
            s = self.seen[device.address] = {"kind": kind, "label": label, "first": now, "n": 0,
                                             "rssi_max": -999, "extra": {}}
        s["last"], s["rssi"] = now, adv.rssi
        s["n"] += 1
        s["rssi_max"] = max(s["rssi_max"], adv.rssi)
        if extra:
            s["extra"].update(extra)

    async def _main(self):
        from bleak import BleakScanner
        while not self.eng.stop.is_set():
            try:
                scanner = BleakScanner(self._cb)
                await scanner.start()
                while not self.eng.stop.is_set():
                    await asyncio.sleep(5)
                    self._evaluate()
                await scanner.stop()
            except Exception as e:  # adapter off / BlueZ hiccup
                self.eng.status("drone", "watch", f"Bluetooth scan unavailable: {e}", "ble")
                self.eng.status("tracker", "watch", f"Bluetooth scan unavailable: {e}")
                await asyncio.sleep(15)

    def _evaluate(self):
        now = time.time()
        self.ignored = set(self.eng.db.kv_get("ble_ignore", []))   # picks up 'This is mine' taps right away
        drones, trackers = [], []
        for addr, s in self.seen.items():
            if now - s["last"] > WINDOW:
                continue
            (drones if s["kind"] == "drone" else trackers).append((addr, s))
        self.eng.live["ble"] = {"advertisements_seen": self.seen_total,
                                "trackers": [self._row(a, s, now) for a, s in trackers],
                                "drones": [self._row(a, s, now) for a, s in drones]}
        self.eng.live.setdefault("drone_fixes", {})["ble"] = [
            {"id": s["extra"].get("basic_id", a), "lat": s["extra"].get("lat"), "lon": s["extra"].get("lon"),
             "op_lat": s["extra"].get("operator_lat"), "op_lon": s["extra"].get("operator_lon"),
             "alt": s["extra"].get("alt_m"), "rssi": s.get("rssi")} for a, s in drones]
        # drones
        if drones:
            addr, s = drones[0]
            e = s["extra"]
            where = f" at {e['lat']:.5f},{e['lon']:.5f}" if e.get("lat") else ""
            base = f"Remote ID broadcast CLAIMS a drone (Bluetooth; unverified) id={e.get('basic_id','?')} rssi={s['rssi']}{where}"
            op = f", operator at {e['operator_lat']:.5f},{e['operator_lon']:.5f}" if e.get("operator_lat") else ""
            self.eng.status("drone", "alert", base + op, "ble")  # live only
            safe = {k: v for k, v in s["extra"].items() if not k.startswith("operator")}
            self.eng.emit("drone", "alert", "ble_remote_id", e.get("basic_id", addr), base,  # operator position NOT stored
                          {"addr": addr, **safe}, 120)
        else:
            self.eng.status("drone", "ok", "No Remote ID drone heard (Bluetooth)", "ble")
        # trackers
        live = [(a, s) for a, s in trackers if a not in self.ignored]
        if live:
            addr, s = max(live, key=lambda x: x[1]["rssi"])
            dur = int(s["last"] - s["first"])
            msg = f"{s['label']} nearby: {addr} rssi={s['rssi']} dBm, seen {dur}s"
            close = dur >= 300 and s["n"] >= 5 and s["rssi_max"] >= -70  # persistent AND close (weak/far = neighbor)
            self.eng.status("tracker", "alert" if close else "watch", msg)
            self.eng.emit("tracker", "alert" if close else "watch", "ble_tracker", addr, msg,
                          {"addr": addr, "rssi": s["rssi"], "label": s["label"]}, 900)
        else:
            own = sum(1 for a, _ in trackers if a in self.ignored)
            self.eng.status("tracker", "ok", f"No unknown trackers in range ({self.seen_total} BLE ads heard, {self.ambient} normal Apple devices ignored"
                            + (f", {own} of your own trackers" if own else "") + ")")

    def _row(self, addr, s, now):
        return {"mine": addr in self.ignored, "addr": addr, "label": s["label"], "rssi": s.get("rssi"), "seen_s": int(s["last"] - s["first"]),
                "ago_s": int(now - s["last"])}
