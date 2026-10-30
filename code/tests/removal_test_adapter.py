"""TEST-ONLY adapter for the removal runner. Not a user-facing practice mode (there is none): it never touches X
and exists only so tests can script lookup/remove/block results and check what the runner asked for."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from removal_runner import RemovalResult  # noqa: E402


class DryTestAdapter:
    def __init__(self, fresh=None, results=None):
        self.fresh = fresh or {}          # handle -> dict overriding the default fresh lookup
        self.results = list(results or [])  # RemovalResult per remove() call, default ok
        self.calls = []                   # ("lookup"|"remove", handle)
        self.removed = set()              # handles removed through this adapter (then they no longer follow)

    def lookup(self, account):
        h = str(account.get("handle") or "").lstrip("@")
        self.calls.append(("lookup", h))
        base = {"user_id": account.get("x_user_id") or account.get("user_id"), "handle": h,
                "i_follow": False, "verified_type": "none", "recent_interaction": False,
                "follows_me": h not in self.removed}
        base.update(self.fresh.get(h, {}))
        return base

    def remove(self, account):
        h = str(account.get("handle") or "").lstrip("@")
        self.calls.append(("remove", h))
        res = self.results.pop(0) if self.results else RemovalResult("ok", "removed (test)")
        if res.status == "ok":
            self.removed.add(h)
        return res

    def block(self, account):
        self.calls.append(("block", str(account.get("handle") or "").lstrip("@")))
        return self.results.pop(0) if self.results else RemovalResult("ok", "blocked (test)")

    # Anything else the runner might call is a test failure.
    def __getattr__(self, name):
        raise AssertionError(f"runner called forbidden adapter method {name!r}")
