from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_snapshot import candidate_from_raw, relationship_evidence  # noqa: E402
from classify import stage1_screen  # noqa: E402

BASE = {"id": "123", "handle": "@someone", "display_name": "Some One"}


class FollowRelationshipSignal(unittest.TestCase):
    def test_follow_back_means_not_followed(self):
        rec = {**BASE, "button": "Follow back"}
        self.assertEqual(relationship_evidence(rec), (False, "browser_follow_back_button"))
        c = candidate_from_raw(rec)
        self.assertFalse(c.followed_by_me)
        self.assertEqual(c.follow_relationship_source, "browser_follow_back_button")
        r = stage1_screen(c)
        self.assertNotEqual(r.get("label"), "PROTECTED / DO NOT REMOVE")
        self.assertIn("You follow: No (source: browser_follow_back_button)", r["signals"])

    def test_following_means_protected(self):
        c = candidate_from_raw({**BASE, "button": "Following"})
        self.assertTrue(c.followed_by_me)
        self.assertEqual(c.follow_relationship_source, "browser_following_button")
        self.assertEqual(stage1_screen(c).get("label"), "PROTECTED / DO NOT REMOVE")

    def test_api_overrides_button(self):
        rec = {**BASE, "button": "Follow back", "connection_status": ["following", "followed_by"]}
        self.assertEqual(relationship_evidence(rec), (True, "api_connection_status"))
        rec2 = {**BASE, "button": "Following", "connection_status": ["followed_by"]}
        self.assertEqual(relationship_evidence(rec2), (False, "api_connection_status"))

    def test_neither_not_available_still_escalates(self):
        c = candidate_from_raw(dict(BASE))
        self.assertEqual(c.follow_relationship_source, "not_available")
        self.assertFalse(c.followed_by_me)
        r = stage1_screen(c)
        self.assertTrue(r["escalate"])
        self.assertIn("You follow: Not available (relationship evidence missing)", r["signals"])


if __name__ == "__main__":
    unittest.main()
