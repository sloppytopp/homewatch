"""ASTM F3411 / FAA Remote ID parser (Bluetooth service-data 0xFFFA and Wi-Fi beacon IE)."""
import struct

ID_TYPES = {0: "none", 1: "serial (ANSI/CTA-2063-A)", 2: "CAA registration", 3: "UTM session", 4: "specific session"}
UA_TYPES = {0: "none", 1: "aeroplane", 2: "helicopter/multirotor", 3: "gyroplane", 4: "VTOL", 5: "ornithopter",
            6: "glider", 7: "kite", 8: "free balloon", 9: "captive balloon", 10: "airship", 11: "parachute",
            12: "rocket", 13: "tethered", 14: "ground obstacle", 15: "other"}


def _s(b):
    return b.split(b"\x00")[0].decode("ascii", "replace").strip()


def _lat(b):
    v = struct.unpack("<i", b)[0] * 1e-7
    return v if v and -90 <= v <= 90 else None


def _lon(b):
    v = struct.unpack("<i", b)[0] * 1e-7
    return v if v and -180 <= v <= 180 else None


def parse_message(m):
    """Parse one 25-byte message -> dict (or None)."""
    if len(m) < 25:
        return None
    t = m[0] >> 4
    if t == 0:
        return {"basic_id": _s(m[2:22]), "id_type": ID_TYPES.get(m[1] >> 4, "?"),
                "ua_type": UA_TYPES.get(m[1] & 0xF, "?")}
    if t == 1:
        # speed: 255 = unknown; multiplier flag -> value*0.75 + 255*0.25 (ASTM F3411)
        spd = None if m[3] == 255 else (m[3] * 0.75 + 255 * 0.25 if m[1] & 1 else m[3] * 0.25)

        def alt_of(b):
            v = struct.unpack("<H", b)[0]
            return None if v == 0xFFFF else round(v * 0.5 - 1000, 1)  # 0xFFFF = unknown
        return {"lat": _lat(m[5:9]), "lon": _lon(m[9:13]),
                "speed_ms": None if spd is None else round(spd, 1),
                "alt_m": alt_of(m[15:17]), "height_agl_m": alt_of(m[17:19]),
                "status": {0: "undeclared", 1: "ground", 2: "airborne", 3: "emergency"}.get(m[1] >> 4, "?")}
    if t == 4:
        return {"operator_lat": _lat(m[2:6]), "operator_lon": _lon(m[6:10])}
    if t == 5:
        return {"operator_id": _s(m[2:22])}
    if t == 3:
        return {"description": _s(m[2:25])}
    return {}


def _parse_pack(buf):
    """Parse a bare message (25 bytes) or a message pack (0xF?, size, count, msgs...)."""
    out = {}
    if not buf:
        return out
    if buf[0] >> 4 == 0xF and len(buf) >= 3:
        size, count = buf[1] or 25, buf[2]
        for i in range(count):
            out.update(parse_message(buf[3 + i * size: 3 + (i + 1) * size]) or {})
    else:
        out.update(parse_message(buf[:25]) or {})
    return out


def parse_pack(buf):
    """Radio input is attacker-controlled: never raise."""
    try:
        return _parse_pack(buf)
    except Exception:
        return {}


def from_ble_service_data(payload):
    """BLE 0xFFFA service data: [app code 0x0D][counter][25-byte message]."""
    if len(payload) >= 27 and payload[0] == 0x0D:
        return parse_pack(payload[2:])
    return parse_pack(payload)


def from_wifi_vendor_ie(data_hex):
    """Wi-Fi beacon vendor IE (OUI FA:0B:BC) data bytes: [0x0D][counter][message pack]."""
    try:
        raw = bytes(int(x, 16) for x in data_hex.split())
    except ValueError:
        return {}
    if raw and raw[0] == 0x0D:
        return parse_pack(raw[2:])
    return parse_pack(raw)
