import unittest

from n0rma import det_host


class PortClassTest(unittest.TestCase):
    def test_tailscale_ports_are_info(self):
        self.assertEqual(det_host.port_class("tcp 100.118.105.60%tailscale0:57753 tailscaled"), "info")
        self.assertEqual(det_host.port_class("tcp [fd7a:115c:a1e0::7601:69dd]%tailscale0:52642 tailscaled"), "info")

    def test_real_lan_ports_still_alert(self):
        self.assertEqual(det_host.port_class("tcp 192.168.1.20:8080 python3"), "alert")
        self.assertEqual(det_host.port_class("tcp 0.0.0.0:80 nginx"), "alert")
        self.assertEqual(det_host.port_class("tcp 192.168.1.20%wlan0:2222 sshd"), "alert")

    def test_loopback_and_virtual_bridges_are_info(self):
        self.assertEqual(det_host.port_class("tcp 127.0.0.1:8777 n0rma"), "info")
        self.assertEqual(det_host.port_class("udp 0.0.0.0%pan1:67 dnsmasq"), "info")


if __name__ == "__main__":
    unittest.main()
