from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from read_pacing import PaceConfig, PaceEvent, PaceMachine, PaceState  # noqa: E402


def test_success_resets_failures_and_marks_seen():
    m = PaceMachine(PaceConfig(initial_batch_size=20))
    m.start()
    m.note_success("alice")
    assert m.should_skip("alice")
    assert not m.should_skip("bob")
    assert m.consecutive_failures == 0
    assert m.state == PaceState.RUNNING


def test_warnings_shrink_batch_and_cooldown():
    m = PaceMachine(PaceConfig(initial_batch_size=20, warning_shrink_after=2, shrink_factor=0.5, min_batch_size=5))
    m.start()
    m.note_event(PaceEvent.WARNING)
    assert m.state == PaceState.RUNNING
    m.note_event(PaceEvent.WARNING)
    assert m.batch_size == 10
    assert m.state == PaceState.COOLDOWN
    assert m.cooldown_seconds() > 0


def test_hard_stop_on_repeated_429():
    m = PaceMachine(PaceConfig(hard_stop_after_failures=3, initial_batch_size=25, min_batch_size=5))
    m.start()
    m.note_event(PaceEvent.RATE_LIMIT_429)
    m.note_event(PaceEvent.LOADING_STUCK)
    assert m.can_continue()
    m.note_event(PaceEvent.BLANK)
    assert m.state == PaceState.HARD_STOP
    assert not m.can_continue()
    assert "hard_stop" in (m.stop_reason or "")


def test_duplicate_skip_prevention():
    m = PaceMachine()
    m.mark_seen("x")
    m.mark_seen("y")
    assert m.should_skip("x")
    status = m.status()
    assert status["seen_count"] == 2
