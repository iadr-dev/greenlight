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
from pathlib import Path

LOG_HOOK = """import json, sys
d = json.loads(sys.stdin.read() or "{}")
rec = {k: d.get(k) for k in ("hook_event_name", "agent_type", "agent_id", "tool_name",
                             "tool_input", "prompt", "prompt_id", "transcript_path")}
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\\n")
"""


def build_plugin(root: Path, log: Path) -> Path:
    plugin = root / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / "hooks").mkdir()
    (plugin / "agents").mkdir()
    (plugin / "skills" / "approve").mkdir(parents=True)
    (plugin / "skills" / "ping").mkdir()
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "probe", "version": "0.0.1"}')
    (plugin / "log.py").write_text(LOG_HOOK)
    cmd = f'python -I "${{CLAUDE_PLUGIN_ROOT}}/log.py" "{log.as_posix()}"'
    shell_cmd = f'echo "BASH=[$BASH_VERSION] OSENV=[%OS%]" > "{(root / "shell.txt").as_posix()}"'
    hooks = {"hooks": {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": shell_cmd}]}],
    }}
    (plugin / "hooks" / "hooks.json").write_text(json.dumps(hooks))
    (plugin / "agents" / "analyst.md").write_text(
        "---\nname: analyst\ndescription: Probe agent. Use when asked to have the analyst write a file.\n"
        "tools: Write, Read\n---\nWrite exactly the file you are asked to write, then stop.\n")
    (plugin / "skills" / "approve" / "SKILL.md").write_text(
        "---\nname: approve\ndescription: Record a human approval. User-only.\n"
        "disable-model-invocation: true\n---\nReply with exactly: APPROVE-SKILL-RAN $ARGUMENTS\n")
    (plugin / "skills" / "ping" / "SKILL.md").write_text(
        "---\nname: ping\ndescription: Probe skill. Use when asked to run the ping skill.\n---\nReply with exactly: PONG\n")
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
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def content_items(entry: dict) -> list[dict]:
    content = (entry.get("message") or {}).get("content")
    return [x for x in content if isinstance(x, dict)] if isinstance(content, list) else []


def main() -> int:
    if not shutil.which("claude"):
        print("claude CLI not found on PATH")
        return 2
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok), detail))

    root = Path(tempfile.mkdtemp(prefix="greenlight-probe-"))
    try:
        log = root / "log.jsonl"
        plugin = build_plugin(root, log)
        cwd = root / "proj"
        cwd.mkdir()

        # 1. A typed slash command reaches UserPromptSubmit as raw text; which shell runs hooks.
        out = claude("/probe:approve FEAT-1 rules", plugin, cwd, "Bash")
        ups = [e for e in events(log) if e["hook_event_name"] == "UserPromptSubmit"]
        check("P5 typed slash command arrives raw in UserPromptSubmit",
              any(e["prompt"] == "/probe:approve FEAT-1 rules" for e in ups), repr([e["prompt"] for e in ups]))
        check("P5 skill ran for the typed command", "APPROVE-SKILL-RAN FEAT-1 rules" in out, out[-200:])
        shell_file = root / "shell.txt"
        shell_txt = shell_file.read_text(encoding="utf-8", errors="replace") if shell_file.exists() else ""
        check("P13 hooks run under bash, not cmd", "BASH=[" in shell_txt and "BASH=[]" not in shell_txt,
              shell_txt.strip())

        # 2. Model-invoked skills and subagents. The model sometimes skips a step, so retry
        #    (up to 3 times) until it has attempted both the approve skill and the agent.
        for attempt in range(3):
            log.write_text("")
            claude("Do these in order: (1) use the Skill tool for probe:ping. (2) use the Skill tool for "
                   "probe:approve with args 'FEAT-2 rules'. (3) use the Agent tool to launch the analyst "
                   "subagent to write a file probe-out.txt containing hi.", plugin, cwd, "Skill Agent Write Read")
            ev = events(log)
            tools_seen = [e["tool_name"] for e in ev if e["hook_event_name"] == "PreToolUse"]
            if tools_seen.count("Skill") >= 2 and "Agent" in tools_seen and "Write" in tools_seen:
                break
        write = [e for e in ev if e["hook_event_name"] == "PreToolUse" and e["tool_name"] == "Write"]
        check("P3 plugin agent reports agent_type 'probe:analyst'",
              bool(write) and write[0]["agent_type"] == "probe:analyst", repr([w["agent_type"] for w in write]))
        ups = [e for e in ev if e["hook_event_name"] == "UserPromptSubmit"]
        check("P6 model-invoked skill fires no UserPromptSubmit of its own",
              not any((e["prompt"] or "").startswith("APPROVE-SKILL-RAN") for e in ups))
        tp = next((e["transcript_path"] for e in ev if e["transcript_path"]), None)
        entries = transcript_entries(tp) if tp else []
        approve_use = next((x["id"] for en in entries for x in content_items(en)
                            if x.get("type") == "tool_use" and x.get("name") == "Skill"
                            and "approve" in json.dumps(x.get("input"))), None)
        refused = any(x.get("type") == "tool_result" and x.get("tool_use_id") == approve_use and x.get("is_error")
                      for en in entries for x in content_items(en))
        check("P7 disable-model-invocation refuses the model's Skill call", approve_use is not None and refused)
        notif = [en for en in entries
                 if en.get("type") == "user" and "<task-notification>" in json.dumps(en.get("message"))]
        check("P14 task-notification prompts are marked origin.kind=task-notification (and also fire the hook)",
              bool(notif) and (notif[0].get("origin") or {}).get("kind") == "task-notification"
              and any("<task-notification>" in (e["prompt"] or "") for e in ups))
        sdk = next((en for en in entries if en.get("type") == "user" and en.get("promptSource")), None)
        check("P14 headless prompts are marked promptSource=sdk", bool(sdk) and sdk["promptSource"] == "sdk",
              repr(sdk and sdk.get("promptSource")))

        # 3. A typed /loop is a user command (no Skill call) that schedules through CronCreate;
        #    a model-chosen /loop would go Skill -> CronCreate. The guard covers both.
        log.write_text("")
        claude("/loop 7m say hi", plugin, cwd, "ToolSearch CronCreate ScheduleWakeup Skill")
        tools = {e["tool_name"] for e in events(log) if e["hook_event_name"] == "PreToolUse"}
        check("P16 /loop schedules through CronCreate", "CronCreate" in tools, repr(sorted(tools)))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}" + ("" if ok or not detail else f"   <- {detail}"))
    print("\nNot checkable headless: a model-scheduled cron prompt fires UserPromptSubmit with "
          "turnOrigin=scheduled (docs/dev/platform-notes.md P6). Re-test interactively.")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
