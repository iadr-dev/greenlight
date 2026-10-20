import unittest

from bddlib import enforcement, state, store
from bddlib.errors import UsageError

from tests.helpers import ProjectCase


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
        self.assertEqual((data["approvals"], data["red"], data["hooks_seen"]), ([], None, False))

    def test_refusals(self):
        with self.assertRaises(UsageError) as cm:
            state.create(self.root, "FEAT-007", "Again", "standard")
        self.assertIn("already exists", str(cm.exception))
        for args in (("FEAT-x", "T", "standard"), ("FEAT-009", "T", "reckless"), ("FEAT-009", "   ", "standard")):
            with self.subTest(args=args):
                with self.assertRaises(UsageError):
                    state.create(self.root, *args)

    def test_a_feature_directory_without_state_gives_a_helpful_message(self):
        (store.features_dir(self.root) / "FEAT-010-bare").mkdir()
        for action in (lambda d: state.load(d), lambda d: state.add_cost(d, "bind", 1, 1.0)):
            with self.assertRaises(UsageError) as cm:
                action(store.features_dir(self.root) / "FEAT-010-bare")
            self.assertIn("bdd state init", str(cm.exception))


class HooksSeenTest(ProjectCase):
    def test_the_fact_is_copied_into_the_state_one_way_only(self):
        self.assertFalse(state.observe_hooks(self.root, self.feature_dir))      # nothing has run hooks yet
        enforcement.touch(self.root, "s1")
        self.assertTrue(state.observe_hooks(self.root, self.feature_dir))
        self.assertTrue(state.load(self.feature_dir)["hooks_seen"])
        # Removing every marker does not make the feature forget that hooks ran while it was built.
        for marker in enforcement.marker_dir(self.root).iterdir():
            marker.unlink()
        self.assertFalse(enforcement.hooks_seen(self.root))
        self.assertTrue(state.observe_hooks(self.root, self.feature_dir))

    def test_states_written_before_the_field_existed_read_as_not_seen(self):
        data = state.load(self.feature_dir)
        data.pop("hooks_seen")
        store.write_json(state.path_of(self.feature_dir), data)
        self.assertFalse(state.observe_hooks(self.root, self.feature_dir))


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


class NextIdTest(ProjectCase):
    def test_the_next_id_follows_the_highest_in_use(self):
        self.assertEqual(state.next_id(self.root), "FEAT-008")                      # FEAT-007 is the fixture feature
        state.create(self.root, "FEAT-012", "Gap", "standard")
        self.assertEqual(state.next_id(self.root), "FEAT-013")

    def test_a_project_without_features_starts_at_one_and_ignores_stray_folders(self):
        import shutil
        shutil.rmtree(store.features_dir(self.root))
        self.assertEqual(state.next_id(self.root), "FEAT-001")
        (store.features_dir(self.root)).mkdir(parents=True)
        (store.features_dir(self.root) / "notes").mkdir()
        (store.features_dir(self.root) / "FEAT-0042-odd").mkdir()
        self.assertEqual(state.next_id(self.root), "FEAT-043")


if __name__ == "__main__":
    unittest.main()
