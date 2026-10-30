"""Two-user isolation (2026-10-16 fix): history, Always Keep, checkpoints, snapshots, backups,
reports and journal for one user_key never reach another; no global fallback."""
import datetime as dt, hashlib, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import storage as st
import record_chat_selection as rcs
import always_keep_backup as akb
import checkpoints as cpm

A, B = "example_owner", "example_friend"


class TwoUsers(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.root = Path(self.td.name)
        for uk in (A, B):
            u = self.root / "data/users" / uk; (u / "snapshots/s1").mkdir(parents=True)
            json.dump({"user_key": uk, "owner_x_handle": f"@{uk}", "protected_handles": [f"{uk}_family"]}, open(u / "config.json", "w"))
            accts = [{"chat_no": n, "card": 1, "handle": f"{uk}_h{n}", "user_id": str(n), "name": "N", "review_id": f"R{n}",
                      "label": "REVIEW", "tab": "In review", "sheet_row": n + 3} for n in range(1, 6)]
            json.dump({"snapshot_id": "s1", "batch_id": uk, "accounts": accts}, open(u / "snapshots/s1/chat_numbering.json", "w"))
        self._root = rcs.ROOT; rcs.ROOT = self.root

    def tearDown(self):
        rcs.ROOT = self._root; self.td.cleanup()

    def test_history_separate_and_chained(self):
        now = dt.datetime(2026, 10, 16, 18, 0, tzinfo=rcs.PT)
        for uk, n in ((A, 2), (B, 1)):
            for _ in range(n):
                e = rcs.build("s1", 1, [1, 2, 3, 4, 5], "1, 2", now=now, user_key=uk)["history_entry"]
                rcs.append_history(e, user_key=uk)
        la = st.history_path(self.root, user_key=A).read_bytes().splitlines()
        lb = st.history_path(self.root, user_key=B).read_bytes().splitlines()
        self.assertEqual((len(la), len(lb)), (2, 1))
        self.assertTrue(all(json.loads(l)["owner_x_handle"] == "@example_owner" for l in la))
        self.assertEqual(json.loads(lb[0])["owner_x_handle"], "@example_friend")
        self.assertNotIn(b"example_friend", b"".join(la)); self.assertNotIn(b"example_owner", b"".join(lb))
        self.assertEqual(json.loads(la[1])["prev_entry_sha256"], hashlib.sha256(la[0]).hexdigest())
        self.assertIsNone(json.loads(lb[0])["prev_entry_sha256"])  # B's chain starts fresh
        # An entry built for A cannot be appended to B's log.
        e = rcs.build("s1", 1, [1, 2, 3, 4, 5], "1", now=now, user_key=A)["history_entry"]
        with self.assertRaises(ValueError):
            rcs.append_history(e, user_key=B)
        self.assertFalse((self.root / "capability_tests").exists())
        self.assertFalse((self.root / "data/history.jsonl").exists())

    def test_keep_lists_checkpoints_backups_separate(self):
        st.save_always_keep([{"username": "a_keep"}], self.root, user_key=A)
        st.save_always_keep([{"username": "b_keep"}], self.root, user_key=B)
        self.assertEqual([x["username"] for x in st.load_always_keep(self.root, user_key=A)], ["a_keep"])
        self.assertEqual([x["username"] for x in st.load_always_keep(self.root, user_key=B)], ["b_keep"])
        cpm.checkpoint_list_batch(batch_index=0, usernames=["only_a"], root=self.root, user_key=A)
        self.assertNotIn("only_a", cpm.usernames_to_skip(self.root, user_key=B))
        bk = akb.local_backup_copy(self.root, user_key=A)
        self.assertTrue(str(bk).startswith(str(self.root / "data/users" / A)))
        payload = json.loads(bk.read_text())
        self.assertFalse(akb.restore_from_payload(payload, self.root, user_key=B, force=True)["restored"])
        self.assertEqual([x["username"] for x in st.load_always_keep(self.root, user_key=B)], ["b_keep"])
        for g in ("data/always_keep.json", "data/checkpoints.json", "data/snapshots", "data/backups"):
            self.assertFalse((self.root / g).exists(), g)

    def test_protected_handles_per_user(self):
        import automatic_policy as ap
        self.assertEqual(ap.protected_handles_for(A, self.root), {"example_owner_family"})
        self.assertEqual(ap.protected_handles_for(B, self.root), {"example_friend_family"})

    def test_journal_and_reports_per_user(self):
        st.append_journal("a line", self.root, user_key=A)
        self.assertFalse(st.journal_path(self.root, user_key=B).exists())
        self.assertNotEqual(st.reports_path(self.root, user_key=A), st.reports_path(self.root, user_key=B))

    def test_no_user_key_refused(self):
        for bad in (None, "", "../x", "A/B", "Upper"):
            with self.assertRaises((ValueError, TypeError)):
                st.always_keep_path(self.root, user_key=bad)
        with self.assertRaises(TypeError):
            st.load_always_keep(self.root)
        with self.assertRaises(TypeError):
            rcs.append_history({"prev_entry_sha256": None})

    def test_config_of_other_user_rejected(self):
        json.dump({"user_key": B}, open(self.root / "data/users" / A / "config.json", "w"))
        with self.assertRaises(ValueError):
            st.load_user_config_dict(self.root, user_key=A)


if __name__ == "__main__":
    unittest.main()
