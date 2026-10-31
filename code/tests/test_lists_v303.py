"""v3.0.3: chat card widgets allow at most 6 options. List batches are 4 + 2 buttons, the final skipped-lists card
is paged 4 at a time, the repeat-offender card is paged, and EVERY card builder in the package stays <= 6 options.
Made-up generic demo lists only; never X."""
import json, re, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st, lists_scan as ls, list_cards as lc, build_candidate_cards as bcc, review_followup as rf
import graveyard_return_cards as grc, graveyard_returns as gr, inactive_mutuals as im
import build_monthly_settings_card as bmc
from test_lists_v301 import root  # noqa: F401  (fixture)
from test_lists_v302 import recs, hist, UK
from test_beta_fixes import env as beta_env, _mutuals, UK as BETA_UK  # noqa: F401

MAX = 6


def labels(card):
    return [o["label"] for o in card["card_spec"]["options"]]


def test_batch_cards_are_four_lists_plus_two_buttons(root):
    sid = ls.build_snapshot(UK, root, records=recs(9))["snapshot_id"]
    cards = lc.build_cards(UK, sid, root)
    assert lc.CARD_SIZE == 4 and [len(c["card_spec"]["options"]) for c in cards] == [6, 6, 3]
    assert all(len(c["card_spec"]["options"]) <= MAX for c in cards)
    assert labels(cards[0])[-2:] == [lc.REMOVE_BTN, lc.KEEP_BTN]
    assert [o["value"] for o in cards[0]["card_spec"]["options"]][-2:] == ["remove", "keep_all"]


def _skip_all(root, n):
    sid = ls.build_snapshot(UK, root, records=recs(n))["snapshot_id"]
    cards = lc.build_cards(UK, sid, root)
    for c in cards:
        lc.record_answer(UK, sid, c["card"], [lc.REMOVE_BTN], root=root)   # nothing picked: every list skipped
    return sid


def test_final_card_pages_of_four_button_order_and_page_state(root):
    sid = _skip_all(root, 10)
    state_p = lc._paths(UK, sid, root)[1]
    seen = []
    for page in (1, 2, 3):
        f = lc.final_skipped_card(UK, sid, root)
        assert f["page"] == page and f["of"] == 3 and f["card_spec"]["prompt"] == lc.FINAL_PROMPT
        opts = f["card_spec"]["options"]
        assert len(opts) <= MAX and len(opts) == (6 if page < 3 else 4)
        assert [o["label"] for o in opts][-2:] == ["Remove me from selected lists", "Keep all skipped lists"]
        assert [o["value"] for o in opts][-2:] == ["remove", "keep_all"]
        assert st.load_json(state_p, {})["final_page"] == page - 1            # page index lives in state
        nums = [int(o["value"]) for o in opts[:-2]]
        assert nums == list(range((page - 1) * 4 + 1, (page - 1) * 4 + 1 + len(nums)))   # continuous numbering
        seen += nums
        # page 1: remove #2 ; page 2: keep all ; page 3: remove nothing
        ans = {1: ["2", lc.FINAL_REMOVE_BTN], 2: [lc.FINAL_KEEP_BTN], 3: [lc.FINAL_REMOVE_BTN]}[page]
        r = lc.record_final_answer(UK, sid, ans, root=root)
        assert r["recorded"] and r["page"] == page and r["of"] == 3
        assert r["next_page"] == (page + 1 if page < 3 else None)
    assert seen == list(range(1, 11))
    assert lc.final_skipped_card(UK, sid, root) is None
    state = st.load_json(state_p, {})
    assert state["final_done"] is True and len(state["in_review"]) == 3 + 2      # unselected on pages 1 and 3
    sel = [e for e in hist(root) if e["status"] == "LIST_SELECTION" and e["card"] == 0]
    assert len(sel) == 1 and sel[0]["final_page"] == 1 and [a["name"] for a in sel[0]["selected"]] == ["Topic B"]
    assert sum(e["status"] == "LIST_KEPT" for e in hist(root)) == 4                # page 2 only
    assert lc.record_final_answer(UK, sid, [lc.FINAL_KEEP_BTN], root=root)["recorded"] is False  # nothing left


