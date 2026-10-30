from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from always_keep_backup import (  # noqa: E402
    build_backup_payload,
    is_newer_or_equal,
    local_backup_copy,
    restore_from_payload,
)
from storage import save_always_keep, load_always_keep  # noqa: E402


def test_local_backup_and_refuse_older_restore(tmp_path: Path):
    save_always_keep([{"username": "keepme"}], root=tmp_path, user_key="test")
    # stamp local as newer
    path = tmp_path / "data" / "users" / "test" / "always_keep.json"
    data = json.loads(path.read_text())
    data["updated_at"] = "2026-09-30T20:00:00-07:00"
    data["version"] = 2
    path.write_text(json.dumps(data))
    backup = local_backup_copy(tmp_path, user_key="test")
    assert backup.exists()
    assert backup.parent == tmp_path / "data" / "users" / "test" / "backups" / "always_keep"
    payload = json.loads(backup.read_text())
    older = dict(payload)
    older["local_updated_at"] = "2026-09-01T00:00:00-07:00"
    older["backed_up_at"] = "2026-09-01T00:00:00-07:00"
    older["list_version"] = 1
    older["accounts"] = [{"username": "old"}]
    result = restore_from_payload(older, root=tmp_path, user_key="test", force=False)
    assert result["restored"] is False
    assert load_always_keep(tmp_path, user_key="test")[0]["username"] == "keepme"


def test_is_newer_or_equal_versions():
    newer = {"local_updated_at": "2026-09-30T12:00:00-07:00", "list_version": 2}
    older = {"local_updated_at": "2026-09-29T12:00:00-07:00", "list_version": 1}
    assert is_newer_or_equal(newer, older) is True
    assert is_newer_or_equal(older, newer) is False
