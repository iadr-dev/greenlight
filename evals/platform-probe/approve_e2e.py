#!/usr/bin/env python3
"""Live check of the approval path inside Claude Code.

Builds a throwaway project with the rules ready to approve, loads this repository as the plugin and
types `/greenlight:approve FEAT-001 rules` into a headless session (Haiku). Then checks that the
hook recorded the approval with its prompt id and transcript path, and that verifying it against the
real transcript classifies the prompt as headless (a `claude -p` prompt is not typed by a person), so
the gates do not accept it unless the project opts in.

    python evals/platform-probe/approve_e2e.py

Exit code 0 only if every check passes. Needs `claude` on PATH and working credentials; it makes one
small model call. Not part of CI. Run it after changing the approval hook or the transcript check,
and after Claude Code upgrades.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "bdd"))

from bddlib import approvals, gates, state  # noqa: E402

SPEC = "@FEAT-001\nFeature: A\n  @R-1.1 @EX-1.1.1\n  Scenario: S\n    Then the request succeeds\n"


def build_project() -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="greenlight-approve-")).resolve()
    (root / ".bdd").mkdir()
    (root / ".bdd" / "config.toml").write_text('[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n',
                                               encoding="utf-8")
    (root / "features").mkdir()
    (root / "features" / "a.feature").write_text(SPEC, encoding="utf-8", newline="\n")
    feature_dir = state.create(root, "FEAT-001", "A", "standard")
    (feature_dir / "rules.md").write_text("# Rules\n\nR-001.1 Something holds.\n", encoding="utf-8", newline="\n")
    gates.record_gate(root, feature_dir, "discover", "pass", {})
    return root, feature_dir


def type_prompt(root: Path, prompt: str) -> str:
    done = subprocess.run(
        ["claude", "-p", prompt, "--plugin-dir", str(REPO), "--model", "haiku", "--setting-sources", "project",
         "--allowedTools", "Read"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=300)
    return (done.stdout or "").strip()


def main() -> int:
    if not shutil.which("claude"):
        print("claude CLI not found on PATH")
        return 2
    root, feature_dir = build_project()
    results: list[tuple[str, bool, str]] = []
    try:
        reply = type_prompt(root, "/greenlight:approve FEAT-001 rules")
        recorded = state.load(feature_dir)["approvals"]
        entry = recorded[0] if recorded else {}
        results.append(("the hook recorded one approval", len(recorded) == 1 and entry.get("gate") == "rules", reply[:200]))
        results.append(("it is hook-grade and starts pending", (entry.get("grade"), entry.get("origin")) == ("hook", "pending"),
                        str(entry)[:200]))
        results.append(("it carries the prompt id and transcript path", bool(entry.get("prompt_id") and entry.get("transcript_path")),
                        str(entry)[:200]))
        decided = approvals.verify_origins(feature_dir)
        verified = state.load(feature_dir)["approvals"][0]
        results.append(("the real transcript is found and classifies a headless prompt",
                        decided == 1 and verified["origin"] == "headless", f"{verified['origin']}: {verified.get('evidence')}"))
        problems = approvals.effective_problems(root, state.load(feature_dir), "rules")
        results.append(("the gates do not accept a headless approval", any("headless" in p for p in problems), str(problems)))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}" + ("" if ok else f"   <- {detail!r}"))
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
