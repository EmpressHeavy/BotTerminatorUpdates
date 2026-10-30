"""v3.3.0 per-user isolation: no shipped file may carry the publisher's personal data (handles, account IDs,
sheet/doc IDs, private paths). The pattern list itself is kept by the publisher, not shipped."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# v3.5.16: the publisher's identifier list is not shipped (not even encoded). The publisher runs this test with
# BT_PRIVATE_PATTERNS_FILE=<local file, one hex-encoded pattern per line, in the original order>; clones skip it.
import os
import pytest
_PF = os.environ.get("BT_PRIVATE_PATTERNS_FILE")
_HEX = [l.strip() for l in open(_PF).read().splitlines() if l.strip()] if _PF and os.path.exists(_PF) else []
if not _HEX:
    pytest.skip("publisher-only identifier scan (BT_PRIVATE_PATTERNS_FILE not set)", allow_module_level=True)
PATTERNS = [bytes.fromhex(h).decode().lower() for h in _HEX]
# v3.5.10: the packaged Hive Mind client and its historical skill fixture must contain the creator's public
# lesson-intake endpoint; only that owner-name pattern is allowed there (v3.5.11 review/intake files must not need it).
ALLOWED = {("hive/hive.py", 3), ("docs/skills/bot-terminator-getting-started.md", 3), ("tests/fixtures/hive_skill_v358.md", 3)}


def shipped_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True)
    files = [f for f in out.stdout.decode().split("\0") if f] if out.returncode == 0 else []
    if not files:  # unpacked tgz without .git
        files = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                 and ".git" not in p.parts and "data" not in p.parts[:1]]
    return files


def test_patterns_decode():
    assert len(PATTERNS) == len(_HEX) and all(PATTERNS)


def test_no_owner_identifiers_in_shipped_files():
    hits = []
    for rel in shipped_files():
        p = ROOT / rel
        if not p.is_file():
            continue
        text = p.read_bytes().decode("utf-8", "ignore").lower()
        hits += [(rel, i) for i, pat in enumerate(PATTERNS) if pat in text and (rel, i) not in ALLOWED]
    assert hits == [], f"publisher identifiers found in shipped files: {hits}"


def test_memory_schema_has_no_prefilled_rows():
    sql = (ROOT / "templates/memory_schema.sql").read_text().upper()
    assert "INSERT" not in sql and "DEFAULT 'E" not in sql
