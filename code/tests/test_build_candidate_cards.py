import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from build_candidate_cards import build_cards

def A(h, uid, label="REVIEW", **kw):
    return dict(handle=h, user_id=uid, label=label, verified_type="none", i_follow=False, **kw)


class Cards(unittest.TestCase):
    def test_keepers_never_appear(self):
        accts = [A("bot1", "1", "BOT-LIKE"), A("Sample_Keeper", "1000000901"), A("x", "1000000902")]
        r = build_cards(accts, keepers=[{"handle": "@sample_keeper", "user_id": "9"}, {"handle": "@other", "user_id": "'1000000902"}])
        self.assertEqual([a["handle"] for a in r["accounts"]], ["bot1"])
        self.assertEqual({e["reason"] for e in r["excluded"]}, {"in Keepers"})  # sheet tabs renamed Actions / Keepers / In review (2026-10-20)

    def test_keep_classification_never_appears(self):
        r = build_cards([A("k", "2", "KEEP"), A("p", "3", "PROTECTED"), A("n", "4", "REVIEW")])
        self.assertEqual([a["handle"] for a in r["accounts"]], ["n"])

    def test_unverified_alone_not_candidate(self):
        self.assertEqual(build_cards([A("u", "5", "KEEP")])["accounts"], [])

    def test_other_exclusions(self):
        accts = [dict(A("f", "6"), i_follow=True), dict(A("v", "7"), verified_type="blue"), A("g", "8"), A("p", "9"),
                 A("ak", "10"), A("ok", "11", "INACTIVE"), A("nq", "12", "BOT-LIKE")]
        r = build_cards(accts, graveyard=["@g"], protected=[{"user_id": "9"}], always_keep=["ak"], queue_ids={"11"})
        self.assertEqual([a["handle"] for a in r["accounts"]], ["ok"])

    def test_numbering_and_cards(self):
        r = build_cards([A(f"b{i}", str(i), "BOT-LIKE") for i in range(7)])
        self.assertEqual(r["cards"], {"1": [1, 2, 3, 4, 5], "2": [6, 7]})

    def test_live_snapshot_excludes_card3_keepers(self):
        import csv, json
        root = Path(__file__).resolve().parents[1]
        cands = json.load(open(root / "tests/fixtures/sample_scan.json"))["card_snapshot"]["candidates"]
        accts = [dict(c, handle=c["username"]) for c in cands]
        r = build_cards(accts)
        handles = {a["handle"].lower() for a in r["accounts"]}
        self.assertEqual(len(r["accounts"]), 10)  # exactly the 10 In review candidates 001-010
        for h in ("sample_user_18", "sample_user_19", "sample_user_20", "sample_user_21", "sample_user_22"):  # the 5 card-3 keepers
            self.assertNotIn(h, handles)


class CardUI(unittest.TestCase):
    def test_select_all_label_and_no_free_text(self):
        r = build_cards([A("b", "1", "BOT-LIKE")])
        self.assertEqual(r["card_ui"]["select_all_label"], "Mark all for termination")
        self.assertFalse(r["card_ui"]["allow_free_text"])

    def test_product_wide_default(self):
        import json, product_config as pc
        self.assertEqual(pc.CARD_SELECT_ALL_LABEL, "Mark all for termination")
        self.assertFalse(pc.CARD_ALLOW_FREE_TEXT)
        d = json.load(open(Path(__file__).resolve().parents[1] / "config/default_user_config.json"))
        self.assertEqual(d["candidate_card_ui"]["select_all_label"], pc.CARD_SELECT_ALL_LABEL)
        self.assertFalse(d["candidate_card_ui"]["allow_free_text"])

    def test_review_note(self):
        import product_config as pc
        r = build_cards([A("b", "1", "BOT-LIKE")])
        self.assertEqual(r["card_ui"]["review_note"], "Unmarked accounts will be kept in review.")
        self.assertEqual(pc.CARD_REVIEW_NOTE, "Unmarked accounts will be kept in review.")

    def test_approval_check_note(self):
        import json, product_config as pc
        n = "Heads up: this is just a Grok Bot action check before I run a step. It has nothing to do with X, and it's not a flag on your account."
        self.assertEqual(pc.APPROVAL_CHECK_NOTE, n)
        d = json.load(open(Path(__file__).resolve().parents[1] / "config/default_user_config.json"))
        self.assertEqual(d["approval_check_note"], n)
