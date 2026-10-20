"""The parts of the end-to-end harness that need no model: its request table and the adoption invariants."""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HARNESS = REPO / "evals" / "run_e2e.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_e2e", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RequestTableTest(unittest.TestCase):
    def test_every_request_has_a_file_a_skill_and_a_reference_app(self):
        harness = load_harness()
        self.assertEqual(set(harness.REQUEST_KINDS), {p.stem for p in (REPO / "evals" / "requests").glob("*.md")})
        for name, kind in harness.REQUEST_KINDS.items():
            with self.subTest(request=name):
                self.assertTrue((harness.APPS / kind["app"]).is_dir())
                self.assertTrue((REPO / "skills" / kind["skill"] / "SKILL.md").is_file())

    def test_the_adoption_reference_app_has_no_tests(self):
        names = [p.name for p in (REPO / "evals" / "apps" / "legacy-billing").rglob("*.py")]
        self.assertFalse([n for n in names if n.startswith("test_") or n.endswith("_test.py")])


class ProductionChangesTest(unittest.TestCase):
    def test_greenlights_data_tests_and_generated_bytecode_are_not_production(self):
        harness = load_harness()
        lines = ["?? .bdd/features/FEAT-001/state.json", " M tests/features/billing.feature",
                 "?? billing/__pycache__/pricing.cpython-312.pyc", " M .gitignore"]
        self.assertEqual(harness.production_changes(lines), [])

    def test_anything_importable_under_a_bytecode_name_is_production(self):
        harness = load_harness()
        lines = ["?? billing/__pycache__/evil.py", "?? billing/legacy.pyc", " M billing/__pycache__/pricing.cpython-312.pyc"]
        self.assertEqual(harness.production_changes(lines),
                         ["billing/__pycache__/evil.py", "billing/legacy.pyc", "billing/__pycache__/pricing.cpython-312.pyc"])

    def test_a_changed_renamed_or_new_source_file_is_production(self):
        harness = load_harness()
        lines = [" M billing/pricing.py", "?? billing/extra.py", "R  billing/old.py -> billing/new.py",
                 ' M "billing/with space.py"']
        self.assertEqual(harness.production_changes(lines),
                         ["billing/pricing.py", "billing/extra.py", "billing/new.py", "billing/with space.py"])


if __name__ == "__main__":
    unittest.main()
