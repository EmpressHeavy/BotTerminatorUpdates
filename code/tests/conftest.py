"""Product tests are not a paid clone. The license gate is exercised in test_license_check.py."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def _license_open_for_product_tests(request, monkeypatch):
    if Path(str(request.node.path)).name == "test_license_check.py":
        return
    import license_check
    monkeypatch.setattr(license_check, "require", lambda *args, **kwargs: {"allow": True, "reason": "test"})
