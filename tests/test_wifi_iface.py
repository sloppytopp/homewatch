import unittest

from n0rma import det_wifi

IW_DEV = """phy#0
\tInterface phy0.mon
\t\tifindex 7
\t\twdev 0x2
\t\taddr 0c:cd:b4:16:9f:a7
\t\ttype monitor
\t\ttxpower 20.00 dBm
\tInterface wlp1s0
\t\tifindex 3
\t\twdev 0x1
\t\taddr 0c:cd:b4:16:9f:a6
\t\tssid Dozer26
\t\ttype managed
\t\tchannel 9 (2452 MHz), width: 20 MHz
"""

NMCLI = r"""Dozer26:10\:5A\:95\:39\:EF\:88:100:2452 MHz
HP-Print-A4-ENVY 5530 series:64\:51\:06\:68\:16\:A4:87:2452 MHz
:D6\:E2\:2F\:B6\:20\:10:65:5765 MHz
"""


class IfaceTest(unittest.TestCase):
    def test_skips_the_monitor_interface(self):
        self.assertEqual(det_wifi.pick_iface(det_wifi.parse_iw_dev(IW_DEV)), "wlp1s0")

    def test_no_managed_interface(self):
        self.assertIsNone(det_wifi.pick_iface([{"name": "x.mon", "type": "monitor", "ssid": ""}]))

    def test_prefers_the_connected_one(self):
        ifs = [{"name": "wlan1", "type": "managed", "ssid": ""}, {"name": "wlan0", "type": "managed", "ssid": "Home"}]
        self.assertEqual(det_wifi.pick_iface(ifs), "wlan0")

    def test_nmcli_parse(self):
        r = det_wifi.parse_nmcli(NMCLI)
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0]["bssid"], "10:5a:95:39:ef:88")
        self.assertEqual(r[0]["ssid"], "Dozer26")
        self.assertAlmostEqual(r[0]["signal"], -50.0)
        self.assertEqual(r[2]["ssid"], "")


if __name__ == "__main__":
    unittest.main()
