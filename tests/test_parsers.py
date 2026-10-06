import struct
import unittest

from homewatch import remoteid, det_ble, det_wifi, det_lan, det_sdr, oui
from homewatch.core import DB, Engine


def loc_msg(lat, lon):
    m = bytearray(25)
    m[0] = 0x10
    m[1] = 0x20  # airborne
    m[3] = 40    # speed
    m[5:9] = struct.pack("<i", int(lat * 1e7))
    m[9:13] = struct.pack("<i", int(lon * 1e7))
    m[15:17] = struct.pack("<H", int((120 + 1000) * 2))
    m[17:19] = struct.pack("<H", int((60 + 1000) * 2))
    return bytes(m)


def basic_msg(ident):
    m = bytearray(25)
    m[0] = 0x00
    m[1] = 0x12  # serial, multirotor
    m[2:2 + len(ident)] = ident.encode()
    return bytes(m)


def sys_msg(lat, lon):
    m = bytearray(25)
    m[0] = 0x40
    m[2:6] = struct.pack("<i", int(lat * 1e7))
    m[6:10] = struct.pack("<i", int(lon * 1e7))
    return bytes(m)


def pack(*msgs):
    return bytes([0xF2, 25, len(msgs)]) + b"".join(msgs)


class RemoteID(unittest.TestCase):
    def test_pack(self):
        d = remoteid.parse_pack(pack(basic_msg("1581F4XYZ123"), loc_msg(33.5, -85.3), sys_msg(33.51, -85.31)))
        self.assertEqual(d["basic_id"], "1581F4XYZ123")
        self.assertAlmostEqual(d["lat"], 33.5, 4)
        self.assertAlmostEqual(d["operator_lon"], -85.31, 4)
        self.assertEqual(d["status"], "airborne")
        self.assertEqual(d["speed_ms"], 10.0)

    def test_ble_service_data(self):
        d = remoteid.from_ble_service_data(bytes([0x0D, 1]) + basic_msg("ABC123"))
        self.assertEqual(d["basic_id"], "ABC123")

    def test_wifi_ie(self):
        raw = bytes([0x0D, 7]) + pack(basic_msg("WIFIDRONE9"), loc_msg(10, 20))
        d = remoteid.from_wifi_vendor_ie(" ".join(f"{b:02x}" for b in raw))
        self.assertEqual(d["basic_id"], "WIFIDRONE9")
        self.assertAlmostEqual(d["lon"], 20, 4)


class RemoteIDEdge(unittest.TestCase):
    def test_unknown_values_filtered(self):
        m = bytearray(loc_msg(10, 20))
        m[3] = 255
        m[15:17] = b"\xff\xff"
        d = remoteid.parse_message(bytes(m))
        self.assertIsNone(d["speed_ms"])
        self.assertIsNone(d["alt_m"])

    def test_speed_multiplier(self):
        m = bytearray(loc_msg(10, 20))
        m[1] |= 1
        m[3] = 100
        self.assertEqual(remoteid.parse_message(bytes(m))["speed_ms"], round(100 * 0.75 + 255 * 0.25, 1))

    def test_malformed_never_raises(self):
        self.assertEqual(remoteid.from_wifi_vendor_ie("0d zz 12"), {})
        self.assertEqual(remoteid.parse_pack(b"\xf2\x19\xff" + b"\x00" * 5), {})
        self.assertEqual(remoteid.from_ble_service_data(b""), {})


