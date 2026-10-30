import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import automatic_policy as ap
import product_config as pc

FAM = ["@example_family"]  # neutral placeholder for a user's private protected handle
BOT = ["Unverified", "You follow: No", "Sparse/incomplete profile", "Very high repost ratio", "Almost no conversational activity"]


class Defaults(unittest.TestCase):
    def test_flag_and_default(self):
        self.assertTrue(pc.AUTOMATIC_MODE_ENABLED)
        self.assertEqual(pc.default_user_config("x").operating_mode, pc.OperatingMode.AUTOMATIC)
        self.assertEqual(ap.DEFAULT_MODE, ap.AUTOMATIC)
        self.assertEqual(pc.load_user_config("config/default_user_config.json").operating_mode, pc.OperatingMode.AUTOMATIC)


class Decide(unittest.TestCase):
    def test_bot_selected_auto(self):
        r = ap.decide(ap.Account("b", "BOT-LIKE", BOT), True, ap.AUTOMATIC, "u")
        self.assertEqual(r["action"], "AUTO_REMOVE"); self.assertTrue(r["authorized"])

    def test_bot_plus_inactive_auto(self):
        self.assertEqual(ap.decide(ap.Account("b", "BOT-LIKE + INACTIVE", BOT), True, ap.AUTOMATIC, "u")["action"], "AUTO_REMOVE")

    # Superseded 2026-10-16 ~4:06 PM PT: weak-signal / inactive-only / needs-look selections are now authorized
    # in Automatic Mode; they still await confirmation in Manual mode.
    def test_weak_or_needs_look_selected_auto_vs_manual(self):
        for lab, sig in (("BOT-LIKE", ["Unverified", "You follow: No"]), ("BOT-LIKE", ["Unverified", "Very high repost ratio"]),
                         ("INACTIVE", ["Unverified", "Inactive 200 days", "Zero posts"]), ("REVIEW", BOT)):
            self.assertTrue(ap.decide(ap.Account("x", lab, sig), True, ap.AUTOMATIC, "u")["authorized"])
            r = ap.decide(ap.Account("x", lab, sig), True, ap.MANUAL, "u")
            self.assertEqual(r["status"], "Selected, awaiting confirmation")

    def test_protections_win_even_if_selected(self):
        for a in (ap.Account("v", "BOT-LIKE", BOT, verified_type="blue"), ap.Account("f", "BOT-LIKE", BOT, i_follow=True),
                  ap.Account("k", "BOT-LIKE", BOT, always_keep=True)):
            self.assertEqual(ap.decide(a, True, ap.AUTOMATIC, "u")["action"], "PROTECTED_SKIP")
        self.assertEqual(ap.decide(ap.Account("@example_family", "BOT-LIKE", BOT), True, ap.AUTOMATIC, "example_owner", protected_handles=FAM)["action"], "PROTECTED_SKIP")
        self.assertEqual(ap.decide(ap.Account("example_family", "BOT-LIKE", BOT), True, ap.AUTOMATIC, "other_user")["action"], "AUTO_REMOVE")  # per-user
        self.assertFalse(ap.recheck_at_execution(ap.Account("z", "BOT-LIKE", BOT, i_follow=True), "u"))

    def test_unselected_deferred_to_final_review(self):
        r = ap.decide(ap.Account("b", "BOT-LIKE", BOT), False, ap.AUTOMATIC, "u")
        self.assertEqual(r["action"], "DEFER_FINAL_REVIEW")

    def test_select_all_authorizes_needs_look_and_inactive(self):
        for lab in ("REVIEW", "INACTIVE"):
            r = ap.decide(ap.Account("n", lab, []), True, ap.AUTOMATIC, "u", via_select_all=True)
            self.assertEqual(r["action"], "AUTO_REMOVE"); self.assertEqual(r["basis"], "select_all_owner_yes")

    def test_select_all_still_protected(self):
        for a in (ap.Account("v", "REVIEW", [], verified_type="blue"), ap.Account("f", "REVIEW", [], i_follow=True),
                  ap.Account("k", "REVIEW", [], always_keep=True), ap.Account("example_family", "REVIEW", [])):
            self.assertEqual(ap.decide(a, True, ap.AUTOMATIC, "example_owner", via_select_all=True, protected_handles=FAM)["action"], "PROTECTED_SKIP")

    def test_individual_needs_look_and_inactive_authorized(self):
        for lab, sig in (("REVIEW", BOT), ("INACTIVE", []), ("BOT-LIKE", ["Unverified"])):
            r = ap.decide(ap.Account("n", lab, sig), True, ap.AUTOMATIC, "u")
            self.assertEqual(r["action"], "AUTO_REMOVE"); self.assertEqual(r["basis"], "selected_owner_yes")

    def test_individual_pick_protections(self):
        self.assertEqual(ap.decide(ap.Account("example_family", "INACTIVE", []), True, ap.AUTOMATIC, "example_owner", protected_handles=FAM)["action"], "PROTECTED_SKIP")

    def test_execution_pauses_on_warning(self):
        self.assertIn("rate_limit", ap.EXECUTION["stop_on"]); self.assertIn("x_warning", ap.EXECUTION["stop_on"])

    def test_final_review_buttons_and_typed(self):
        self.assertEqual(ap.parse_final_review("Add all to Always Keep", [6, 7]), {6: "ALWAYS_KEEP", 7: "ALWAYS_KEEP"})
        self.assertEqual(ap.parse_final_review("Mark all as not a bot (Keep)", [6]), {6: "NOT_A_BOT"})
        self.assertEqual(ap.parse_final_review("Always Keep 11, 13; rest leave", [11, 12, 13, 14]),
                         {11: "ALWAYS_KEEP", 12: "LEAVE", 13: "ALWAYS_KEEP", 14: "LEAVE"})
        self.assertEqual(ap.parse_final_review("keep 12; always keep 11", [11, 12, 13]),
                         {11: "ALWAYS_KEEP", 12: "NOT_A_BOT", 13: "LEAVE"})
        m = ap.final_review_mapping({1: "ALWAYS_KEEP", 2: "NOT_A_BOT", 3: "LEAVE"})
        self.assertTrue(m[1]["add_to_always_keep_list"]); self.assertEqual(m[2]["sheet"], "Keepers"); self.assertIsNone(m[3]["sheet"])

    def test_collect_and_message(self):
        cards = [{"accounts": [{"chat_no": 1, "handle": "a"}, {"chat_no": 2, "handle": "b", "reason": "Needs your look"}], "selected": [1]},
                 {"accounts": [{"chat_no": 6, "handle": "c"}], "selected": []}]
        u = ap.collect_unselected(cards)
        self.assertEqual([a["chat_no"] for a in u], [2, 6])
        msg = ap.final_review_message(u)
        self.assertTrue(msg.startswith("I noticed you didn't select these 2 accounts. What do you want me to do with them?"))
        self.assertIn("https://x.com/b", msg); self.assertIn("Needs your look", msg)

    def test_manual_never_auto(self):
        self.assertEqual(ap.decide(ap.Account("b", "BOT-LIKE", BOT), True, ap.MANUAL, "u")["action"], "AWAIT_CONFIRMATION")

    def test_execution_policy(self):
        self.assertEqual(ap.EXECUTION["spacing_seconds"], 10); self.assertFalse(ap.EXECUTION["block"])
        self.assertIn("rate_limit", ap.EXECUTION["stop_on"])


