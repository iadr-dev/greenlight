"""tools/pins/bump.py and release.py: the language versions move to the newest supported release, the patch release is prepared."""
import datetime
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PINS = REPO / "tools" / "pins"
sys.path.insert(0, str(PINS))


def load(name):
    spec = importlib.util.spec_from_file_location(f"pins_{name}", PINS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bump, release = load("bump"), load("release")
TODAY = datetime.date(2026, 11, 5)
NODE = [{"cycle": "27", "eol": "2030-04-30", "lts": False, "releaseDate": "2026-10-28"},      # too new to move to
        {"cycle": "26", "eol": "2029-04-30", "lts": "2026-10-28", "releaseDate": "2026-04-22"},
        {"cycle": "25", "eol": "2026-06-01", "lts": False, "releaseDate": "2025-10-15"},
        {"cycle": "24", "eol": "2028-04-30", "lts": True, "releaseDate": "2025-05-06"},
        {"cycle": "22", "eol": "2027-04-30", "lts": True, "releaseDate": "2024-04-24"}]
PYTHON = [{"cycle": "3.15", "eol": "2031-10-31", "lts": False, "releaseDate": "2026-10-16"},
          {"cycle": "3.14", "eol": "2030-10-31", "lts": False, "releaseDate": "2025-10-07"},
          {"cycle": "3.13", "eol": "2029-10-31", "lts": False, "releaseDate": "2024-10-07"}]
DOTNET = [{"cycle": "10", "eol": "2028-11-14", "lts": True, "releaseDate": "2025-11-11"},
          {"cycle": "9", "eol": "2026-11-10", "lts": False, "releaseDate": "2024-11-12"}]


class TargetTest(unittest.TestCase):
    def test_the_newest_long_term_cycle_that_has_settled_where_the_language_has_them(self):
        self.assertEqual(bump.target(NODE, TODAY), "26")

    def test_the_newest_supported_cycle_that_has_settled_where_it_has_none(self):
        self.assertEqual(bump.target(PYTHON, TODAY), "3.14")

    def test_nothing_when_no_cycle_is_supported(self):
        self.assertIsNone(bump.target([{"cycle": "8", "eol": True}], TODAY))

    def test_a_pin_keeps_its_shape_and_only_moves_up(self):
        self.assertEqual(bump.moved("22", "26"), "26")
        self.assertEqual(bump.moved("3.12", "3.14"), "3.14")
        self.assertEqual(bump.moved("10.0.x", "11"), "11.0.x")
        self.assertIsNone(bump.moved("26", "26"))
        self.assertIsNone(bump.moved("26", "24"))
        self.assertIsNone(bump.moved("3.13.1", "3.14"))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.answers = {"https://endoflife.date/api/nodejs.json": NODE, "https://endoflife.date/api/python.json": PYTHON,
                        "https://endoflife.date/api/dotnet.json": DOTNET}

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def plan(self):
        return bump.plan(self.root, self.answers.get, TODAY)

    def test_every_file_is_moved_and_only_the_version_changes(self):
        path = self.write(".github/workflows/ci.yml", 'steps:\n  - with:\n      node-version: "22"   # LTS\n      python-version: "3.12"\n')
        texts, changes, skipped = self.plan()
        self.assertEqual(texts[path], 'steps:\n  - with:\n      node-version: "26"   # LTS\n      python-version: "3.14"\n')
        self.assertEqual(sorted(changes), ["nodejs 22 -> 26 in .github/workflows/ci.yml", "python 3.12 -> 3.14 in .github/workflows/ci.yml"])
        self.assertEqual(skipped, [])

    def test_a_version_in_the_current_form_of_a_guide_is_moved_too(self):
        path = self.write("adapters/x/ci.md", "- uses: actions/setup-node@abc  # v7\n  with:\n    node-version: 22\n")
        texts, _, _ = self.plan()
        self.assertIn("node-version: 26\n", texts[path])

    def test_a_pin_already_at_the_target_or_ahead_is_left_alone(self):
        self.write(".github/workflows/ci.yml", 'node-version: "26"\ndotnet-version: "10.0.x"\n')
        texts, changes, _ = self.plan()
        self.assertEqual((texts, changes), ({}, []))

    def test_a_pin_held_on_its_line_stays_while_the_others_of_the_file_move(self):
        held = '  java-version: "21"   # pins: hold - detekt stops at 22\n'
        path = self.write(".github/workflows/ci.yml", 'a:\n  java-version: "21"\nb:\n' + held)
        self.answers["https://endoflife.date/api/eclipse-temurin.json"] = [
            {"cycle": "25", "eol": "2031-09-30", "lts": True, "releaseDate": "2025-09-16"}]
        texts, changes, skipped = self.plan()
        self.assertEqual(texts[path], 'a:\n  java-version: "25"\nb:\n' + held)
        self.assertEqual((len(changes), skipped), (1, []))

    def test_a_file_whose_only_pin_is_held_is_left_untouched(self):
        self.write(".github/workflows/ci.yml", 'node-version: "22"   # pins: hold - the tool needs 22\n')
        self.assertEqual(self.plan()[0], {})

    def test_two_versions_of_one_language_in_a_file_are_a_decision_and_are_left_alone(self):
        self.write(".github/workflows/ci.yml", 'a: 1\nnode-version: "20"\nnode-version: "22"\n')
        texts, changes, skipped = self.plan()
        self.assertEqual((texts, changes), ({}, []))
        self.assertIn("names 20, 22; left alone", skipped[0])

    def test_a_language_with_no_answer_is_left_alone_and_said(self):
        self.answers.clear()
        self.write(".github/workflows/ci.yml", 'node-version: "22"\n')
        texts, _, skipped = self.plan()
        self.assertEqual((texts, skipped), ({}, ["nodejs: no answer from endoflife.date; left alone"]))

    def test_the_summary_groups_the_files_of_one_move(self):
        text = bump.summary(["nodejs 22 -> 26 in a.yml", "nodejs 22 -> 26 in b.yml"], ["c.yml: x"])
        self.assertIn("- nodejs 22 -> 26 (2 files)", text)
        self.assertIn("Left alone:", text)


class LogEntryTest(unittest.TestCase):
    def test_the_change_is_recorded_under_unreleased(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CHANGELOG.md").write_text("# C\n\n## [Unreleased]\n\n### Added\n- x\n\n## [1.0.0] - d\n", encoding="utf-8")
            bump.log_entry(root, ["nodejs 22 -> 26 in a.yml", "nodejs 22 -> 26 in b.yml", "go 1.26 -> 1.27 in c.yml"])
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [Unreleased]\n\n### Changed\n- Pinned language versions moved", text)
        self.assertIn("go 1.26 -> 1.27; nodejs 22 -> 26.", text)
        self.assertIn("### Added\n- x", text)


class ReleaseTest(unittest.TestCase):
    CHANGELOG = ("# Changelog\n\n## [Unreleased]\n\n### Changed\n- A thing.\n\n## [1.2.0] - 2026-11-04\n\nOld.\n")

    def test_the_next_patch_version(self):
        self.assertEqual(release.patch_after("1.2.0"), "1.2.1")
        self.assertEqual(release.patch_after("1.9.9"), "1.9.10")

    def test_unreleased_becomes_the_section_of_the_new_version(self):
        text = release.changelog(self.CHANGELOG, "1.2.1", datetime.date(2026, 11, 9))
        self.assertIn("## [Unreleased]\n\n## [1.2.1] - 2026-11-09\n\n" + release.INTRO + "\n\n### Changed\n- A thing.\n\n## [1.2.0]", text)

    def test_nothing_is_released_when_nothing_is_unreleased(self):
        with self.assertRaises(SystemExit):
            release.changelog("# C\n\n## [Unreleased]\n\n## [1.2.0] - x\n", "1.2.1", TODAY)

    def test_the_tag_the_adapters_clone_is_found_in_both_forms(self):
        for text in ("  GREENLIGHT_REF: v1.2.0          # a release tag", "- run: git clone --depth 1 --branch v1.2.0 https://x"):
            self.assertIn("v1.2.1", release.CLONE.sub(lambda m: m.group(1) + "1.2.1", text))

    def test_writing_a_release_edits_every_place_the_version_is_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = {".claude-plugin/plugin.json": '{\n  "version": "1.2.0"\n}\n',
                     ".claude-plugin/marketplace.json": '{"plugins": [{"version": "1.2.0"}]}\n',
                     "tools/bdd/bddlib/__init__.py": '__version__ = "1.2.0"\n',
                     "adapters/a/ci/github-actions.yml": "  GREENLIGHT_REF: v1.2.0          # a release tag\n",
                     "adapters/a/ci.md": "- run: git clone --depth 1 --branch v1.2.0 https://x\n",
                     "CHANGELOG.md": self.CHANGELOG}
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            original, release.REPO = release.REPO, root
            try:
                self.assertEqual(release.main(["--write"]), 0)
            finally:
                release.REPO = original
            for rel in list(files)[:5]:
                text = (root / rel).read_text(encoding="utf-8")
                self.assertIn("1.2.1", text, rel)
                self.assertNotIn("1.2.0", text, rel)
            log = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## [Unreleased]\n\n## [1.2.1] - ", log)
            self.assertIn("### Changed\n- A thing.\n\n## [1.2.0] - 2026-11-04", log)

    def test_the_repository_stamps_one_version_everywhere(self):
        version = release.current(REPO)
        self.assertEqual(json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["plugins"][0]["version"], version)
        for path in sorted(REPO.glob("adapters/*/ci/github-actions.yml")) + sorted(REPO.glob("adapters/*/ci.md")):
            for m in release.CLONE.finditer(path.read_text(encoding="utf-8")):
                self.assertEqual(m.group(0).split("v")[-1], version, str(path))


if __name__ == "__main__":
    unittest.main()