def test_final_page_ignores_numbers_from_other_pages_and_needs_one_button(root):
    sid = _skip_all(root, 6)
    assert lc.record_final_answer(UK, sid, ["6", lc.FINAL_REMOVE_BTN], root=root)["authorized"] == []   # #6 is page 2
    assert lc.record_final_answer(UK, sid, [lc.FINAL_REMOVE_BTN, lc.FINAL_KEEP_BTN], root=root)["recorded"] is False
    assert lc.final_skipped_card(UK, sid, root)["page"] == 2
    assert lc.record_final_answer(UK, sid, ["6", lc.FINAL_REMOVE_BTN], root=root)["authorized"] == ["Topic F"]


def _returns(n):
    return [{"owner_handle": f"@demo_owner_{i}", "name": f"Topic {i}", "url": f"https://x.com/i/lists/{i}"}
            for i in range(1, n + 1)]


def test_repeat_offender_card_keeps_done_and_is_paged(root):
    ret = _returns(12)
    pages = [lc.build_repeat_offender_card(UK, ret, p) for p in (1, 2, 3)]
    assert [len(c["card_spec"]["options"]) for c in pages] == [6, 6, 3] and all(c["of"] == 3 for c in pages)
    assert all(c["card_spec"]["options"][-1]["label"] == "Done" for c in pages)
    assert [o["value"] for c in pages for o in c["card_spec"]["options"] if o["value"] != "done"] == [str(i) for i in range(1, 13)]
    assert lc.build_repeat_offender_card(UK, ret[:2])["card_spec"]["options"][-1]["label"] == "Done"
    assert lc.build_repeat_offender_card(UK, []) == {"accounts": []}
    # page-restricted answer: 7 is on page 2, so page 1's Done ignores it
    r = lc.record_repeat_offender_answer(UK, "s1", ret, ["7", "Done"], root=root, page=1)
    assert r["recorded"] is False
    r = lc.record_repeat_offender_answer(UK, "s1", ret, ["7", "Done"], root=root, page=2)
    assert r["authorized"] == ["@demo_owner_7"]


def test_graveyard_returns_card_is_paged():
    rets = [{"n": i, "handle": f"demo_{i:02d}"} for i in range(1, 13)]
    cards = [gr.returns_card(rets, p) for p in (1, 2, 3)]
    assert [len(c["options"]) + 1 for c in cards] == [6, 6, 3]       # +1 for the select-all option
    assert cards[1]["options"][0].startswith("R6.") and cards[0]["of"] == 3


# ---- every card builder in the package: <= 6 options (mark-all / Done / action buttons count) ----
def _gr_fake(n):
    return [{"handle": f"demo_{i:02d}", "x_user_id": str(2000000000 + i), "removed_at": "2026-10-03T12:00:00-07:00",
             "returned_at": "2026-10-16T19:00:00-07:00", "previous_handle": None} for i in range(1, n + 1)]


def _acct(i):
    return dict(handle=f"demo{i}", user_id=str(1000 + i), label="REVIEW", verified_type="none", i_follow=False)