class Vendors(unittest.TestCase):
    def test_no_false_camera_for_routers(self):
        for v in ("D-Link Corporation", "TRENDnet, Inc.", "Anker Innovations", "Nest Labs Inc.", "Ubiquiti Inc",
                  "Shenzhen Some Electronic Co", "Hangzhou Random Tech"):
            self.assertNotEqual(oui.classify(v), "camera", v)

    def test_real_cameras_still_match(self):
        self.assertEqual(oui.classify("Hangzhou Hikvision Digital Technology"), "camera")
        self.assertEqual(oui.classify("Zhejiang Dahua Technology"), "camera")
        self.assertEqual(oui.classify("Reolink Innovation"), "camera")

    def test_bssid_with_local_bit_not_called_randomized(self):
        # virtual AP of a real router: first byte has the locally-administered bit set
        real = "28:57:be:00:00:01"
        virt = "2a:57:be:00:00:01"
        if oui.table_size():
            self.assertEqual(oui.vendor(virt, bssid=True), oui.vendor(real, bssid=True))
        self.assertEqual(oui.vendor("12:00:00:00:00:01"), "(randomized MAC)")  # clients still flagged


class BLE(unittest.TestCase):
    def test_airtag_separated(self):
        k, label, _ = det_ble.classify_adv({0x004C: bytes([0x12, 0x19, 0x10] + [0] * 22)}, {}, [])
        self.assertEqual(k, "tracker")

    def test_apple_owner_nearby_is_not_tracker(self):
        k, *_ = det_ble.classify_adv({0x004C: bytes([0x12, 0x02, 0x00, 0x02])}, {}, [])
        self.assertEqual(k, "ambient")

    def test_airpods_not_tracker(self):
        k, *_ = det_ble.classify_adv({0x004C: bytes([0x07, 0x19] + [0] * 20)}, {}, [])
        self.assertIsNone(k)

    def test_tile_smarttag(self):
        self.assertEqual(det_ble.classify_adv({}, {}, ["0000feed-0000-1000-8000-00805f9b34fb"])[0], "tracker")
        self.assertEqual(det_ble.classify_adv({}, {"0000fd5a-0000-1000-8000-00805f9b34fb": b"x"}, [])[0], "tracker")

    def test_remote_id_ble(self):
        k, _, info = det_ble.classify_adv({}, {"0000fffa-0000-1000-8000-00805f9b34fb":
                                               bytes([0x0D, 1]) + basic_msg("DRN1")}, [])
        self.assertEqual((k, info["basic_id"]), ("drone", "DRN1"))


IW = """BSS aa:bb:cc:00:00:01(on wlp1s0) -- associated
\tfreq: 5765
\tsignal: -48.00 dBm
\tSSID: HomeNet
BSS 60:60:1f:11:22:33(on wlp1s0)
\tfreq: 2437
\tsignal: -61.00 dBm
\tSSID: DJI-MAVIC3-ABC
BSS 02:11:22:33:44:55(on wlp1s0)
\tfreq: 2412
\tsignal: -40.00 dBm
\tSSID: HDWifiCam_8F2A
BSS de:ad:be:ef:00:01(on wlp1s0)
\tfreq: 2462
\tsignal: -70.00 dBm
\tSSID: 
\tVendor specific: OUI fa:0b:bc, data: 0d 01 f2 19 01 00 12 41 42 43 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
"""


class Wifi(unittest.TestCase):
    def test_parse_and_detect(self):
        bss = det_wifi.parse_iw(IW)
        self.assertEqual(len(bss), 4)
        self.assertEqual(len(bss[3]["rid_ies"]), 1)
        eng = Engine(DB(":memory:"), quiet=True)
        wd = det_wifi.WifiDetector(eng)
        wd.first_pass = False
        wd.evaluate(bss)
        self.assertEqual(eng.state["drone"]["level"], "alert")
        self.assertEqual(eng.state["network"]["level"], "alert")  # -40 dBm camera AP: very close


class Lan(unittest.TestCase):
    def test_neigh(self):
        t = "192.168.0.1 lladdr 00:11:22:33:44:55 REACHABLE\n192.168.0.9  FAILED\n192.168.0.7 lladdr aa:bb:cc:dd:ee:ff STALE\n"
        self.assertEqual(det_lan.parse_neigh(t), {"192.168.0.1": "00:11:22:33:44:55", "192.168.0.7": "aa:bb:cc:dd:ee:ff"})

    def test_vendor_class(self):
        self.assertEqual(oui.classify("Hangzhou Hikvision Digital Technology"), "camera")
        self.assertEqual(oui.classify("SZ DJI TECHNOLOGY CO.,LTD"), "drone")
        self.assertTrue(oui.is_random("02:11:22:33:44:55"))


