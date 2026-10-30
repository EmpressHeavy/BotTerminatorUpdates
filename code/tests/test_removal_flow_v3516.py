"""v3.5.16: copies must remove followers themselves in the box browser, never fall back to a TXT file or manual steps."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import removal_flow as rf  # noqa: E402

_cands = [ROOT / "docs/skills/bot-terminator-getting-started.md",
          ROOT.parent / "skills/bot-terminator-getting-started/SKILL.md"]
SKILL = next(p for p in _cands if p.exists()).read_text()


def test_skill_has_bot_run_removal_flow():
    assert rf.missing_terms(SKILL) == []


def test_skill_and_readme_have_no_manual_or_file_handoff():
    assert rf.check_text(SKILL) == []
    assert rf.check_text((ROOT / "README.md").read_text()) == []


def test_skill_does_not_need_owner_computer():
    assert "on this owner's own computer" not in SKILL
    assert "box browser" in SKILL


def test_lint_catches_regressions():
    assert rf.check_text("Here is a TXT file; remove these by hand.")
    assert rf.check_text("You can remove them manually on X.")
    assert rf.check_text("Never tell the owner to remove accounts by hand.") == []


def test_constants():
    assert rf.ROUND_SIZE == 5 and rf.SECONDS_APART == 10 and rf.ALLOWED_OWNER_FILE == "csv_backup"
