"""Shared engine: sqlite log, live status per question, alerts."""
import json
import os
import secrets
import urllib.request
import shutil
import sqlite3
import subprocess
import threading
import time

DATA_DIR = os.environ.get("HOMEWATCH_DIR") or os.path.expanduser("~/.local/share/homewatch")
DOMAINS = {
    "drone": "Drone near the house?",
    "tracker": "Active tracker present?",
    "network": "Hidden camera / unknown device?",
    "rf": "Elevated RF / EMF? (RTL-SDR)",
    "host": "This computer's own camera/mic/remote access",
}
LEVELS = ("off", "ok", "watch", "alert")

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
PUSH_TEXT = {  # phone pushes are deliberately generic: no MACs, no coordinates
    "drone": "A drone signal was detected near the house.",
    "tracker": "A tracker has stayed close to the house.",
    "network": "Something new or camera-like showed up on your network.",
    "rf": "Unusual radio activity was detected.",
    "host": "Your computer's camera, mic or remote access triggered.",
}


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_PATH, 0o600)


def new_token():
    return secrets.token_urlsafe(9)


SCHEMA = """
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts REAL, domain TEXT,
  level TEXT, kind TEXT, key TEXT, msg TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS ev_ts ON events(ts);
CREATE TABLE IF NOT EXISTS beeps(id INTEGER PRIMARY KEY, ts REAL, note TEXT);
CREATE TABLE IF NOT EXISTS devices(mac TEXT PRIMARY KEY, first_seen REAL, last_seen REAL,
  ip TEXT, vendor TEXT, klass TEXT, ports TEXT, trusted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


class DB:
    def __init__(self, path=None):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.path = path or os.path.join(DATA_DIR, "homewatch.db")
        self.c = sqlite3.connect(self.path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.c.executescript(SCHEMA)

    def exec(self, sql, args=()):
        with self.lock:
            cur = self.c.execute(sql, args)
            self.c.commit()
            return cur

    def query(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.c.execute(sql, args).fetchall()]

    def prune(self, days=30):
        """Retention: don't keep sighting history forever."""
        self.exec("DELETE FROM events WHERE ts < ?", (time.time() - days * 86400,))
        self.exec("DELETE FROM beeps WHERE ts < ?", (time.time() - 365 * 86400,))

    def kv_get(self, k, default=None):
        r = self.query("SELECT v FROM kv WHERE k=?", (k,))
        return json.loads(r[0]["v"]) if r else default

    def kv_set(self, k, v):
        self.exec("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, json.dumps(v)))


class Engine:
    def __init__(self, db=None, quiet=False):
        self.db = db or DB()
        self.quiet = quiet
        self.state = {d: {"level": "off", "msg": "starting", "ts": time.time()} for d in DOMAINS}
        self.lock = threading.Lock()
        self.sources = {}
        self.started = time.time()
        self.stop = threading.Event()
        self._last_emit = {}
        self.live = {}  # free-form live detail per detector (shown on dashboard)
        self._last_push = {}

    # -- status -------------------------------------------------------
    def status(self, domain, level, msg, source="main"):
        """Each source reports its own level; the domain shows the worst one."""
        with self.lock:
            prev = self.state[domain]["level"]
            self.sources.setdefault(domain, {})[source] = (level, msg, time.time())
            worst = max(self.sources[domain].values(), key=lambda v: LEVELS.index(v[0]))
            self.state[domain] = {"level": worst[0], "msg": worst[1], "ts": time.time()}
            cur = worst[0]
        if cur == "alert" and prev != "alert":
            self.notify(f"HOMEWATCH ALERT: {DOMAINS[domain]}", worst[1], push=PUSH_TEXT.get(domain))

    # -- events -------------------------------------------------------
    def emit(self, domain, level, kind, key, msg, detail=None, cooldown=600):
        now = time.time()
        k = (kind, key)
        if now - self._last_emit.get(k, 0) < cooldown:
            return False
        self._last_emit[k] = now
        self.db.exec(
            "INSERT INTO events(ts,domain,level,kind,key,msg,detail) VALUES(?,?,?,?,?,?,?)",
            (now, domain, level, kind, key, msg, json.dumps(detail or {}, default=str)),
        )
        if not self.quiet:
            stamp = time.strftime("%H:%M:%S", time.localtime(now))
            print(f"[{stamp}] {level.upper():5} {domain:7} {msg}", flush=True)
        return True

    def beep(self, note="", ts=None):
        self.db.exec("INSERT INTO beeps(ts,note) VALUES(?,?)", (ts or time.time(), note))

    # -- alerting -----------------------------------------------------
    def push(self, text, title="Homewatch"):
        """Phone alert via ntfy.sh. Off until `homewatch ntfy on`. Never includes MACs/coordinates."""
        cfg = load_config().get("ntfy", {})
        if self.quiet or not (cfg.get("enabled") and cfg.get("topic")):
            return False
        now = time.time()
        if now - self._last_push.get(text, 0) < 120:
            return False
        self._last_push[text] = now
        try:
            req = urllib.request.Request(f"https://ntfy.sh/{cfg['topic']}", data=text.encode(),
                                         headers={"Title": title, "Tags": "satellite"}, method="POST")
            urllib.request.urlopen(req, timeout=8).read()
            return True
        except Exception:
            return False

    def notify(self, title, body, push=None):
        if self.quiet:
            return
        if push:
            threading.Thread(target=self.push, args=(push,), daemon=True).start()
        # Soft chime only - no voice. Set HOMEWATCH_SOUND=off to silence completely.
        if os.environ.get("HOMEWATCH_SOUND", "ding") != "off" and shutil.which("paplay"):
            snd = "/usr/share/sounds/freedesktop/stereo/message.oga"
            subprocess.Popen(["paplay", snd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-u", "normal", title, body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def snapshot(self):
        with self.lock:
            st = {d: dict(v, title=DOMAINS[d]) for d, v in self.state.items()}
        recent = self.db.query("SELECT ts,domain,level,msg FROM events ORDER BY id DESC LIMIT 40")
        return {"now": time.time(), "state": st, "events": recent, "live": self.live,
                "home": load_config().get("home"), "my_ssids": load_config().get("my_ssids", []), "started": self.started}
