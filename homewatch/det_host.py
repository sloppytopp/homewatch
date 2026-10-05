"""This computer: who is using camera/mic, new listening ports, new USB devices, remote-access tools."""
import glob
import os
import re
import time
import subprocess

REMOTE_TOOLS = re.compile(r"anydesk|teamviewer|rustdesk|x11vnc|vncserver|Xvnc|tigervnc|vino|"
                          r"ngrok|chrome-remote|zerotier|screenconnect|rdesktop|xrdp", re.I)


def fd_users(patterns):
    """Processes (of any readable user) holding the given device files open."""
    hits = {}
    devs = {os.path.realpath(p) for pat in patterns for p in glob.glob(pat)}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                tgt = os.path.realpath(f"/proc/{pid}/fd/{fd}")
                if tgt in devs:
                    name = open(f"/proc/{pid}/comm").read().strip()
                    hits.setdefault(tgt, set()).add(f"{name}({pid})")
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
    return hits


def audio_recorders():
    """Apps actually recording audio via PipeWire/Pulse (not the audio server itself, not output monitors)."""
    try:
        out = subprocess.run(["pactl", "list", "source-outputs"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None  # pactl unavailable
    apps = []
    for blk in out.split("Source Output #")[1:]:
        if "Corked: yes" in blk:
            continue
        m = re.search(r'application.name = "([^"]+)"', blk)
        src = re.search(r"Source: (\d+)", blk)
        apps.append(m.group(1) if m else "unknown app")
    return apps


# UDP ports used by ordinary LAN discovery / DHCP: seeing them appear is normal, never an alarm.
LAN_DISCOVERY_UDP = {5353, 5355, 3702, 1900, 67, 68, 546, 547}


# Virtual bridges (Bluetooth PAN, libvirt, Docker) run their own DHCP/DNS for tethering/containers; not an exposure to the real LAN.
VIRTUAL_IFACE = re.compile(r"^(pan|virbr|docker|br-|veth|lxcbr)")


def port_class(entry):
    """'info' = harmless-looking (loopback-only, or ordinary LAN discovery); 'alert' = reachable from other machines."""
    proto, addr, *_ = entry.split(None, 2)
    host, _, port = addr.rpartition(":")
    host = host.strip("[]")
    if host.startswith("127.") or host == "::1":
        return "info"
    iface = host.partition("%")[2]
    if iface and VIRTUAL_IFACE.match(iface):
        return "info"
    if proto.startswith("udp") and port.isdigit() and int(port) in LAN_DISCOVERY_UDP:
        return "info"
    return "alert"


def listening():
    out = subprocess.run(["ss", "-H", "-tulnp"], capture_output=True, text=True).stdout
    res = set()
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 5:
            proc = re.search(r'users:\(\("([^"]+)"', line)
            port = p[4].rsplit(":", 1)[-1]
            if p[0].startswith("udp") and port.isdigit() and int(port) >= 32768:
                continue  # ephemeral UDP (browser WebRTC/QUIC etc.) - noise
            res.add(f"{p[0]} {p[4]} {proc.group(1) if proc else '?'}")
    return res


def usb_devices():
    out = subprocess.run(["lsusb"], capture_output=True, text=True).stdout
    return {re.sub(r"Bus \d+ Device \d+: ", "", l) for l in out.splitlines()}


class HostDetector:
    def __init__(self, eng, interval=30, own_port=None):
        self.eng, self.interval, self.own_port = eng, interval, own_port
        self.base_ports = set(eng.db.kv_get("host_ports", []))
        self.base_usb = set(eng.db.kv_get("host_usb", []))
        self.learn = not self.base_ports
        self.usb_pending = {}

    def start(self):
        import threading
        threading.Thread(target=self._loop, daemon=True, name="host").start()

    def _loop(self):
        while not self.eng.stop.is_set():
            try:
                self.check()
            except Exception as e:
                self.eng.status("host", "watch", f"host check failed: {e}")
            self.eng.stop.wait(self.interval)

    def check(self):
        eng = self.eng
        problems, notes = [], []
        cam = fd_users(["/dev/video*"])
        for dev, who in cam.items():
            problems.append(f"{dev} in use by {', '.join(sorted(who))}")
        rec = audio_recorders()
        if rec is None:  # no pactl: fall back to raw device check, ignoring the audio server itself
            for dev, who in fd_users(["/dev/snd/pcmC*D*c"]).items():
                who = {w for w in who if not w.startswith(("pipewire", "wireplumber", "pulseaudio"))}
                if who:
                    problems.append(f"microphone device in use by {', '.join(sorted(who))}")
        elif rec:
            problems.append(f"microphone is being recorded by: {', '.join(rec)}")
        ports, usb = listening(), usb_devices()
        if self.own_port:
            ports = {p for p in ports if not p.split()[1].endswith(f':{self.own_port}')}
        if self.learn:
            self.base_ports, self.base_usb, self.learn = ports, usb, False
            eng.db.kv_set("host_ports", sorted(ports))
            eng.db.kv_set("host_usb", sorted(usb))
        watching = []
        # new listening ports: harmless ones are logged once and then treated as normal; reachable ones stay red until approved
        for p in sorted(ports - self.base_ports):
            if port_class(p) == "info":
                eng.emit("host", "info", "hostport", p, f"new listening port (local/discovery only): {p}", cooldown=0)
                self.base_ports.add(p)
                eng.db.kv_set("host_ports", sorted(self.base_ports))
            else:
                problems.append(f"new listening port reachable from the network: {p}  (check it, then run: homewatch rebaseline)")
        # new USB devices: amber for 10 minutes, then accepted as normal (it is logged either way)
        now = time.time()
        for u in sorted(usb - self.base_usb):
            until = self.usb_pending.setdefault(u, now + 600)
            if until == now + 600:
                eng.emit("host", "watch", "usb", u, f"new USB device: {u}", cooldown=0)
            if now < until:
                watching.append(f"new USB device: {u}")
            else:
                self.base_usb.add(u)
                self.usb_pending.pop(u, None)
                eng.db.kv_set("host_usb", sorted(self.base_usb))
        for line in subprocess.run(["ps", "-eo", "pid,comm,args"], capture_output=True, text=True).stdout.splitlines():
            if REMOTE_TOOLS.search(line.split(None, 2)[1] if len(line.split(None, 2)) > 1 else ""):
                problems.append(f"remote-access tool running: {line.strip()[:80]}")
        if problems:
            eng.status("host", "alert", "; ".join(problems[:3]))
            for p in problems:
                eng.emit("host", "alert", "host", p, p, cooldown=3600)
        elif watching:
            eng.status("host", "watch", "; ".join(watching[:3]))
        else:
            eng.status("host", "ok", "No camera/mic use, no new ports or USB devices, no remote-access tools")
        eng.live["host"] = {"listening": sorted(ports), "usb": sorted(usb), "no_video_devices": not glob.glob("/dev/video*")}
