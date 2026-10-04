"""RTL-SDR RF watch. Dormant until an RTL-SDR dongle + rtl_power are present.

Sweeps the bands where bugs, trackers, handhelds and analog 1.2 GHz video transmitters live,
learns a per-band baseline, and flags carriers well above it.
"""
import shutil
import statistics
import subprocess
import time

BANDS = [
    ("VHF handheld/FRS 136-174 MHz", 136e6, 174e6),
    ("UHF 400-470 MHz (GMRS, bugs)", 400e6, 470e6),
    ("ISM 433 MHz (sensors, key fobs, bugs)", 430e6, 440e6),
    ("ISM 868 MHz (EU trackers/sensors)", 863e6, 870e6),
    ("ISM 915 MHz (US trackers/sensors/LoRa)", 902e6, 928e6),
    ("1.2 GHz analog video / spy-cam TX", 1.08e9, 1.32e9),
]
LEARN_SWEEPS = 12
JUMP_DB = 12.0


def parse_rtl_power(text):
    """-> (peak_db, peak_hz, median_db) over all rows of an rtl_power CSV."""
    peak, peak_hz, vals = -999.0, 0.0, []
    for line in text.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 7:
            continue
        try:
            lo, step = float(p[2]), float(p[4])
            dbs = [float(x) for x in p[6:]]
        except ValueError:
            continue
        for i, d in enumerate(dbs):
            vals.append(d)
            if d > peak:
                peak, peak_hz = d, lo + i * step
    if not vals:
        return None
    return peak, peak_hz, statistics.median(vals)


def dongle_present():
    if not shutil.which("rtl_power"):
        return False
    try:
        r = subprocess.run(["lsusb"], capture_output=True, text=True).stdout
        return "0bda:2838" in r or "0bda:2832" in r or "RTL28" in r
    except Exception:
        return False


class SdrDetector:
    def __init__(self, eng):
        self.eng = eng
        self.hist = {b[0]: [] for b in BANDS}

    def start(self):
        import threading
        if not dongle_present():
            self.eng.status("rf", "off", "RTL-SDR not detected (install rtl-sdr, plug in dongle, restart)")
            return False
        threading.Thread(target=self._loop, daemon=True, name="sdr").start()
        return True

    def _loop(self):
        while not self.eng.stop.is_set():
            hot = []
            for name, lo, hi in BANDS:
                try:
                    r = subprocess.run(["rtl_power", "-f", f"{int(lo)}:{int(hi)}:25k", "-i", "4", "-1", "-"],
                                       capture_output=True, text=True, timeout=60)
                except subprocess.TimeoutExpired:
                    continue
                res = parse_rtl_power(r.stdout)
                if not res:
                    self.eng.status("rf", "watch", f"rtl_power returned no data: {r.stderr.strip()[:80]}")
                    continue
                peak, hz, floor = res
                h = self.hist[name]
                if len(h) >= LEARN_SWEEPS:
                    base = statistics.mean(x[0] for x in h)
                    if peak > base + JUMP_DB:
                        hot.append((name, hz, peak, base))
                        self.eng.emit("rf", "alert", "rf_spike", name,
                                      f"RF carrier in {name}: {hz/1e6:.3f} MHz at {peak:.0f} dB "
                                      f"(baseline {base:.0f} dB)", {"hz": hz, "peak": peak, "base": base}, 600)
                h.append((peak, hz, floor))
                del h[:-200]
                self.eng.live.setdefault("rf", {})[name] = {"peak_db": round(peak, 1), "mhz": round(hz / 1e6, 3),
                                                             "floor_db": round(floor, 1), "samples": len(h)}
            if hot:
                n, hz, p, b = hot[0]
                self.eng.status("rf", "alert", f"RF jump in {n}: {hz/1e6:.3f} MHz, +{p-b:.0f} dB over baseline")
            elif all(len(h) < LEARN_SWEEPS for h in self.hist.values()):
                self.eng.status("rf", "watch", "RF baseline learning (leave running ~10 min)")
            else:
                self.eng.status("rf", "ok", "RF levels within baseline in all watched bands")
        return
