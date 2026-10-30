import sys, unittest, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import session_counts as sc

T0 = dt.datetime(2026, 10, 16, 16, 26, 41, tzinfo=sc.PT)
T1 = dt.datetime(2026, 10, 16, 16, 40, tzinfo=sc.PT)


class SessionCounts(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(sc.parse_followers({"data": {"public_metrics": {"followers_count": 12345}}}), 12345)
        self.assertIsNone(sc.parse_followers({"errors": []}))

    def test_format(self):
        self.assertEqual(sc.fmt_count(12345), "12,345")
        self.assertEqual(sc.fmt_count(None), "Not available")
        self.assertEqual(sc.fmt_time(T0), "Oct 16, 4:26 PM PT")
        self.assertEqual(sc.fmt_time(dt.datetime(2026, 10, 16, 0, 5, tzinfo=sc.PT)), "Oct 16, 12:05 AM PT")

    def test_start_message(self):
        r = sc.start_record("example_owner", "example_owner", 12345, T0)
        self.assertEqual(sc.start_message(r, T0), "Your follower count at the start of this session: 12,345 (as of Oct 16, 4:26 PM PT).")
        self.assertEqual(r["handle"], "@example_owner")

    def test_end_summary(self):
        s = sc.end_summary(sc.start_record("u", "x", 12345, T0), 10, 12337, T1)
        self.assertTrue(s["message"].startswith("Removed this session: 10\n"))
        self.assertIn("12,337", s["message"]); self.assertIn("may not equal", s["message"])
        self.assertEqual(s["net_change"], -8); self.assertFalse(s["matches_removed"])
        self.assertIn("removed this session (verified): 10", sc.batch_log_note(s))

    def test_missing_counts(self):
        s = sc.end_summary(sc.start_record("u", "x", None, T0), 2, None, T1)
        self.assertIsNone(s["net_change"]); self.assertIn("Not available", s["message"])
