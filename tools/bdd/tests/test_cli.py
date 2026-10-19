import io
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from bddlib.cli import configure_streams

MAIN = Path(__file__).resolve().parents[1] / "main.py"
WRAPPER = MAIN.parent / "bdd"

CR, LF = chr(13), chr(10)
CHECK_MARK, ZH = chr(0x2713), chr(0x4E2D) + chr(0x6587)  # a check mark and "中文"


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


class OutputFormatTest(unittest.TestCase):
    """Output must be identical from PowerShell, cmd and Git Bash: UTF-8 bytes, LF endings."""

    def test_stream_becomes_utf8_with_lf_even_on_a_legacy_codepage_console(self):
        text = f"ok {CHECK_MARK} {ZH}{LF}"
        for legacy in ("cp950", "cp1252", "cp437"):
            with self.subTest(codepage=legacy):
                raw = io.BytesIO()
                stream = io.TextIOWrapper(raw, encoding=legacy, newline=CR + LF)  # a Windows pipe
                configure_streams(stream)
                stream.write(text)
                stream.flush()
                self.assertEqual(raw.getvalue(), text.encode("utf-8"))

    def test_wrapper_output_has_no_carriage_returns_under_a_legacy_codepage(self):
        sh = shutil.which("sh")
        if not sh:
            self.skipTest("needs sh")
        env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        r = subprocess.run([sh, str(WRAPPER), "--version"], capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(CR.encode(), r.stdout)


if __name__ == "__main__":
    unittest.main()
