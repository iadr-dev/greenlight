import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from bddlib import store
from bddlib.errors import StoreError


class FileLockTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "state.json"
        store.write_json(self.path, {"schema": 1, "n": 0})

    def lock_file(self) -> Path:
        return self.path.with_name("state.json.lock")

    def test_concurrent_updates_are_never_lost(self):
        errors = []

        def worker():
            try:
                for _ in range(5):
                    store.update_json(self.path, "state", lambda d: d.__setitem__("n", d["n"] + 1))
            except Exception as exc:                      # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(store.read_json(self.path, "state")["n"], 60)

    def test_lock_is_released_after_use_and_after_an_error(self):
        store.update_json(self.path, "state", lambda d: None)
        self.assertFalse(self.lock_file().exists())

        def boom(_data):
            raise ValueError("rejected")

        with self.assertRaises(ValueError):
            store.update_json(self.path, "state", boom)
        self.assertFalse(self.lock_file().exists())
        self.assertEqual(store.read_json(self.path, "state")["n"], 0)       # nothing was written

    def test_a_held_lock_times_out_with_a_clear_message(self):
        self.lock_file().write_bytes(b"")
        with self.assertRaises(StoreError) as cm:
            with store.file_lock(self.path, timeout=0.2):
                pass
        self.assertIn("locked by another greenlight process", str(cm.exception))
        self.assertTrue(self.lock_file().exists())                            # someone else's lock is left alone

    def test_a_real_permission_problem_is_not_reported_as_contention(self):
        with mock.patch("os.open", side_effect=PermissionError(13, "Permission denied")):
            with self.assertRaises(StoreError) as cm:
                with store.file_lock(self.path, timeout=0.1):
                    pass
        self.assertIn("cannot create", str(cm.exception))
        self.assertIn("permission denied", str(cm.exception))

    def test_a_lock_left_by_a_crashed_process_is_broken_after_it_goes_stale(self):
        self.lock_file().write_bytes(b"")
        old = time.time() - 120
        os.utime(self.lock_file(), (old, old))
        with store.file_lock(self.path, timeout=1.0, stale_after=60.0):
            pass
        self.assertFalse(self.lock_file().exists())


if __name__ == "__main__":
    unittest.main()
