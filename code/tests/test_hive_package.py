"""v3.5.9/v3.5.11: hive/hive.py ships in the package and is installed byte-for-byte (no edits) by tools/install_hive.sh.
v3.5.11: the hive-mind skill no longer embeds the client; it points at the packaged file, so the identity check is
package file == installed file, and the skill text in docs/skills/hive-mind.md carries no code block."""
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_helper_copies_byte_identical(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path), "MEM_DB": str(tmp_path / "brain.db")}
    subprocess.run(["sh", str(ROOT / "tools/install_hive.sh")], check=True, env=env, capture_output=True)
    assert (tmp_path / "memory/hive.py").read_bytes() == (ROOT / "hive/hive.py").read_bytes()
    wrapper = (tmp_path / "bin/hive").read_text()
    assert wrapper == '#!/bin/sh\nexec python3 "$HOME/memory/hive.py" "$@"\n'
    out = subprocess.run([str(tmp_path / "bin/hive"), "status"], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.startswith("enabled=0")


def test_rerun_refreshes_client_without_changing_hive_switch(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path), "MEM_DB": str(tmp_path / "memory/brain.db")}
    subprocess.run(["sh", str(ROOT / "tools/install_hive.sh")], check=True, env=env, capture_output=True)
    hive = str(tmp_path / "bin/hive")
    off = subprocess.run([hive, "status"], env=env, capture_output=True, text=True, check=True)
    assert off.stdout.startswith("enabled=0")
    subprocess.run([hive, "on", "--bot", "bt"], env=env, capture_output=True, text=True, check=True)
    subprocess.run(["sh", str(ROOT / "tools/install_hive.sh")], check=True, env=env, capture_output=True)
    on = subprocess.run([hive, "status"], env=env, capture_output=True, text=True, check=True)
    assert on.stdout.startswith("enabled=1")
    assert (tmp_path / "memory/hive.py").read_bytes() == (ROOT / "hive/hive.py").read_bytes()
    assert (tmp_path / "memory/VERSION").read_text().strip() == (ROOT / "VERSION").read_text().strip() == "v3.5.21"
    script = (ROOT / "tools/install_hive.sh").read_text()
    assert "hive on" not in script and "hive off" not in script


def test_install_script_is_plain_copy():
    sh = (ROOT / "tools/install_hive.sh").read_text()
    assert 'cp "$PKG_DIR/hive/hive.py" "$HOME/memory/hive.py"' in sh
    assert "sed" not in sh and "curl" not in sh and "wget" not in sh


def test_skill_doc_has_no_embedded_client():
    skill = (ROOT / "docs/skills/hive-mind.md").read_text()
    assert "```python" not in skill and "def main" not in skill and not skill.startswith("---")
    assert "hive/hive.py" in skill
