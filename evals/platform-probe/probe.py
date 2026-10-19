#!/usr/bin/env python3
"""Re-verify the Claude Code behaviours greenlight's design depends on.

Builds a throwaway plugin in a temp directory, runs a few cheap headless sessions
(`claude -p --model haiku`), and checks each behaviour recorded in docs/dev/platform-notes.md.
Run it after every Claude Code upgrade and before a release:

    python evals/platform-probe/probe.py

Exit code 0 only if every check passes. Needs `claude` on PATH and working credentials;
it makes a handful of small model calls. Not part of CI.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

LOG_HOOK = """import json, sys
d = json.loads(sys.stdin.read() or "{}")
rec = {k: d.get(k) for k in ("hook_event_name", "agent_type", "agent_id", "tool_name",
                             "tool_input", "prompt", "prompt_id", "transcript_path")}
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\\n")
"""

MULTI_STEP_PROMPT = (
    "Do these in order: (1) use the Skill tool for probe:ping. (2) use the Skill tool for "
    "probe:approve with args 'FEAT-2 rules'. (3) use the Agent tool to launch the analyst "
    "subagent to write a file probe-out.txt containing hi."
)
TRANSCRIPT_ROOT = Path.home() / ".claude" / "projects"
HOOK_EVENT = "hook_event_name"


def write_files(base: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def build_plugin(root: Path, log: Path) -> Path:
    plugin = root / "plugin"
    cmd = f'python -I "${{CLAUDE_PLUGIN_ROOT}}/log.py" "{log.as_posix()}"'
    shell_cmd = f'echo "BASH=[$BASH_VERSION] OSENV=[%OS%]" > "{(root / "shell.txt").as_posix()}"'
    hooks = {"hooks": {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": shell_cmd}]}],
    }}
    write_files(plugin, {
        ".claude-plugin/plugin.json": '{"name": "probe", "version": "0.0.1"}',
        "log.py": LOG_HOOK,
        "hooks/hooks.json": json.dumps(hooks),
        "agents/analyst.md": (
            "---\nname: analyst\ndescription: Probe agent. Use when asked to have the analyst write a file.\n"
            "tools: Write, Read\n---\nWrite exactly the file you are asked to write, then stop.\n"),
        "skills/approve/SKILL.md": (
            "---\nname: approve\ndescription: Record a human approval. User-only.\n"
            "disable-model-invocation: true\n---\nReply with exactly: APPROVE-SKILL-RAN $ARGUMENTS\n"),
        "skills/ping/SKILL.md": (
            "---\nname: ping\ndescription: Probe skill. Use when asked to run the ping skill.\n---\n"
            "Reply with exactly: PONG\n"),
    })
    return plugin


def claude(prompt: str, plugin: Path, cwd: Path, tools: str) -> str:
    r = subprocess.run(
        ["claude", "-p", prompt, "--plugin-dir", str(plugin), "--model", "haiku",
         "--setting-sources", "project", "--allowedTools", tools],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=300)
    return (r.stdout or "") + (r.stderr or "")


def events(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def transcript_entries(path: str) -> list[dict]:
    """Read a session transcript. Only .jsonl files under ~/.claude/projects are accepted,
    because the path comes from hook data rather than from this script."""
    resolved = Path(path).resolve()
    if resolved.suffix != ".jsonl" or not resolved.is_relative_to(TRANSCRIPT_ROOT.resolve()):
        raise ValueError(f"refusing to read transcript outside {TRANSCRIPT_ROOT}: {resolved}")
    entries = []
    for line in resolved.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass
    return entries


def content_items(entry: dict) -> list[dict]:
    content = (entry.get("message") or {}).get("content")
    return [x for x in content if isinstance(x, dict)] if isinstance(content, list) else []


@dataclass
class Probe:
    root: Path
    log: Path
    plugin: Path
    cwd: Path
    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, bool(ok), detail))

    def reset_log(self) -> None:
        self.log.write_text("")

    def typed_command(self) -> None:
        """A typed slash command reaches UserPromptSubmit as raw text; which shell runs hooks."""
        out = claude("/probe:approve FEAT-1 rules", self.plugin, self.cwd, "Bash")
        ups = [e for e in events(self.log) if e[HOOK_EVENT] == "UserPromptSubmit"]
        self.check("P5 typed slash command arrives raw in UserPromptSubmit",
                   any(e["prompt"] == "/probe:approve FEAT-1 rules" for e in ups), repr([e["prompt"] for e in ups]))
        self.check("P5 skill ran for the typed command", "APPROVE-SKILL-RAN FEAT-1 rules" in out, out[-200:])
        shell_file = self.root / "shell.txt"
        text = shell_file.read_text(encoding="utf-8", errors="replace").strip() if shell_file.exists() else ""
        self.check("P13 hooks run under bash, not cmd", "BASH=[" in text and "BASH=[]" not in text, text)

    def run_multi_step(self) -> list[dict]:
        """The model sometimes skips a step, so retry (up to 3 times) until it has attempted
        both the approve skill and the agent."""
        ev: list[dict] = []
        for _ in range(3):
            self.reset_log()
            claude(MULTI_STEP_PROMPT, self.plugin, self.cwd, "Skill Agent Write Read")
            ev = events(self.log)
            seen = [e["tool_name"] for e in ev if e[HOOK_EVENT] == "PreToolUse"]
            if seen.count("Skill") >= 2 and "Agent" in seen and "Write" in seen:
                break
        return ev

    def model_paths(self) -> None:
        """Model-invoked skills and subagents."""
        ev = self.run_multi_step()
        writes = [e for e in ev if e[HOOK_EVENT] == "PreToolUse" and e["tool_name"] == "Write"]
        self.check("P3 plugin agent reports agent_type 'probe:analyst'",
                   bool(writes) and writes[0]["agent_type"] == "probe:analyst", repr([w["agent_type"] for w in writes]))
        ups = [e for e in ev if e[HOOK_EVENT] == "UserPromptSubmit"]
        self.check("P6 model-invoked skill fires no UserPromptSubmit of its own",
                   not any((e["prompt"] or "").startswith("APPROVE-SKILL-RAN") for e in ups))
        path = next((e["transcript_path"] for e in ev if e["transcript_path"]), None)
        entries = transcript_entries(path) if path else []
        self.check_refused_skill(entries)
        self.check_origins(entries, ups)

    def check_refused_skill(self, entries: list[dict]) -> None:
        use_id = next((x["id"] for en in entries for x in content_items(en)
                       if x.get("type") == "tool_use" and x.get("name") == "Skill"
                       and "approve" in json.dumps(x.get("input"))), None)
        refused = any(x.get("type") == "tool_result" and x.get("tool_use_id") == use_id and x.get("is_error")
                      for en in entries for x in content_items(en))
        self.check("P7 disable-model-invocation refuses the model's Skill call", use_id is not None and refused)

    def check_origins(self, entries: list[dict], ups: list[dict]) -> None:
        notif = [en for en in entries
                 if en.get("type") == "user" and "<task-notification>" in json.dumps(en.get("message"))]
        self.check("P14 task-notification prompts are marked origin.kind=task-notification (and also fire the hook)",
                   bool(notif) and (notif[0].get("origin") or {}).get("kind") == "task-notification"
                   and any("<task-notification>" in (e["prompt"] or "") for e in ups))
        sdk = next((en for en in entries if en.get("type") == "user" and en.get("promptSource")), None)
        self.check("P14 headless prompts are marked promptSource=sdk", bool(sdk) and sdk["promptSource"] == "sdk",
                   repr(sdk and sdk.get("promptSource")))

    def loop_scheduling(self) -> None:
        """A typed /loop is a user command (no Skill call) that schedules through CronCreate;
        a model-chosen /loop would go Skill -> CronCreate. The guard covers both."""
        self.reset_log()
        claude("/loop 7m say hi", self.plugin, self.cwd, "ToolSearch CronCreate ScheduleWakeup Skill")
        tools = {e["tool_name"] for e in events(self.log) if e[HOOK_EVENT] == "PreToolUse"}
        self.check("P16 /loop schedules through CronCreate", "CronCreate" in tools, repr(sorted(tools)))


def report(results: list[tuple[str, bool, str]]) -> int:
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}" + ("" if ok or not detail else f"   <- {detail}"))
    print("\nNot checkable headless: a model-scheduled cron prompt fires UserPromptSubmit with "
          "turnOrigin=scheduled (docs/dev/platform-notes.md P6). Re-test interactively.")
    return 0 if all(ok for _, ok, _ in results) else 1


def main() -> int:
    if not shutil.which("claude"):
        print("claude CLI not found on PATH")
        return 2
    root = Path(tempfile.mkdtemp(prefix="greenlight-probe-"))
    try:
        log = root / "log.jsonl"
        cwd = root / "proj"
        cwd.mkdir()
        probe = Probe(root, log, build_plugin(root, log), cwd)
        probe.typed_command()
        probe.model_paths()
        probe.loop_scheduling()
        return report(probe.results)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