def test_every_card_builder_has_at_most_six_options(root, beta_env):
    checked = {}

    def chk(name, opts):
        opts = list(opts)
        assert opts and len(opts) <= MAX, (name, len(opts))
        checked[name] = max(checked.get(name, 0), len(opts))

    # list cards (lists_scan + list_cards)
    chk("lists_scan.scope_card", ls.scope_card()["options"])
    sid = _skip_all(root, 23)
    for c in lc.build_cards(UK, sid, root):
        chk("list_cards.build_cards", c["card_spec"]["options"])
    while (f := lc.final_skipped_card(UK, sid, root)):
        chk("list_cards.final_skipped_card", f["card_spec"]["options"])
        lc.record_final_answer(UK, sid, [lc.FINAL_KEEP_BTN], root=root)
    for p in range(1, 4):
        chk("list_cards.build_repeat_offender_card", lc.build_repeat_offender_card(UK, _returns(11), p)["card_spec"]["options"])
    # likely-bot cards (any count, default card size)
    res = bcc.build_cards([_acct(i) for i in range(23)])
    for c in res["render"]:
        chk("build_candidate_cards.render_cards", c["card_spec"]["options"])
    # in-review follow-up cards
    items = [{"type": rf.RETURNEE if i % 2 else rf.CANDIDATE, "handle": f"demo{i}", "user_id": str(i)} for i in range(13)]
    for c in rf.build_review_cards(items)["cards"]:
        chk("review_followup.build_review_cards", c["options"])
    # v3.5.0 records backup setup card and upgrade card
    import records
    chk("records.setup_card", records.setup_card()["options"])
    chk("records.upgrade_card", records.upgrade_card()["options"])
    chk("records.migration_card", records.migration_card()["options"])
    chk("review_followup.keep_card", rf.keep_card([dict(i, n=k + 1) for k, i in enumerate(items)], 1)["options"])
    # graveyard returns: chat flow + legacy card
    for c in grc.build_flow(_gr_fake(13))["cards"]:
        chk("graveyard_return_cards.build_flow", c["options"])
    for p in (1, 2, 3):
        chk("graveyard_returns.returns_card", gr.returns_card([{"n": i, "handle": f"d{i}"} for i in range(1, 14)], p)["options"] + ["select_all"])
    # inactive mutuals (daily limit is capped at the card size)
    cfg_p = st.user_data_root(BETA_UK, beta_env["root"]) / "config.json"
    cfg = json.loads(cfg_p.read_text()); cfg["inactive_mutuals_per_day"] = 50; cfg_p.write_text(json.dumps(cfg))
    _mutuals(beta_env, 12)
    chk("inactive_mutuals.build_card", im.build_card(BETA_UK, beta_env["sid"], beta_env["root"], today="2026-10-20")["card_spec"]["options"])
    # monthly settings card (buttons)
    chk("build_monthly_settings_card.build", bmc.build()["buttons"])
    chk("build_monthly_settings_card.build(prior)", bmc.build({"last_purge_date": "2026-01-01"})["buttons"])
    import terminate_reminder as tr
    chk("terminate_reminder.card", [o["label"] for o in tr.card()["options"]])
    chk("terminate_reminder.time_card", [o["label"] for o in tr.time_card()["options"]])
    import hive_setup as hs
    chk("hive_setup.off_request_card", hs.off_request_card()["buttons"])
    chk("build_monthly_settings_card.build_toggle_card", bmc.build_toggle_card({}, True)["options"])
    assert set(checked) == EXPECTED_BUILDERS


EXPECTED_BUILDERS = {"lists_scan.scope_card", "list_cards.build_cards", "list_cards.final_skipped_card",
                     "list_cards.build_repeat_offender_card", "build_candidate_cards.render_cards",
                     "review_followup.build_review_cards", "review_followup.keep_card",
                     "graveyard_return_cards.build_flow", "graveyard_returns.returns_card",
                     "inactive_mutuals.build_card", "build_monthly_settings_card.build",
                     "build_monthly_settings_card.build(prior)",
                     "terminate_reminder.card", "terminate_reminder.time_card",
                     "records.setup_card", "records.upgrade_card", "records.migration_card",
                     "hive_setup.off_request_card", "build_monthly_settings_card.build_toggle_card"}


def test_no_unlisted_card_builder_in_src():
    """Guard: any src module that emits card options/buttons must be covered by the test above. If this fails you
    added a card builder: add it to test_every_card_builder_has_at_most_six_options and EXPECTED_FILES."""
    pat = re.compile(r'"(options|buttons|card_spec)"\s*:')
    found = {p.name for p in (ROOT / "src").glob("*.py") if pat.search(p.read_text(encoding="utf-8"))}
    assert found == EXPECTED_FILES, found ^ EXPECTED_FILES


EXPECTED_FILES = {"lists_scan.py", "list_cards.py", "build_candidate_cards.py", "review_followup.py",
                  "graveyard_return_cards.py", "graveyard_returns.py", "inactive_mutuals.py",
                  "build_monthly_settings_card.py", "terminate_reminder.py", "records.py", "hive_setup.py"}
