import sys, unittest, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import json, tempfile
import record_chat_selection as rcs
from record_chat_selection import parse_answer, build, PT

C1 = [1, 2, 3, 4, 5]
UK = "example_owner"  # neutral placeholder user
_TD = None


def setUpModule():
    """Self-contained per-user fixture: data/users/example_owner/{config.json, snapshots/fx_cards}."""
    global _TD
    _TD = tempfile.TemporaryDirectory()
    root = Path(_TD.name)
    u = root / "data/users" / UK
    (u / "snapshots/fx_cards").mkdir(parents=True)
    json.dump({"user_key": UK, "owner_x_handle": "@example_owner"}, open(u / "config.json", "w"))
    accts = [{"chat_no": n, "card": (n - 1) // 5 + 1, "handle": f"h{n}", "user_id": str(n), "name": f"N{n}",
              "review_id": f"BT-FX-{n:03d}", "label": "REVIEW", "tab": "In review" if n <= 10 else "Keepers",
              "sheet_row": n + 3} for n in range(1, 16)]
    json.dump({"snapshot_id": "fx_cards", "batch_id": "FX", "accounts": accts}, open(u / "snapshots/fx_cards/chat_numbering.json", "w"))
    rcs._orig_root = rcs.ROOT
    rcs.ROOT = root


def tearDownModule():
    rcs.ROOT = rcs._orig_root
    _TD.cleanup()


class ParseTests(unittest.TestCase):
    def test_list(self):
        self.assertEqual(parse_answer(["1", "3"], C1), ([1, 3], "card"))
        self.assertEqual(parse_answer(["mark_all"], C1), (C1, "Select all"))

    def test_select_all(self):
        self.assertEqual(parse_answer("Select all", C1), (C1, "Select all"))
        self.assertEqual(parse_answer("Select all on card 1 (1-5)", C1), (C1, "Select all"))

    def test_mark_all_label(self):
        self.assertEqual(parse_answer("Mark all for termination", C1), (C1, "Select all"))
        self.assertEqual(parse_answer("Select all \u2014 mark for termination", C1), (C1, "Select all"))
        self.assertEqual(parse_answer("Select all on card 1 (1-5)", C1), (C1, "Select all"))
        self.assertEqual(parse_answer("mark all except 3", C1)[0], [1, 2, 4, 5])

    def test_everyone_except(self):
        self.assertEqual(parse_answer("everyone except 3", C1), ([1, 2, 4, 5], "typed 'everyone except'"))
        self.assertEqual(parse_answer("all but 2 and 4", C1)[0], [1, 3, 5])

    def test_range(self):
        self.assertEqual(parse_answer("1-3", C1)[0], [1, 2, 3])

    def test_off_card_numbers_ignored(self):
        self.assertEqual(parse_answer("4, 7, 9", C1)[0], [4])
        self.assertEqual(parse_answer("6, 9", [6, 7, 8, 9, 10])[0], [6, 9])

    def test_none_and_words(self):
        self.assertEqual(parse_answer("none", C1)[0], [])
        self.assertEqual(parse_answer("one and three", C1)[0], [1, 3])


class BuildTests(unittest.TestCase):
    def test_build_dry(self):
        r = build("fx_cards", 1, C1, "1, 3", keep=[2], now=dt.datetime(2026, 10, 16, 16, 0, tzinfo=PT), user_key=UK)
        self.assertEqual(len(r["chat_rows"]), 5)
        a_writes = {o["cells"]: o["values"][0][0] for o in r["sheet_ops"] if o.get("cells", "").startswith("A")}
        self.assertEqual(a_writes, {"A4": "Terminate", "A6": "Terminate", "A5": "Keep"})
        self.assertNotIn("A7", a_writes)  # unselected, no Keep -> left blank
        self.assertEqual(r["history_entry"]["status"], "CHAT_SELECTION")
        self.assertFalse(r["history_entry"]["bot_terminator_executed"])
        self.assertEqual(r["history_entry"]["owner_x_handle"], "@example_owner")
        self.assertEqual(r["history_entry"]["user_key"], UK)

    def test_requires_user_key(self):
        with self.assertRaises(TypeError):
            build("fx_cards", 1, C1, "1")
        with self.assertRaises(ValueError):
            build("fx_cards", 1, C1, "1", user_key="")

    def test_keepers_card_no_column_a(self):
        r = build("fx_cards", 3, [11, 12, 13, 14, 15], "Select all", user_key=UK)
        self.assertEqual([o for o in r["sheet_ops"] if o["tool"] == "write_range"], [])
        self.assertEqual(r["selected"], [11, 12, 13, 14, 15])


if __name__ == "__main__":
    unittest.main()


class Amendment20261016(unittest.TestCase):
    """2026-10-16 ~4:05 PM PT: Select all authorizes; final review card for unselected."""
    def test_select_all_authorized(self):
        r = build("fx_cards", 1, C1, "Select all", now=dt.datetime(2026, 10, 16, 16, 5, tzinfo=PT), user_key=UK)
        self.assertTrue(all(row[11].startswith("Authorized: Select all") for row in r["chat_rows"]))
        self.assertTrue(r["history_entry"]["authorization"].startswith("SELECT_ALL_OWNER_YES"))

    def test_individual_awaits_and_rest_held(self):
        r = build("fx_cards", 1, C1, "1, 3", now=dt.datetime(2026, 10, 16, 16, 5, tzinfo=PT), user_key=UK)
        self.assertTrue(r["chat_rows"][0][11].startswith("Authorized: selected + done"))
        self.assertTrue(r["history_entry"]["authorization"].startswith("SELECTED_OWNER_YES"))
        m = build("fx_cards", 1, C1, "1, 3", now=dt.datetime(2026, 10, 16, 16, 6, tzinfo=PT), mode="manual", user_key=UK)
        self.assertEqual(m["chat_rows"][0][11], "Selected, awaiting confirmation")
        self.assertEqual(r["chat_rows"][1][11], "Held for final review card")
        self.assertEqual(r["history_entry"]["held_for_final_review"], [2, 4, 5])

    def test_final_review(self):
        from record_chat_selection import build_final_review
        r = build_final_review("fx_cards", [2, 4, 5], "Always Keep 2; 4 not a bot; rest leave",
                               now=dt.datetime(2026, 10, 16, 16, 5, tzinfo=PT), user_key=UK)
        self.assertEqual(r["decisions"], {2: "ALWAYS_KEEP", 4: "NOT_A_BOT", 5: "LEAVE"})
        self.assertEqual(len(r["always_keep_add"]), 1)
        self.assertEqual(r["sheet_ops"][0]["sheet"], "Actions")
        self.assertEqual(sum(1 for o in r["sheet_ops"] if o["tool"] == "keepers_add"), 2)
        self.assertEqual(r["history_entry"]["status"], "CHAT_FINAL_REVIEW")
