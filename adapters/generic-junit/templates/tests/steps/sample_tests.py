"""The sample feature (tests/features/sample.feature) as plain unittest cases.

One test per scenario; the test name contains the scenario name, which is how greenlight finds it. Delete this file with
the sample feature once you have your own.
"""
import unittest

from sample_domain import NegativeInput, add


class SampleFeature(unittest.TestCase):
    tags = ("FEAT-000",)

    def test_two_numbers_are_added(self):
        self.assertEqual(add(2, 3), 5)

    def test_a_negative_number_is_refused(self):
        with self.assertRaises(NegativeInput):
            add(-1, 3)


if __name__ == "__main__":
    unittest.main()
