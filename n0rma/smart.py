"""Sort nearby gadgets into broad maker groups by network name, Bluetooth name and maker. A hint, never proof: a device that hides its name will not show up."""
import re

GROUPS = {
    "amazon": ("Amazon (Echo, Ring, Fire TV, Sidewalk)", "Amazon devices can share a slice of your internet connection with neighbours' devices through Sidewalk unless you turn it off."),
    "google": ("Google (Nest, Home, Chromecast)", "Speakers, displays and cameras with microphones or cameras built in."),
    "samsung": ("Samsung (SmartThings, TVs, SmartTag)", "TVs, hubs and tags that report to Samsung's cloud."),
    "camera": ("Cameras and doorbells", "Anything that looks like a camera or video doorbell by its network name or maker."),
    "iot": ("Smart plugs, bulbs and other gadgets", "Cheap internet-connected gadgets: often unmanaged, rarely updated."),
    "media": ("TVs and streaming boxes", "Roku, Sonos, Apple TV and similar."),
}

_I = re.IGNORECASE
_AMAZON = re.compile(r"(^|[^a-z])(echo|alexa|ring[-_ ]|amazon|fire[-_ ]?(tv|stick)|kindle|blink)", _I)
_GOOGLE = re.compile(r"(nest|google[-_ ]?home|chromecast|google ?(mini|hub)|^GHome)", _I)
_SAMSUNG = re.compile(r"(smartthings|^\[?(TV|AV)\]? ?samsung|samsung|galaxy ?(tag|smart)|smarttag)", _I)
_CAMERA = re.compile(r"(wyze|arlo|eufy|reolink|tapo[-_ ]?cam|doorbell|cam(era)?[-_ ]|ipcam|hikvision|dahua|yi[-_ ]|ezviz|blink)", _I)
_IOT = re.compile(r"(tuya|smartlife|shelly|kasa|tp-?link_smart|esp[-_ ]?\d|^esp_|tasmota|govee|hue|lifx|meross|sonoff|switchbot|wiz_|bulb|plug)", _I)
_MEDIA = re.compile(r"(roku|sonos|apple ?tv|bravia|vizio|lg ?webos|\[lg\]|firetv)", _I)


def classify(name, klass="", vendor=""):
    n = (name or "").strip()
    if klass == "camera" or _CAMERA.search(n):
        return "camera"
    if _AMAZON.search(n) or (vendor or "").startswith("Amazon"):
        return "amazon"
    if _GOOGLE.search(n):
        return "google"
    if _SAMSUNG.search(n):
        return "samsung"
    if _MEDIA.search(n):
        return "media"
    if _IOT.search(n):
        return "iot"
    return None


def group_live(live):
    """live: the dashboard's live dict. Returns {group: [{title, sub, signal, addr}]}, strongest first, empty groups omitted."""
    out = {}
    for w in live.get("wifi", []) or []:
        g = classify(w.get("ssid", ""), w.get("klass", ""), w.get("vendor", ""))
        if g:
            out.setdefault(g, []).append({"title": w.get("ssid") or "(hidden)", "sub": "Wi-Fi · " + str(w.get("bssid", "")), "signal": w.get("signal", -100), "addr": str(w.get("bssid", ""))})
    ble = live.get("ble") or {}
    for t in (ble.get("trackers") or []) + (ble.get("drones") or []):
        g = classify(t.get("label", ""))
        if g:
            out.setdefault(g, []).append({"title": t.get("label", ""), "sub": "Bluetooth · " + str(t.get("addr", "")), "signal": t.get("rssi", -100), "addr": str(t.get("addr", ""))})
    for g in out:
        out[g].sort(key=lambda r: r["signal"], reverse=True)
    return out
