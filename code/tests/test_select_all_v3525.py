"""v3.5.25 (Hive Mind 2026-W47): the review card's select-all answer must select EVERY account on the card.

Live bug: the select-all option's value ("mark_all") arrived as plain text and was recorded as no selection.
Every shape the card can hand back (value, label with the real count, JSON-encoded list, list) is covered.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import card_text as ct  # noqa: E402
import graveyard_return_cards as grc  # noqa: E402
import record_chat_selection as rcs  # noqa: E402
import review_followup as rf  # noqa: E402
from test_review_followup import rv  # noqa: E402,F401
from test_graveyard_returns import env, UK  # noqa: E402,F401

C = [91, 92, 93, 94, 95]
SELECT_ALL_ANSWERS = [
    "mark_all", "MARK_ALL", " mark_all ", '"mark_all"', '["mark_all"]', "select_all",
    "Mark all 5 for termination", "mark all 5 for termination", "Mark all for termination",
    "Mark all for blocking", "Select all", "Select all \u2014 mark for termination",
    ["mark_all"], ["Mark all 5 for termination"], ["select_all"], ('mark_all',),
    [{"label": "Mark all 5 for termination", "value": "mark_all"}], {"value": "mark_all"},
]
NOT_SELECT_ALL = ["", None, [], "none", "92", ["92", "94"], '["92","94"]', "mark all except 93",
                  "92. @someone \u2014 3 posts"]


@pytest.mark.parametrize("ans", SELECT_ALL_ANSWERS, ids=repr)
def test_is_select_all(ans):
    assert ct.is_select_all(ans)


@pytest.mark.parametrize("ans", NOT_SELECT_ALL, ids=repr)
def test_not_select_all(ans):
    assert not ct.is_select_all(ans)


@pytest.mark.parametrize("ans", SELECT_ALL_ANSWERS, ids=repr)
def test_round_card_select_all_marks_every_account(ans):
    sel, via = rcs.parse_answer(ans, C)
    assert sel == C and via == "Select all"


@pytest.mark.parametrize("ans", SELECT_ALL_ANSWERS, ids=repr)
def test_graveyard_card_select_all_marks_every_account(ans):
    assert grc.parse_answer(ans, C) == C


def test_individual_picks_unchanged():
    assert rcs.parse_answer(["92", "94"], C)[0] == [92, 94]
    assert rcs.parse_answer('["92","94"]', C)[0] == [92, 94]
    assert rcs.parse_answer("mark all except 93", C)[0] == [91, 92, 94, 95]
    assert rcs.parse_answer([], C)[0] == []
    assert grc.parse_answer(["92", "94"], C) == [92, 94]


@pytest.mark.parametrize("ans", ["mark_all", '["mark_all"]', "Mark all 4 for termination"])
def test_review_followup_plain_text_select_all(rv, ans):
    rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    res = rf.record_terminate(UK, rv["s2"], 1, ans, root=rv["root"])
    assert res["removal_authorized"] == [1] and res["block_authorized"] == [2, 3, 4] and res["keep_card"] is None
