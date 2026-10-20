"""The query counter of the Python adapter is plain Python, so it is tested without pytest or a database library."""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / "adapters" / "python-pytest-bdd" / "templates" / "tests" / "drivers" / "queries.py"


def load():
    spec = importlib.util.spec_from_file_location("greenlight_queries", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QueryCounterTest(unittest.TestCase):
    def setUp(self):
        self.counter = load().QueryCounter()

    def test_statements_are_counted_and_transaction_control_is_not(self):
        for statement in ("SELECT 1", "  select * from orders", "INSERT INTO t VALUES (1)"):
            self.counter.record(statement)
        for statement in ("SAVEPOINT s1", "RELEASE SAVEPOINT s1", "ROLLBACK TO SAVEPOINT s1", "BEGIN", " commit", "ROLLBACK"):
            self.counter.record(statement)
        self.assertEqual(self.counter.count, 3)

    def test_the_django_wrapper_counts_and_passes_the_call_on(self):
        seen = []

        def execute(sql, params, many, context):
            seen.append((sql, params, many, context))
            return "result"

        self.assertEqual(self.counter.django_wrapper(execute, "SELECT 2", (1,), False, {"k": 1}), "result")
        self.assertEqual((self.counter.count, seen), (1, [("SELECT 2", (1,), False, {"k": 1})]))


if __name__ == "__main__":
    unittest.main()