class Modes(unittest.TestCase):
    def test_switch_logged_and_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            s = ap.ModeStore(Path(d))
            self.assertEqual(s.get("a"), ap.AUTOMATIC)
            r = s.switch("a", ap.MANUAL, by="a")
            self.assertEqual(s.get("a"), ap.MANUAL); self.assertEqual(s.get("b"), ap.AUTOMATIC)
            self.assertEqual(r["log"][-1]["applies_to"], "future cards only")


if __name__ == "__main__":
    unittest.main()


class PerUserConfigProtections(unittest.TestCase):
    """protected_handles come only from the user's own config (isolation fix 2026-10-16)."""
    def test_loaded_from_own_config_only(self):
        import json, storage
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "data/users/example_owner"; d.mkdir(parents=True)
            json.dump({"user_key": "example_owner", "owner_x_handle": "@example_owner",
                       "protected_handles": ["example_family"]}, open(d / "config.json", "w"))
            self.assertEqual(ap.protected_handles_for("example_owner", td), {"example_family"})
            self.assertEqual(ap.protected_handles_for("example_friend", td), set())
            with self.assertRaises(ValueError):
                ap.protected_handles_for("", td)

    def test_no_hardcoded_table(self):
        self.assertFalse(hasattr(ap, "PER_USER_PROTECTED_HANDLES"))
        self.assertFalse(hasattr(pc, "HIDE_VERIFIED_FORCED_USER_KEYS"))
        cfg = pc.default_user_config("example_owner"); cfg.HIDE_VERIFIED_FROM_REVIEW_QUEUE = False
        self.assertFalse(pc.hide_verified_from_review_queue(cfg))
        cfg.hide_verified_forced = True
        self.assertTrue(pc.hide_verified_from_review_queue(cfg))
