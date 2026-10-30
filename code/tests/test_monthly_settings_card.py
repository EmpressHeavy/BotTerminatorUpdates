import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import build_monthly_settings_card as m

class T(unittest.TestCase):
    def test_no_cleanup(self):
        for pc in (None, {}, {"skipped": True, "last_purge_tool": "X"}, {"last_purge_date": None}):
            c = m.build(pc); self.assertEqual(c["buttons"][4], "6\u20137. Pacing, reminders and connectors")
            self.assertEqual(len(c["extra_companion_lines"]), 2); self.assertIn("Terminate reminder (chat nudge): OFF", c["extra_companion_lines"][0]); self.assertIn("Memory backup: OFF (default)", c["extra_companion_lines"][1])  # v3.3.0; self.assertEqual(len(c["settings"]), 7)
    def test_with_cleanup(self):
        c = m.build({"last_purge_date": "2026-01-15", "last_purge_tool": "ExampleCleanupTool"})
        self.assertEqual(len(c["buttons"]), 6); self.assertTrue(c["buttons"][4].startswith("6\u20138."))
        self.assertEqual(c["extra_companion_lines"][0], "8. Last bot cleanup: 2026-01-15 (ExampleCleanupTool). Your first scans covered followers since then.")
        self.assertEqual(c["buttons"][-1], "Keep everything as-is"); self.assertNotIn("Select all", " ".join(c["buttons"]))
    def test_tool_only(self):
        self.assertIn("date not given (ExampleCleanupTool)", m.last_cleanup_line({"last_purge_tool": "ExampleCleanupTool"}))
