"""MAC vendor lookup + device classification from the system OUI databases."""
import functools
import re

def _rx(words):
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I)


# Tight lists: only vendors that make (mostly) cameras/drones. Routers, chargers, thermostats and
# generic "shenzhen ... technology" OUIs are NOT included - they caused false camera alarms.
CAMERA_VENDORS = _rx(["hikvision", "hangzhou hikvision", "dahua", "zhejiang dahua", "reolink", "wyze", "amcrest",
                      "foscam", "axis communications", "arlo", "lorex", "swann", "vivotek", "hanwha",
                      "annke", "xiaoyi", "yi technology", "xiongmai", "hangzhou xiongmai", "uniview",
                      "tiandy", "ezviz", "imou", "wansview", "sricam", "yoosee", "vstarcam", "jooan",
                      "tenvis", "mobotix", "kuna", "simplisafe", "canary connect", "eufy"])
DRONE_VENDORS = _rx(["dji", "sz dji technology", "parrot", "autel", "skydio", "yuneec", "hubsan", "ryze",
                     "fimi", "holy stone", "potensic", "syma", "walkera", "zerotech"])
IOT_VENDORS = _rx(["espressif", "tuya", "ai-thinker", "hi-flying", "beken", "bouffalo"])
# Only ports that are really camera/NVR protocols may upgrade an unknown device to "camera?"
STRONG_VIDEO_PORTS = {554, 8554, 8000, 37777, 34567, 8899}


@functools.lru_cache(maxsize=1)
def _table():
    t = {}
    try:
        with open("/usr/share/ieee-data/oui.txt", errors="ignore") as f:
            for line in f:
                m = re.match(r"^([0-9A-F]{2})-([0-9A-F]{2})-([0-9A-F]{2})\s+\(hex\)\s+(.+)$", line)
                if m:
                    t["".join(m.group(1, 2, 3))] = m.group(4).strip()
    except OSError:
        pass
    try:
        with open("/usr/share/nmap/nmap-mac-prefixes", errors="ignore") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    k, _, v = line.partition(" ")
                    t.setdefault(k.upper(), v.strip())
    except OSError:
        pass
    return t


def is_random(mac):
    """Locally-administered bit set -> randomized/private address."""
    try:
        return bool(int(mac.replace(":", "")[:2], 16) & 0x02)
    except ValueError:
        return False


def table_size():
    return len(_table())


def vendor(mac, bssid=False):
    """Vendor name. For client devices a locally-administered MAC means 'randomized'.
    For BSSIDs (routers/APs) that bit is usually just a virtual-AP address derived from the real
    one, so clear it and look the vendor up instead of giving up."""
    raw = mac.upper().replace(":", "").replace("-", "")
    key = raw[:6]
    if bssid:
        v = _table().get(key)
        if not v and is_random(mac):
            v = _table().get(f"{int(raw[:2], 16) & ~0x02:02X}{raw[2:6]}")
        return v or "(unknown vendor)"
    if is_random(mac):
        return "(randomized MAC)"
    return _table().get(key, "(unknown vendor)")


def classify(vendor_name, ssid=""):
    """-> 'drone' | 'camera' | 'iot' | 'other'"""
    s = f"{vendor_name} {ssid}"
    if DRONE_VENDORS.search(vendor_name):
        return "drone"
    if CAMERA_VENDORS.search(vendor_name):
        return "camera"
    if IOT_VENDORS.search(vendor_name):
        return "iot"
    return "other"
