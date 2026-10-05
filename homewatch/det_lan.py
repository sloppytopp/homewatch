"""LAN inventory: every device on your network, camera vendors, video-stream ports, newcomers."""
import concurrent.futures as cf
import ipaddress
import re
import socket
import subprocess
import time

from . import oui

VIDEO_PORTS = {554: "RTSP video stream", 8554: "RTSP video stream", 8000: "Hikvision SDK", 37777: "Dahua SDK",
               5000: "camera/NAS stream", 8899: "ONVIF/camera", 34567: "Xiongmai DVR", 1935: "RTMP stream",
               81: "alt-HTTP camera"}


def parse_neigh(text):
    """`ip neigh` -> {ip: mac}"""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^(\d+\.\d+\.\d+\.\d+) .*lladdr ([0-9a-f:]{17}) (\w+)", line)
        if m and m.group(3) not in ("FAILED", "INCOMPLETE"):
            out[m.group(1)] = m.group(2).lower()
    return out


def local_net():
    out = subprocess.run(["ip", "-4", "-o", "route", "show", "default"], capture_output=True, text=True).stdout
    m = re.search(r"default via (\S+) dev (\S+)", out)
    gw, ifc = (m.group(1), m.group(2)) if m else (None, None)
    a = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", ifc or "lo"], capture_output=True, text=True).stdout
    m = re.search(r"inet (\S+)", a)
    return gw, ifc, (ipaddress.ip_interface(m.group(1)) if m else None)


def ping(ip):
    subprocess.run(["ping", "-c", "1", "-W", "1", str(ip)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def probe_ports(ip, ports=tuple(VIDEO_PORTS)):
    found = {}
    for p in ports:
        s = socket.socket()
        s.settimeout(0.4)
        try:
            if s.connect_ex((ip, p)) == 0:
                found[p] = VIDEO_PORTS[p]
        except OSError:
            pass
        finally:
            s.close()
    return found


class LanDetector:
    def __init__(self, eng, interval=60):
        self.eng, self.interval = eng, interval
        self.baseline_done = eng.db.kv_get("lan_baseline", False)

    def start(self):
        import threading
        threading.Thread(target=self._loop, daemon=True, name="lan").start()

    def _loop(self):
        while not self.eng.stop.is_set():
            try:
                self.scan()
            except Exception as e:
                self.eng.status("network", "watch", f"LAN scan failed: {e}", "lan")
            self.eng.stop.wait(self.interval)

    def announce(self, newcomers):
        """Log + chime once for every device that newly joined the network."""
        for ip, mac, ven, klass, pts in newcomers:
            msg = f"NEW device joined your network: {ip} {mac} {ven} [{klass}] {pts or ''}"
            if self.eng.emit("network", "alert" if klass.startswith("camera") else "watch", "lan_new", mac, msg,
                             {"ip": ip, "mac": mac, "vendor": ven}, 3600):
                self.eng.notify("New device on your network", f"{ip}  {mac}  {ven}",
                                push="A new device joined your Wi-Fi.")

    def scan(self):
        eng = self.eng
        gw, ifc, me = local_net()
        if not me or me.network.num_addresses > 1024:
            raise RuntimeError("no usable LAN")
        cur = str(me.network)
        home = eng.db.kv_get("lan_subnet")
        if not home and self.baseline_done:
            eng.db.kv_set("lan_subnet", cur)          # existing install: the network we've been watching is home
            home = cur
        if home and cur != home:
            # e.g. a phone's USB-tether network: its gateway is not a stranger joining YOUR network
            eng.emit("network", "info", "lan_other", cur, f"On a different network ({cur} via {ifc}); LAN inventory paused until back on {home}", cooldown=3600)
            eng.status("network", "ok", f"LAN inventory paused - on a different network ({cur}); home network is {home}", "lan")
            return
        hosts = [str(h) for h in me.network.hosts() if str(h) != str(me.ip)]
        with cf.ThreadPoolExecutor(64) as ex:
            list(ex.map(ping, hosts))
        neigh = parse_neigh(subprocess.run(["ip", "neigh", "show", "dev", ifc], capture_output=True, text=True).stdout)
        now = time.time()
        known = {d["mac"]: d for d in eng.db.query("SELECT * FROM devices")}
        with cf.ThreadPoolExecutor(32) as ex:
            ports = dict(zip(neigh, ex.map(probe_ports, neigh)))
        cams, newcomers, inventory = [], [], []
        for ip, mac in neigh.items():
            ven = oui.vendor(mac)
            klass = oui.classify(ven)
            pts = ports.get(ip, {})
            if klass in ("other", "iot") and set(pts) & oui.STRONG_VIDEO_PORTS:
                klass = "camera?"  # unknown vendor exposing real camera/NVR protocol ports
            if mac not in known:
                eng.db.exec("INSERT INTO devices(mac,first_seen,last_seen,ip,vendor,klass,ports,trusted) "
                            "VALUES(?,?,?,?,?,?,?,?)",
                            (mac, now, now, ip, ven, klass, ",".join(map(str, pts)), 0))
                if self.baseline_done:
                    newcomers.append((ip, mac, ven, klass, pts))
            else:
                eng.db.exec("UPDATE devices SET last_seen=?, ip=?, klass=?, ports=? WHERE mac=?",
                            (now, ip, klass, ",".join(map(str, pts)), mac))
            inventory.append({"ip": ip, "mac": mac, "vendor": ven, "klass": klass,
                              "ports": pts, "gateway": ip == gw})
            if klass.startswith("camera") or pts:
                cams.append(inventory[-1])
        # --- status
        self.announce(newcomers)
        fresh = eng.db.query("SELECT * FROM devices WHERE trusted=0 AND last_seen>?", (now - 600,))
        if any(d["klass"].startswith("camera") for d in fresh):
            d = next(d for d in fresh if d["klass"].startswith("camera"))
            eng.status("network", "alert", f"Untrusted camera-class device {d['ip']} {d['mac']} ({d['vendor']}). "
                       f"Run: homewatch trust {d['mac']} if it's yours", "lan")
        elif fresh:
            eng.status("network", "watch", f"{len(fresh)} device(s) on your network not yet reviewed - run: homewatch setup", "lan")
        else:
            note = f"; {len(cams)} camera-class/video-port device(s) are in your trusted list" if cams else ""
            eng.status("network", "ok", f"{len(neigh)} devices on LAN, all known{note}", "lan")
        if not self.baseline_done:
            eng.db.kv_set("lan_baseline", True)
            eng.db.kv_set("lan_subnet", cur)
            self.baseline_done = True
            eng.emit("network", "info", "lan_baseline", "x",
                     f"Baseline recorded: {len(neigh)} devices on LAN (review with: homewatch devices)", cooldown=0)
        eng.live["lan"] = inventory
