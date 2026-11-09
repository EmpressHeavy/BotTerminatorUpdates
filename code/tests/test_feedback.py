"""v3.5.0 opt-in 'Send feedback to the creator' (independent of Hive Mind)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import feedback, memory  # noqa: E402



def test_scrub_removes_identifiers():
    t = feedback.scrub("I'm @someone, mail me at a.b" + "@x.com, id 1234567890 see https://x.com/p")
    assert "@someone" not in t and "x.com" not in t and "1234567890" not in t


def test_hive_only_on_clear_yes_and_always_recorded(tmp_path):
    r = feedback.handle("demo_a", "Please support Dropbox instead of Google Drive", "no thanks", root=tmp_path)
    assert r["hive"] is None and r["memory_id"]
    r = feedback.handle("demo_a", "Please support Dropbox, ping @someone", "Yes", topic="storage", root=tmp_path)
    h = r["hive"]
    assert h["record"].startswith("hive feedback add request ") and "@someone" not in h["record"]
    assert h["send"].startswith("hive feedback --bot bt --category request ") and h["dry_run"] == h["send"] + " --dry-run"
    assert h["intake"].startswith("https://hive-mind-intake.") and h["intake"] in (ROOT / "hive" / "hive.py").read_text()
    assert "draft" not in r


def test_hive_kind_mapping():
    assert feedback.hive_kind("bug") == "broken" and feedback.hive_kind("praise") == "request"
    assert feedback.hive_kind("declined") == "declined"
    assert feedback.hive_category("bug") == "bug" and feedback.hive_category("praise") == "praise" and feedback.hive_category("x") == "other"


def test_offer_mentions_dry_run_not_email():
    assert "email" not in feedback.OFFER.lower() and "exactly" in feedback.OFFER


def test_template_version_reads_package_file():
    ver = (ROOT / "VERSION").read_text().strip()
    assert feedback.TEMPLATE_VERSION == ver == "v3.5.20"


def test_package_has_no_creator_address():
    assert "botterminator@" not in (ROOT / "src" / "feedback.py").read_text().replace('"', "")
