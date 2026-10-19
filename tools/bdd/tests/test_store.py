import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import store
from bddlib.errors import StoreError, UsageError


class FeatureIdTest(unittest.TestCase):
    def test_valid_and_invalid_ids(self):
        self.assertEqual(store.parse_feature_id("FEAT-007"), "FEAT-007")
        for bad in ("feat-7", "FEAT-", "FEAT-7x", "FEAT-7 ", "../FEAT-7", "R-7.1", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(UsageError):
                    store.parse_feature_id(bad)

    def test_find_feature_dir_accepts_bare_and_slugged_names(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (store.features_dir(root) / "FEAT-007-order-discounts").mkdir(parents=True)
            (store.features_dir(root) / "FEAT-0070-other").mkdir()     # a different feature with the same prefix
            self.assertEqual(store.find_feature_dir(root, "FEAT-007").name, "FEAT-007-order-discounts")
            (store.features_dir(root) / "FEAT-008").mkdir()
            self.assertEqual(store.find_feature_dir(root, "FEAT-008").name, "FEAT-008")

    def test_missing_and_ambiguous_features(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (store.features_dir(root) / "FEAT-001").mkdir(parents=True)
            (store.features_dir(root) / "FEAT-001-again").mkdir()
            with self.assertRaises(UsageError) as cm:
                store.find_feature_dir(root, "FEAT-002")
            self.assertIn("no feature directory for FEAT-002", str(cm.exception))
            with self.assertRaises(UsageError) as cm:
                store.find_feature_dir(root, "FEAT-001")
            self.assertIn("ambiguous", str(cm.exception))


class JsonFilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "sub" / "x.json"

    def test_round_trip_is_utf8_lf_and_stable(self):
        store.write_json(self.path, {"schema": 1, "title": "訂單折扣", "b": 1, "a": 2})
        raw = self.path.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertIn("訂單折扣".encode("utf-8"), raw)                  # not \u-escaped
        self.assertLess(raw.index(b'"a"'), raw.index(b'"b"'))           # sorted keys: clean diffs
        self.assertEqual(store.read_json(self.path, "test file")["title"], "訂單折扣")

    def test_failed_write_leaves_the_original_and_no_temp_files(self):
        store.write_json(self.path, {"schema": 1, "v": "old"})
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.write_json(self.path, {"schema": 1, "v": "new"})
        self.assertEqual(store.read_json(self.path, "x")["v"], "old")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["x.json"])

    def test_refuses_corrupt_unversioned_and_newer_files(self):
        self.path.parent.mkdir(parents=True)
        cases = [("{not json", "cannot read"), ('{"a": 1}', "no schema version"), ("[1]", "no schema version"),
                 (json.dumps({"schema": store.SCHEMA + 1}), "upgrade greenlight")]
        for text, message in cases:
            with self.subTest(message=message):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(StoreError) as cm:
                    store.read_json(self.path, "state file")
                self.assertIn(message, str(cm.exception))

    def test_missing_file_is_reported_as_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            store.read_json(self.path, "x")

    def test_utc_timestamps_are_iso_8601(self):
        self.assertRegex(store.utc_now(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


if __name__ == "__main__":
    unittest.main()
