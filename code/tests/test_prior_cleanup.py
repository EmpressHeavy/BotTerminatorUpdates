import json, sys, unittest, datetime as dt, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import product_config as pc
R = os.path.join(os.path.dirname(__file__), "..", "config")

class T(unittest.TestCase):
    def test_count_diff(self):
        r = pc.first_scan_window(12403, 10000); self.assertEqual((r["method"], r["estimate"]), ("count difference", 2403))
    def test_growth(self):
        r = pc.first_scan_window(5000, None, "2026-10-06", 2.0, today=dt.date(2026, 10, 16)); self.assertEqual(r["estimate"], 20)
    def test_unknown(self):
        r = pc.first_scan_window(12403); self.assertIsNone(r["estimate"]); self.assertEqual(r["scan_mode"], "backlog")
    def test_never_and_large(self):
        self.assertIn("recent batches", pc.first_scan_window(500, ever_cleaned=False)["method"])
        self.assertIn("recent batches", pc.first_scan_window(150000, 100000)["method"])
    def test_mode_switch(self):
        self.assertEqual(pc.next_scan_mode(True), "maintenance"); self.assertEqual(pc.next_scan_mode(False), "backlog")
    def test_configs(self):
        d = json.load(open(f"{R}/default_user_config.json"))["prior_cleanup"]
        for f in pc.PRIOR_CLEANUP_SETUP_FIELDS: self.assertIn(f, d)
        self.assertIn(d["scan_mode"], pc.SCAN_MODES)
        # Per-user configs (any present) must carry the same setup fields; no user's values are asserted here.
        import glob
        for f in glob.glob(f"{R}/dev_user_*.json"):
            e = json.load(open(f)).get("prior_cleanup") or {}
            for k in pc.PRIOR_CLEANUP_SETUP_FIELDS: self.assertIn(k, e)

class Optional(unittest.TestCase):
    def test_optional_flags(self):
        self.assertTrue(pc.PRIOR_CLEANUP_OPTIONAL); self.assertEqual(pc.PRIOR_CLEANUP_SKIP_ANSWER, "Skip / never done one")
        import glob
        for f in [f"{R}/default_user_config.json"] + glob.glob(f"{R}/dev_user_*.json"):
            b = json.load(open(f))["prior_cleanup"]; self.assertTrue(b["optional"]); self.assertIn("skip_answer", b)
    def test_skipped_starts_recent(self):
        r = pc.first_scan_window(12403, 10000, skipped=True)
        self.assertIn("recent batches", r["method"]); self.assertEqual(r["scan_mode"], "backlog")
