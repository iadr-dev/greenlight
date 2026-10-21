"""A real Codex session against greenlight's hooks. Opt in: it needs a signed-in Codex and uses your account.

Codex runs a project's hooks only once a person has trusted them and ``codex exec`` cannot ask, so the folder is yours:

1. Pick an empty folder and set ``GREENLIGHT_LIVE_CODEX=1`` and ``GREENLIGHT_LIVE_CODEX_DIR=<that folder>``.
2. Run ``python -m unittest tests.test_codex_live``. The first run prepares the folder (adapter, a locked sample spec, the
   project's Codex hooks) and skips with a message.
3. In that folder start ``codex`` interactively, review the greenlight hooks (their command is ``sh ".../bdd" codex-hook``),
   trust them and leave.
4. Run the test again. It asks Codex to append a line to the locked feature file and checks that the file is unchanged and that
   Codex was told the call was blocked by the PreToolUse hook.

What it checked by hand on 2026-10-21 with codex-cli 0.142.3 on Windows: a hook that exits 2 with the reason on stderr did
not stop the edit, a hook that prints a ``permissionDecision: deny`` decision on stdout and exits 0 did.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from bddlib import adapter, cli, lockfile, state

FOLDER = os.environ.get("GREENLIGHT_LIVE_CODEX_DIR")
LIVE = os.environ.get("GREENLIGHT_LIVE_CODEX") == "1" and bool(FOLDER) and shutil.which("codex") is not None
PROMPT = ("Append one new line containing the text '# edit' to the end of the file {path} using a shell edit. "
          "If anything blocks or refuses, tell me the exact message. Do nothing else.")


@unittest.skipUnless(LIVE, "opt in with GREENLIGHT_LIVE_CODEX=1 and a signed-in codex on PATH")
class LiveCodexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(FOLDER).resolve()
        cls.spec = cls.root / "tests" / "features" / "sample.feature"
        cls.prepared = (cls.root / ".bdd").is_dir()
        if cls.prepared:
            return
        cls.root.mkdir(parents=True, exist_ok=True)
        (cls.root / ".bdd").mkdir()
        subprocess.run(["git", "init", "-q", str(cls.root)], check=True)
        adapter.apply(cls.root, "python-pytest-bdd")
        feature_dir = state.create(cls.root, "FEAT-000", "Sample", "standard")
        lockfile.lock(cls.root, feature_dir, "FEAT-000", "spec", [cls.spec])
        here = os.getcwd()
        os.chdir(cls.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(["install-hooks", "codex", "--project", "--apply"])
        finally:
            os.chdir(here)

    def test_a_locked_spec_cannot_be_edited_through_codex(self):
        if not self.prepared:
            self.skipTest(f"prepared {self.root}: trust the hooks once in an interactive `codex` session there, then run again")
        before = self.spec.read_bytes()
        done = subprocess.run(["codex", "exec", "--json", "--skip-git-repo-check", "-s", "workspace-write",
                               PROMPT.format(path=self.spec)], cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
        messages = " ".join(json.dumps(json.loads(line)) for line in done.stdout.splitlines() if line.startswith("{"))
        if "hook" not in messages.lower() and self.spec.read_bytes() != before:
            self.skipTest(f"the hooks did not run: trust them once in an interactive `codex` session in {self.root}")
        self.assertEqual(self.spec.read_bytes(), before)
        self.assertIn("blocked by PreToolUse hook", messages)


if __name__ == "__main__":
    unittest.main()
