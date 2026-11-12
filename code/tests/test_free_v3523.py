"""v3.5.23: Bot Terminator is free. No gate module, config, or check step remains."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gate_files_are_gone():
    assert not (ROOT / "src" / "license_check.py").exists()
    assert not (ROOT / "config" / "license.json").exists()


def test_no_code_calls_a_gate():
    for path in (ROOT / "src").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "license_check" not in text and "_license_gate" not in text, path.name


def test_daily_scan_has_no_check_step():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import daily_routine
    steps = daily_routine.scan_steps({})
    assert steps[0].startswith("preflight")
    assert not any("license" in s or "Subscribe" in s for s in steps)