class NewDevice(unittest.TestCase):
    def test_chime_once_per_new_device(self):
        eng = Engine(DB(":memory:"), quiet=True)
        calls = []
        eng.notify = lambda t, b, push=None: calls.append((t, b))
        ld = det_lan.LanDetector(eng)
        dev = [("192.168.0.50", "f6:00:00:00:00:01", "(randomized MAC)", "other", {})]
        ld.announce(dev)
        ld.announce(dev)  # same device again within cooldown -> no second chime
        self.assertEqual(len(calls), 1)
        self.assertIn("192.168.0.50", calls[0][1])


class Sdr(unittest.TestCase):
    def test_csv(self):
        csv = "2026-10-03, 10:00:00, 430000000, 440000000, 25000, 4, -60.0, -58.0, -30.5, -61.0\n"
        peak, hz, med = det_sdr.parse_rtl_power(csv)
        self.assertEqual(peak, -30.5)
        self.assertEqual(hz, 430000000 + 2 * 25000)


class Status(unittest.TestCase):
    def test_worst_source_wins(self):
        eng = Engine(DB(":memory:"), quiet=True)
        eng.status("drone", "ok", "a", "ble")
        eng.status("drone", "alert", "b", "wifi")
        eng.status("drone", "ok", "c", "ble")
        self.assertEqual(eng.state["drone"]["level"], "alert")
        eng.status("drone", "ok", "d", "wifi")
        self.assertEqual(eng.state["drone"]["level"], "ok")


if __name__ == "__main__":
    unittest.main()


class WebSecurity(unittest.TestCase):
    def _srv(self, token):
        from homewatch import web
        eng = Engine(DB(":memory:"), quiet=True)
        srv = web.serve(eng, "127.0.0.1", 0, token)
        return eng, srv, srv.server_address[1]

    def _req(self, port, method, path, headers=None):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(method, path, headers=headers or {})
        r = c.getresponse()
        r.read()
        return r.status

    def test_dns_rebinding_host_rejected_in_localhost_mode(self):
        eng, srv, port = self._srv(None)
        self.assertEqual(self._req(port, "GET", "/api/status", {"Host": f"127.0.0.1:{port}"}), 200)
        self.assertEqual(self._req(port, "GET", "/api/status", {"Host": "evil.example.com"}), 401)
        srv.shutdown()

    def test_post_needs_custom_header(self):
        eng, srv, port = self._srv(None)
        self.assertEqual(self._req(port, "POST", "/api/beep"), 403)
        self.assertEqual(self._req(port, "POST", "/api/beep", {"X-Homewatch": "1"}), 200)
        self.assertEqual(len(eng.db.query("SELECT * FROM beeps")), 1)
        srv.shutdown()

    def test_token_rules(self):
        eng, srv, port = self._srv("s3cr3t")
        self.assertEqual(self._req(port, "GET", "/api/status"), 401)
        self.assertEqual(self._req(port, "GET", "/api/status?k=nope"), 401)
        self.assertEqual(self._req(port, "GET", "/api/status?k=s3cr3t"), 200)
        self.assertEqual(self._req(port, "GET", "/api/status", {"Cookie": "hw_k=s3cr3t"}), 200)
        self.assertEqual(self._req(port, "GET", "/api/status", {"Cookie": "x=hw_k=s3cr3t"}), 401)  # no substring match
        srv.shutdown()


