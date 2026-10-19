import tempfile
import unittest
from pathlib import Path

from bddlib import lockfile, state, store
from bddlib.errors import UsageError

SPEC = "@FEAT-007\nFeature: Discounts\n  @R-7.1 @EX-7.1.1\n  Scenario: S\n    Then the request succeeds\n"


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n')
        self.spec = self.write("features/discounts.feature", SPEC)
        self.step = self.write("steps/steps.py", "def then_ok():\n    assert True\n")
        self.feature_dir = state.create(self.root, "FEAT-007", "Order discounts", "standard")

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def gate(self, name: str, result: str = "pass", detail=None, red=None) -> dict:
        return state.record_gate(self.root, self.feature_dir, name, result, detail or {}, red)

    def lock_both(self) -> None:
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "spec", [self.spec])
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])


class CreateTest(ProjectCase):
    def test_slug(self):
        for title, expected in [("Order discounts", "order-discounts"), ("  A--b  ", "a-b"), ("訂單折扣", "feature"),
                                ("Café déjà vu", "cafe-deja-vu"), ("x" * 100, "x" * 40), ("!!!", "feature")]:
            with self.subTest(title=title):
                self.assertEqual(state.slug(title), expected)

    def test_new_feature_has_a_complete_initial_state(self):
        self.assertEqual(self.feature_dir.name, "FEAT-007-order-discounts")
        data = state.load(self.feature_dir)
        self.assertEqual((data["schema"], data["feature"], data["title"], data["phase"]),
                         (1, "FEAT-007", "Order discounts", "discover"))
        self.assertEqual(data["autonomy"], {"level": "standard", "switches": []})
        for key in ("gates", "assumptions", "cost"):
            self.assertEqual(data[key], {} if key in ("gates", "cost") else [])
        self.assertEqual((data["approvals"], data["red"]), ([], None))

    def test_refusals(self):
        with self.assertRaises(UsageError) as cm:
            state.create(self.root, "FEAT-007", "Again", "standard")
        self.assertIn("already exists", str(cm.exception))
        for args in (("FEAT-x", "T", "standard"),("FEAT-009", "T", "reckless"), ("FEAT-009", "   ", "standard")):
            with self.subTest(args=args):
                with self.assertRaises(UsageError):
                    state.create(self.root, *args)

    def test_a_feature_directory_without_state_gives_a_helpful_message(self):
        (store.features_dir(self.root) / "FEAT-010-bare").mkdir()
        for action in (lambda d: state.load(d), lambda d: state.add_cost(d, "bind", 1, 1.0)):
            with self.assertRaises(UsageError) as cm:
                action(store.features_dir(self.root) / "FEAT-010-bare")
            self.assertIn("bdd state init", str(cm.exception))


class GateTest(ProjectCase):
    def test_passing_gates_move_the_phase_forward_in_order(self):
        seen = []
        for gate in ("discover", "test-design", "system-map", "refine"):
            seen.append(self.gate(gate)["phase"])
        self.assertEqual(seen, ["specify", "examples", "refine", "bind"])

    def test_failing_gates_do_not_advance_and_keep_their_evidence(self):
        data = self.gate("discover", "fail", {"blocking_questions": "2"})
        self.assertEqual(data["phase"], "discover")
        self.assertEqual(data["gates"]["discover"]["result"], "fail")
        self.assertEqual(data["gates"]["discover"]["detail"], {"blocking_questions": "2"})

    def test_the_phase_never_moves_backwards(self):
        self.gate("discover")
        self.gate("test-design")
        self.assertEqual(self.gate("discover")["phase"], "examples")       # re-running an early gate

    def test_human_gates_cannot_be_recorded_here(self):
        for name in state.HUMAN_GATES:
            with self.assertRaises(UsageError) as cm:
                self.gate(name)
            self.assertIn("only the person can approve", str(cm.exception))
            self.assertIn(f"/greenlight:approve <feature> {name}", str(cm.exception))
        self.assertEqual(state.load(self.feature_dir)["gates"], {})

    def test_unknown_gate_and_bad_result(self):
        with self.assertRaises(UsageError):
            self.gate("deploy")
        with self.assertRaises(UsageError):
            self.gate("discover", "maybe")

    def test_red_may_only_accompany_the_bind_gate(self):
        with self.assertRaises(UsageError):
            self.gate("discover", red={"commit": "abc"})
        data = self.gate("bind", red={"commit": "abc", "dirty": False, "source_hash": "h", "at": "now"})
        self.assertEqual(data["red"]["commit"], "abc")


