import unittest

from n0rma import evidence, inspection, smart, tscm


class SmartTest(unittest.TestCase):
    def test_groups_by_name(self):
        self.assertEqual(smart.classify("Echo Dot-4TQ"), "amazon")
        self.assertEqual(smart.classify("Ring-a1b2c3"), "amazon")
        self.assertEqual(smart.classify("Nest-Hub-93"), "google")
        self.assertEqual(smart.classify("Wyze_Cam_V3"), "camera")
        self.assertEqual(smart.classify("ESP_1A2B3C"), "iot")
        self.assertEqual(smart.classify("whatever", klass="camera"), "camera")

    def test_ordinary_names_unclassified(self):
        for n in ("HAL9000", "NeighborNet", "HP-Print-A4-ENVY 5530 series", ""):
            self.assertIsNone(smart.classify(n))

    def test_group_live_sorts_strongest_first(self):
        live = {"wifi": [{"ssid": "Echo A", "bssid": "aa", "signal": -80}, {"ssid": "Echo B", "bssid": "bb", "signal": -50}, {"ssid": "Plain", "bssid": "cc", "signal": -40}],
                "ble": {"trackers": [{"label": "Tile tracker", "addr": "X", "rssi": -60}], "drones": []}}
        g = smart.group_live(live)
        self.assertEqual([r["title"] for r in g["amazon"]], ["Echo B", "Echo A"])
        self.assertNotIn("iot", g)


class InspectionTest(unittest.TestCase):
    def test_car_and_rooms(self):
        self.assertTrue({"obd", "under"} <= {i[0] for i in inspection.items_for("Car")})
        self.assertNotIn("ceil", {i[0] for i in inspection.items_for("Car")})
        self.assertIn("bed", {i[0] for i in inspection.items_for("Master Bedroom")})
        self.assertNotIn("bed", {i[0] for i in inspection.items_for("Kitchen")})

    def test_ids_unique(self):
        for r in ("Car", "Bedroom", "Bathroom", "Hotel room", "Kitchen"):
            ids = [i[0] for i in inspection.items_for(r)]
            self.assertEqual(len(ids), len(set(ids)), r)

    def test_progress_ignores_unknown_ids(self):
        self.assertEqual(inspection.progress("Kitchen", {"ceil", "outlets", "nope"})[0], 2)


class SweepReportTest(unittest.TestCase):
    EV = [{"ts": 1_700_000_000, "domain": "camera", "level": "watch", "msg": "Camera-like source"}]

    def _report(self, ev=()):
        return evidence.build(list(ev), 1_700_000_100_000, tscm.TITLE, tscm.sections({"Bedroom": {"ceil", "outlets"}, "Garage": set()}, list(ev), 2))

    def test_lists_what_was_and_was_not_done(self):
        r = self._report()
        self.assertIn("Bedroom: 2 of ", r)
        self.assertEqual(r.count("NOT CHECKED: Ceiling"), 1)   # only the Garage
        self.assertIn("METHODS NOT PERFORMED", r)
        self.assertIn("Non-linear junction", r)

    def test_never_says_clear(self):
        r = self._report()
        self.assertIn("does NOT show the area is free", r)
        self.assertNotIn("all clear", r.lower())
        self.assertNotIn("area is clear", r)

    def test_flagged_counted(self):
        r = self._report(self.EV)
        self.assertIn("1 camera", r)
        self.assertIn("not proof of surveillance", r)

    def test_chain_verifies_and_catches_scope_edits(self):
        r = self._report()
        self.assertTrue(evidence.verify(r))
        self.assertFalse(evidence.verify(r.replace("Garage: 0 of", "Garage: 9 of")))

    def test_plain_evidence_report_unchanged(self):
        self.assertTrue(evidence.verify(evidence.build([], 1_700_000_100_000)))


if __name__ == "__main__":
    unittest.main()