class MineFeature(unittest.TestCase):
    def test_own_tracker_does_not_flag(self):
        eng = Engine(DB(":memory:"), quiet=True)
        d = det_ble.BLEDetector(eng)
        now = __import__("time").time()
        d.seen["E9:F5:02:62:C4:B5"] = {"kind": "tracker", "label": "Tile tracker", "first": now - 900, "last": now, "n": 40,
                                       "rssi": -55, "rssi_max": -50, "extra": {}}
        d._evaluate()
        self.assertEqual(eng.state["tracker"]["level"], "alert")          # persistent + close, unknown
        eng.db.kv_set("ble_ignore", ["E9:F5:02:62:C4:B5"])                 # user taps "this is mine"
        d._evaluate()
        self.assertEqual(eng.state["tracker"]["level"], "ok")
        self.assertIn("your own", eng.state["tracker"]["msg"])
        self.assertTrue(eng.live["ble"]["trackers"][0]["mine"])

    def test_mine_api_needs_header_and_valid_address(self):
        from homewatch import web
        import http.client
        eng = Engine(DB(":memory:"), quiet=True)
        srv = web.serve(eng, "127.0.0.1", 0, None)
        port = srv.server_address[1]

        def post(path, hdr=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("POST", path, headers=hdr or {})
            r = c.getresponse(); r.read(); c.close(); return r.status
        h = {"X-Homewatch": "1"}
        self.assertEqual(post("/api/mine?addr=AA:BB:CC:DD:EE:FF&on=1"), 403)               # no header
        self.assertEqual(post("/api/mine?addr=not-an-address&on=1", h), 400)               # validated
        self.assertEqual(post("/api/mine?addr=aa:bb:cc:dd:ee:ff&on=1", h), 200)
        self.assertEqual(eng.db.kv_get("ble_ignore"), ["AA:BB:CC:DD:EE:FF"])
        self.assertEqual(post("/api/mine?addr=AA:BB:CC:DD:EE:FF&on=0", h), 200)
        self.assertEqual(eng.db.kv_get("ble_ignore"), [])
        srv.shutdown(); srv.server_close()

    def test_page_has_banner_night_and_no_flashing_alerts(self):
        from homewatch.web import PAGE
        self.assertIn('id=banner', PAGE); self.assertIn('id=night', PAGE)
        self.assertNotIn("brightness(1.35)", PAGE)                       # old bright pulsing alert is gone


class DeafScannerWatchdog(unittest.TestCase):
    def test_silent_radio_is_never_all_clear(self):
        eng = Engine(DB(":memory:"), quiet=True)
        d = det_ble.BLEDetector(eng)
        now = __import__("time").time()
        d.started = now - 3600
        d.last_ad = now - 400                      # nothing heard for ~7 minutes
        d._evaluate()
        self.assertEqual(eng.state["tracker"]["level"], "watch")
        self.assertEqual(eng.state["drone"]["level"], "watch")
        self.assertIn("NOTHING", eng.state["tracker"]["msg"])
        self.assertTrue(d._restart)                # asks the loop to power-cycle the adapter
        # a reset is attempted at most every 10 minutes
        d._restart = False
        d._evaluate()
        self.assertFalse(d._restart)

    def test_hearing_again_clears_the_warning(self):
        eng = Engine(DB(":memory:"), quiet=True)
        d = det_ble.BLEDetector(eng)
        now = __import__("time").time()
        d.started = now - 3600
        d.last_ad = now - 400
        d._evaluate()
        d.last_ad = now                            # ads are back
        d._evaluate()
        self.assertEqual(eng.state["tracker"]["level"], "ok")
        self.assertEqual(eng.state["drone"]["level"], "ok")


class HostNoise(unittest.TestCase):
    def test_port_classes(self):
        from homewatch import det_host as h
        self.assertEqual(h.port_class("tcp 127.0.0.1:5037 adb"), "info")           # adb server, loopback only
        self.assertEqual(h.port_class("udp 224.0.0.251:5353 chrome"), "info")      # mDNS
        self.assertEqual(h.port_class("udp *:5353 adb"), "info")
        self.assertEqual(h.port_class("udp [::]:3702 ?"), "info")                  # WS-Discovery
        self.assertEqual(h.port_class("tcp 0.0.0.0:8080 python"), "alert")         # reachable from the network
        self.assertEqual(h.port_class("tcp *:22 sshd"), "alert")

    def _host(self, ports, usb):
        from homewatch import det_host as h
        eng = Engine(DB(":memory:"), quiet=True)
        det = h.HostDetector(eng)
        h.listening = lambda: set(ports)
        h.usb_devices = lambda: set(usb)
        h.fd_users = lambda pats: {}
        h.audio_recorders = lambda: []
        return h, eng, det

    def test_harmless_new_port_is_logged_once_then_normal(self):
        h, eng, det = self._host({"tcp 0.0.0.0:631 cupsd"}, {"hub"})
        det.check()                                                 # first run learns the baseline
        h.listening = lambda: {"tcp 0.0.0.0:631 cupsd", "tcp 127.0.0.1:5037 adb"}
        det.check()
        self.assertEqual(eng.state["host"]["level"], "ok")
        n = len(eng.db.query("SELECT * FROM events WHERE kind='hostport'"))
        det.check()
        self.assertEqual(len(eng.db.query("SELECT * FROM events WHERE kind='hostport'")), n)   # not repeated every hour

    def test_reachable_new_port_stays_red_until_approved(self):
        h, eng, det = self._host({"tcp 0.0.0.0:631 cupsd"}, {"hub"})
        det.check()
        h.listening = lambda: {"tcp 0.0.0.0:631 cupsd", "tcp 0.0.0.0:4444 nc"}
        det.check(); det.check()
        self.assertEqual(eng.state["host"]["level"], "alert")
        self.assertIn("4444", eng.state["host"]["msg"])

    def test_new_usb_is_amber_then_accepted(self):
        import time as _t
        h, eng, det = self._host({"tcp 0.0.0.0:631 cupsd"}, {"hub"})
        det.check()
        h.usb_devices = lambda: {"hub", "ID 1bbb:0167 Phone"}
        det.check()
        self.assertEqual(eng.state["host"]["level"], "watch")
        det.usb_pending["ID 1bbb:0167 Phone"] = _t.time() - 1       # 10 minutes later
        det.check()
        self.assertEqual(eng.state["host"]["level"], "ok")
        self.assertEqual(len(eng.db.query("SELECT * FROM events WHERE kind='usb'")), 1)


class Privacy(unittest.TestCase):
    def test_operator_position_not_stored(self):
        eng = Engine(DB(":memory:"), quiet=True)
        wd = det_wifi.WifiDetector(eng)
        wd.first_pass = False
        raw = bytes([0x0D, 1]) + pack(basic_msg("D1"), loc_msg(33.1, -85.1), sys_msg(33.2, -85.2))
        ie = " ".join(f"{b:02x}" for b in raw)
        wd.evaluate([{"bssid": "de:ad:be:ef:00:01", "ssid": "", "signal": -60.0, "freq": 2412,
                      "rid_ies": [ie], "seen_ms": 0}])
        rows = eng.db.query("SELECT msg, detail FROM events WHERE kind='wifi_drone'")
        self.assertTrue(rows)
        blob = rows[0]["msg"] + rows[0]["detail"]
        self.assertNotIn("33.2", blob)
        self.assertNotIn("-85.2", blob)
        self.assertIn("operator", eng.state["drone"]["msg"])  # still shown live
        self.assertIn("CLAIMS", rows[0]["msg"])


def test_port_class_virtual_bridge_and_mdns_are_info():
    from homewatch.det_host import port_class
    assert port_class("tcp [fe80::60cc:c6ff:fed2:caf9]%pan1:53 ?") == "info"
    assert port_class("udp 224.0.0.251:5353 chrome") == "info"
    assert port_class("udp 0.0.0.0:5353 adb") == "info"
    assert port_class("tcp 0.0.0.0:8080 python") == "alert"
    assert port_class("tcp [fe80::1]%wlp1s0:53 ?") == "alert"


def test_port_class_ipv4_mapped_loopback_is_info():
    from homewatch.det_host import port_class
    assert port_class("tcp [::ffff:127.0.0.1]:44131 java") == "info"
    assert port_class("tcp [::ffff:192.168.0.5]:8080 java") == "alert"
