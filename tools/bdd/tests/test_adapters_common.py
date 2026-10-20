"""What every adapter must give: each instruction of the profiles it declares is bound, and its settings are usable."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter
from bddlib import config as cfg

REPO = Path(__file__).resolve().parents[3]
ADAPTERS = REPO / "adapters"
STEP_COMMENT = re.compile(r"(?:#|//) (C\.[A-Z_.]+)")
CORE = json.loads((REPO / "vocabulary" / "core.json").read_text(encoding="utf-8"))["instructions"]


def adapters_with_settings() -> list[Path]:
    return sorted(p.parent for p in ADAPTERS.glob("*/adapter.toml"))


def bound_instructions(path: Path) -> set[str]:
    """The instruction ids named in the comments of the adapter's step templates."""
    found: set[str] = set()
    for steps in (path / "templates").rglob("steps"):
        for source in steps.rglob("*"):
            if source.is_file() and source.suffix in {".py", ".ts", ".js", ".mjs"}:
                found |= set(STEP_COMMENT.findall(source.read_text(encoding="utf-8")))
    return found


class EveryAdapterTest(unittest.TestCase):
    def test_there_are_adapters_to_check(self):
        names = {p.name for p in adapters_with_settings()}
        self.assertTrue({"python-pytest-bdd", "ts-playwright-bdd"} <= names, names)

    def test_every_instruction_of_the_declared_profiles_is_bound_and_no_other(self):
        for path in adapters_with_settings():
            with self.subTest(adapter=path.name):
                profiles = set(adapter.load(path)["profiles"])
                wanted = {i["id"] for i in CORE if set(i["profiles"]) <= profiles}
                bound = bound_instructions(path)
                self.assertEqual(wanted - bound, set(), "instructions of the declared profiles without a step")
                self.assertEqual(bound - wanted, set(), "steps for instructions outside the declared profiles")

    def test_the_contract_files_exist(self):
        for path in adapters_with_settings():
            with self.subTest(adapter=path.name):
                for name in adapter.REQUIRED + ("ci.md",):
                    self.assertTrue((path / name).exists(), name)
                self.assertEqual(adapter.load(path)["name"], path.name)

    def test_the_config_block_is_valid_and_complete(self):
        for path in adapters_with_settings():
            with self.subTest(adapter=path.name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".bdd").mkdir()
                (root / ".bdd" / "config.toml").write_text(adapter.config_block(adapter.load(path)), encoding="utf-8")
                config = cfg.load(root)
                (scan,), (run,) = config.scans, config.runs
                self.assertEqual(run.adapter, path.name)
                self.assertTrue(scan.assert_patterns and scan.sleep_patterns and scan.stub_patterns)
                self.assertIn("BDD_EXPECTED_MISSING", run.expected_fail)
                self.assertIn("NotMapped", run.test_defect)
                self.assertTrue(config.feature_dirs and config.step_dirs)

    def test_every_support_file_of_an_adapter_is_one_it_ships(self):
        for path in adapters_with_settings():
            with self.subTest(adapter=path.name):
                shipped = {p.relative_to(path / "templates").as_posix() for p in adapter.template_files(path)}
                for name in adapter.load(path)["paths"].get("support", []):
                    if not any(c in name for c in "*?["):
                        self.assertIn(name, shipped, "a bound plumbing file the adapter does not provide")

    def test_installed_tooling_and_caches_are_not_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "templates"
            for rel in ("tests/a.ts", "tests/node_modules/pkg/index.js", "tests/__pycache__/a.pyc", ".gitkeep"):
                (base / rel).parent.mkdir(parents=True, exist_ok=True)
                (base / rel).write_text("x", encoding="utf-8")
            self.assertEqual([p.relative_to(base).as_posix() for p in adapter.template_files(Path(tmp))], ["tests/a.ts"])


if __name__ == "__main__":
    unittest.main()
