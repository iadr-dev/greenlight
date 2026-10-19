import subprocess
import sys
import unittest
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "main.py"


class CliSmokeTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        # -I mirrors production: isolated mode must still find the package.
        return subprocess.run(
            [sys.executable, "-I", str(MAIN), *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_version_runs_in_isolated_mode(self):
        r = self.run_cli("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"^bdd \d+\.\d+\.\d+")

    def test_no_command_is_a_usage_error(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)


if __name__ == "__main__":
    unittest.main()