class EnforcedGateTest(ProjectCase):
    def test_implement_cannot_pass_while_nothing_is_locked(self):
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("spec is not locked", str(cm.exception))
        self.assertIn("bind is not locked", str(cm.exception))
        self.assertNotIn("implement", state.load(self.feature_dir)["gates"])

    def test_implement_passes_with_intact_locks_and_moves_to_verify(self):
        self.lock_both()
        self.assertEqual(self.gate("implement")["phase"], "verify")

    def test_implement_is_refused_if_a_locked_step_was_weakened(self):
        self.lock_both()
        self.step.write_text("def then_ok():\n    pass\n", encoding="utf-8", newline="\n")
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("steps/steps.py changed since it was locked", str(cm.exception))

    def test_implement_is_refused_if_a_spec_was_added_after_locking(self):
        self.lock_both()
        self.write("features/extra.feature", SPEC.replace("Discounts", "Extra"))
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("never locked", str(cm.exception))

    def test_a_failing_result_is_always_recordable(self):
        self.assertEqual(self.gate("implement", "fail")["gates"]["implement"]["result"], "fail")

    def test_verify_needs_implement_to_have_passed(self):
        self.lock_both()
        with self.assertRaises(UsageError) as cm:
            self.gate("verify")
        self.assertIn("implement gate has not passed", str(cm.exception))
        self.gate("implement")
        self.assertEqual(self.gate("verify")["phase"], "done")


class AssumptionCostModeTest(ProjectCase):
    def test_assumption_ids_follow_the_feature_number(self):
        first = state.add_assumption(self.feature_dir, "Discount applies before tax", "common in retail", ["after tax"])
        second = state.add_assumption(self.feature_dir, "Rounding is half-up", "default for money", [])
        self.assertEqual((first, second), ("A-007.1", "A-007.2"))
        stored = state.load(self.feature_dir)["assumptions"][0]
        self.assertEqual((stored["text"], stored["alternatives"]), ("Discount applies before tax", ["after tax"]))

    def test_assumptions_need_a_rationale(self):
        for text, why in (("x", ""), ("", "y"), ("  ", "y")):
            with self.subTest(text=text, why=why):
                with self.assertRaises(UsageError):
                    state.add_assumption(self.feature_dir, text, why, [])

    def test_cost_accumulates_per_phase(self):
        state.add_cost(self.feature_dir, "bind", 1200, 30.5)
        data = state.add_cost(self.feature_dir, "bind", 800, 10.0)
        state.add_cost(self.feature_dir, "implement", 5, 0.5)
        self.assertEqual(data["cost"]["bind"], {"tokens": 2000, "seconds": 40.5, "runs": 2})
        self.assertEqual(set(state.load(self.feature_dir)["cost"]), {"bind", "implement"})

    def test_cost_validation(self):
        for args in (("deploy", 1, 1.0), ("bind", -1, 1.0), ("bind", 1, -0.5)):
            with self.subTest(args=args):
                with self.assertRaises(UsageError):
                    state.add_cost(self.feature_dir, *args)

    def test_mode_switch_is_recorded_with_the_users_words(self):
        data = state.switch_autonomy(self.feature_dir, "autopilot", 'user said: "you decide"')
        self.assertEqual(data["autonomy"]["level"], "autopilot")
        (switch,) = data["autonomy"]["switches"]
        self.assertEqual((switch["from"], switch["to"], switch["phase"]), ("standard", "autopilot", "discover"))
        self.assertEqual(switch["reason"], 'user said: "you decide"')

    def test_mode_switch_validation(self):
        with self.assertRaises(UsageError):
            state.switch_autonomy(self.feature_dir, "standard", "no change")        # already standard
        with self.assertRaises(UsageError):
            state.switch_autonomy(self.feature_dir, "autopilot", "  ")
        with self.assertRaises(UsageError):
            state.switch_autonomy(self.feature_dir, "reckless", "why")


if __name__ == "__main__":
    unittest.main()
