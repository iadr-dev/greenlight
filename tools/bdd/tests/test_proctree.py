"""A command that runs too long is stopped together with everything it started, and the wait for its output is bounded.

``subprocess.run(timeout=...)`` kills only the process it started. On Windows it then reads the pipes again without a
limit, so a grandchild that still holds them (the Java process under ``gradlew.bat``, a build daemon) keeps the call
blocked for as long as it lives. These tests start such a grandchild and check that the run ends, and that the
grandchild does not.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bddlib import proctree, runner
from bddlib.errors import UsageError

# The grandchild inherits the pipes and rewrites a heartbeat file until a stop file appears (a stray one ends by itself
# after a minute). Its parent starts it, says something and then waits.
GRANDCHILD = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "beat, born = Path(sys.argv[1]), time.time()\n"
    "while time.time() - born < 60 and not Path(sys.argv[1] + '.stop').exists():\n"
    "    beat.write_text(str(time.time()))\n"
    "    time.sleep(0.2)\n"
)
START = "subprocess.Popen([sys.executable, '-c', " + repr(GRANDCHILD) + ", sys.argv[1]])\n"
CHILD = "import subprocess, sys, time\nprint('before the hang', flush=True)\n" + START + "time.sleep(120)\n"
# The same, but the child ends at once and only the grandchild keeps the pipes.
LEAVER = CHILD.replace("time.sleep(120)\n", "print('done', flush=True)\n")
# The same, but the grandchild has left the child's process group, as a daemon may.
DETACHED = CHILD.replace("subprocess.Popen([", "subprocess.Popen(start_new_session=True, args=[")


class Heartbeat:
    """The file a stray grandchild keeps rewriting while it lives."""

    def __init__(self, folder: str):
        self.path = Path(folder) / "beat"
        self.stop = Path(folder) / "beat.stop"

    def wait_until_alive(self, seconds: float = 20.0) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.path.is_file() and self.path.read_text(encoding="utf-8"):
                return
            time.sleep(0.05)
        raise AssertionError("the grandchild never started")

    def is_alive(self) -> bool:
        before = self.path.read_text(encoding="utf-8")
        time.sleep(1.0)
        return self.path.read_text(encoding="utf-8") != before

    def end(self) -> None:
        """Let a grandchild that is still running finish, so that the folder can be removed."""
        self.stop.write_text("stop", encoding="utf-8")
        time.sleep(0.5)


class TreeCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = tmp.name
        self.beat = Heartbeat(self.folder)
        self.addCleanup(self.beat.end)               # runs before the folder is removed


class RunTreeTest(TreeCase):
    def test_the_status_and_both_streams_come_back_and_stdin_is_empty(self):
        code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3 + len(sys.stdin.read()))"
        done = proctree.run([sys.executable, "-c", code], timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip(), done.stderr.strip()), (3, "out", "err"))

    def test_a_timeout_stops_the_grandchildren_and_does_not_wait_for_them(self):
        started = time.perf_counter()
        with self.assertRaises(proctree.TimedOut) as caught:
            proctree.run([sys.executable, "-c", CHILD, str(self.beat.path)], timeout=3)
        self.assertLess(time.perf_counter() - started, 30, "the call waited for the grandchild's pipes")
        self.assertIn("before the hang", caught.exception.stdout)
        self.beat.wait_until_alive()
        self.assertFalse(self.beat.is_alive(), "the grandchild survived the timeout")

    def test_a_command_that_has_finished_is_not_held_by_a_grandchild_that_keeps_the_pipes(self):
        started = time.perf_counter()
        done = proctree.run([sys.executable, "-c", LEAVER, str(self.beat.path)], timeout=60, grace=1)
        self.assertLess(time.perf_counter() - started, 30)
        self.assertEqual((done.returncode, done.stdout.split()), (0, ["before", "the", "hang", "done"]))
        self.beat.wait_until_alive()
        self.assertTrue(self.beat.is_alive(), "a finished command's background process is not ours to stop")

    @unittest.skipIf(os.name == "nt", "a child cannot leave a Windows job unless it asks to")
    def test_a_grandchild_outside_the_group_does_not_keep_the_wait_going(self):
        started = time.perf_counter()
        with self.assertRaises(proctree.TimedOut):
            proctree.run([sys.executable, "-c", DETACHED, str(self.beat.path)], timeout=2, grace=1)
        self.assertLess(time.perf_counter() - started, 30)


class ExecuteTest(TreeCase):
    """``runner.execute`` is what ``bdd run``, the quality checks and the mutation check start their commands with."""

    def test_a_run_that_times_out_ends_and_leaves_no_process_behind(self):
        started = time.perf_counter()
        with self.assertRaises(UsageError) as caught:
            runner.execute([sys.executable, "-c", CHILD, str(self.beat.path)], Path(self.folder), 3)
        self.assertLess(time.perf_counter() - started, 30)
        self.assertIn("took longer than 3 s", str(caught.exception))
        self.beat.wait_until_alive()
        self.assertFalse(self.beat.is_alive())


if __name__ == "__main__":
    unittest.main()
