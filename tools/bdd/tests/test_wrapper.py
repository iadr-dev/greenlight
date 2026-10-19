"""Scenario tests for tools/bdd/bdd (the interpreter-resolving sh wrapper)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[1] / "bdd"
SH = shutil.which("sh")
REAL_PY = sys.executable.replace("\\", "/")


def write_script(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_bytes(("#!/bin/sh\n" + body + "\n").encode())  # LF even on Windows
    path.chmod(0o755)


@unittest.skipUnless(SH, "needs a POSIX sh")
class WrapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cache = self.tmp / "cache"
        self.fake = self.tmp / "fake"
        self.fake.mkdir()

    def run_wrapper(self, path_dirs, *args):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_DATA"}
        env["GREENLIGHT_CACHE_DIR"] = str(self.cache)
        env["PATH"] = os.pathsep.join(str(d) for d in path_dirs)
        return subprocess.run([SH, str(WRAPPER), *args], capture_output=True, text=True,
                              env=env, timeout=60)

    def failing_pythons(self, *names):
        for n in names:
            write_script(self.fake, n, "exit 9")  # what the Microsoft Store stub effectively does

    def test_normal_machine(self):
        r = self.run_wrapper([os.path.dirname(sys.executable), *os.environ["PATH"].split(os.pathsep)], "--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("bdd "))

    def test_store_stub_first_then_py_launcher(self):
        self.failing_pythons("python3", "python")
        write_script(self.fake, "py", f'shift\nexec "{REAL_PY}" "$@"')  # emulates `py -3`
        r = self.run_wrapper([self.fake, *os.environ["PATH"].split(os.pathsep)], "--version")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_python_gives_actionable_message(self):
        self.failing_pythons("python3", "python", "py")
        r = self.run_wrapper([self.fake], "--version")
        self.assertEqual(r.returncode, 127)
        self.assertIn("no Python 3.11+ found", r.stderr)
        self.assertIn("bdd doctor", r.stderr)

    def test_interpreter_is_cached_and_reused_without_path(self):
        r1 = self.run_wrapper([os.path.dirname(sys.executable), *os.environ["PATH"].split(os.pathsep)], "--version")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertTrue((self.cache / "python-path").exists())
        self.failing_pythons("python3", "python", "py")
        r2 = self.run_wrapper([self.fake], "--version")  # PATH has no usable python
        self.assertEqual(r2.returncode, 0, r2.stderr)

    def test_no_home_and_no_cache_vars_never_uses_shared_tmp(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_PLUGIN_DATA", "GREENLIGHT_CACHE_DIR", "HOME")}
        r = subprocess.run([SH, str(WRAPPER), "--version"], capture_output=True, text=True,
                           env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)  # still works, just uncached
        leaked = subprocess.run([SH, "-c", "[ -e /tmp/.cache/greenlight/python-path ]"])
        self.assertNotEqual(leaked.returncode, 0, "wrapper wrote its cache under shared /tmp")

    def test_stale_cache_is_reprobed(self):
        self.cache.mkdir()
        (self.cache / "python-path").write_text("/no/such/python\n")
        r = self.run_wrapper([os.path.dirname(sys.executable), *os.environ["PATH"].split(os.pathsep)], "--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("/no/such", (self.cache / "python-path").read_text())


if __name__ == "__main__":
    unittest.main()
