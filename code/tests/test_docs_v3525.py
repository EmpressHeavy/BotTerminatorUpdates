"""v3.5.25 (Hive Mind 2026-W47): shipped skill text covers the X sign-in browser fallback and the public-repo-only
install rule, and never tells an owner to request access to a private repo."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "docs" / "skills" / "bot-terminator-getting-started.md"
ACCESS_ASK = re.compile(r"\b(?:request|ask for|email (?:me |us |the creator )?for)\s+(?:read-only\s+)?access\b", re.I)
NEG = re.compile(r"\b(?:never|no|not|don't|do not|without)\b", re.I)


def _text():
    return SKILL.read_text(encoding="utf-8")


def test_sign_in_fallback_to_alternate_browser():
    t = _text()
    assert "If the sign-in hangs" in t and "Firefox" in t and "request_box_help" in t
    assert "phone-confirm" in t and "x_browser" in t


def test_public_repo_only_install():
    t = _text()
    assert "https://github.com/EmpressHeavy/BotTerminatorUpdates" in t
    assert "Public repo only, never private access" in t
    assert "my-bot-terminator-backup" in t


def test_no_unnegated_access_request_wording():
    texts = [_text(), (ROOT / "README.md").read_text(encoding="utf-8")]
    for t in texts:
        for line in t.splitlines():
            if ACCESS_ASK.search(line):
                assert NEG.search(line), line
