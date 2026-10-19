# Platform notes — verified Claude Code facts

> Rows labelled P1–P16 are referenced from code comments and decisions. Re-run the probes
> on every Claude Code upgrade.

Checked 2026-10-19 against code.claude.com docs and Claude Code 2.1.286 on Windows 11.
Re-check these against the then-current docs on every Claude Code upgrade. Rows marked **tested** were confirmed
by experiment with a throwaway probe plugin (`claude -p --plugin-dir`, Haiku, temp folder).

| # | Question | Answer | Source | Plan impact |
|---|---|---|---|---|
| P1 | Can subagents spawn subagents? | Yes, up to 3 levels by default (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`) | [sub-agents](https://code.claude.com/docs/en/sub-agents.md) | Not a constraint |
| P2 | Can subagents ask the user (AskUserQuestion)? | **No** — always removed from subagents | [sub-agents](https://code.claude.com/docs/en/sub-agents.md) | Orchestrator stays in the main session (D8) |
| P3 | Does PreToolUse input identify the calling agent? | Yes: `agent_id`, `agent_type`. **Tested:** plugin agents report `agent_type = "<plugin>:<agent>"` (probe → `probe:analyst`); main-session calls have no `agent_type` | [hooks](https://code.claude.com/docs/en/hooks) + experiment | `bdd guard` keys path limits on `greenlight:<agent>`; absent = orchestrator |
| P4 | Does frontmatter support path-restricted tools? | No — `tools` / `disallowedTools` are by tool name only | [components](https://code.claude.com/docs/en/plugins/components.md) | Path limits live in `bdd guard` (P3) |
| P5 | UserPromptSubmit payload | Fields: `cwd`, `hook_event_name`, `permission_mode`, `prompt`, `prompt_id`, `session_id`, `transcript_path`. **Tested:** a typed `/probe:approve FEAT-1 rules` arrives unexpanded as exactly that text | [hooks](https://code.claude.com/docs/en/hooks) + experiment | Approval writer parses `prompt`; stores `prompt_id` |
| P6 | Can the model trigger UserPromptSubmit? | Model-invoked skills: **no** (tested: Skill-tool call fired no event). **But tested: UserPromptSubmit also fires for system-injected prompts** — a background subagent's `<task-notification>` (which embeds the subagent's result text) arrived as a UserPromptSubmit with identical fields. **Tested (interactive): a model-scheduled CronCreate prompt also fires UserPromptSubmit**, with exactly the model-written text and the same payload fields as a typed prompt. | experiment | Approval needs 3 defences — see the approval-provenance design in docs/. Payload alone can't tell human from system |
| P7 | User-only skills | `disable-model-invocation: true`. **Tested:** model's Skill-tool call to such a skill is refused | [skills](https://code.claude.com/docs/en/skills.md) + experiment | `approve` skill sets it |
| P8 | Hook exit codes | 0 = ok (stdout may be JSON with `hookSpecificOutput.permissionDecision`: allow/deny/ask/defer); 2 = block (PreToolUse and UserPromptSubmit), stderr shown; other = non-blocking unless `onFailure: "block"` | [hooks](https://code.claude.com/docs/en/hooks) | Guard uses exit 2; approve hook uses exit 0 so the prompt still runs |
| P9 | Plugin env vars | `${CLAUDE_PLUGIN_ROOT}` (install dir); `${CLAUDE_PLUGIN_DATA}` (persistent per-plugin dir, survives updates) | [manifest-reference](https://code.claude.com/docs/en/plugins/manifest-reference.md) | Wrapper caches the resolved interpreter in `${CLAUDE_PLUGIN_DATA}` |
| P10 | Plugin layout | `.claude-plugin/plugin.json` optional; auto-discovers `skills/`, `agents/`, `hooks/hooks.json`, `.mcp.json`; marketplace plugin `"source": "./"` | [create](https://code.claude.com/docs/en/plugins/create.md), [marketplace-reference](https://code.claude.com/docs/en/plugins/marketplace-reference.md) | Matches plan; still ship `plugin.json` for metadata |
| P11 | `bin/` on PATH | Yes for the Bash tool, **but** claude.ai and Cowork refuse to install plugins with a top-level `bin/` | [components](https://code.claude.com/docs/en/plugins/components.md) | Wrapper lives at `tools/bdd/bdd`, not `bin/`, to keep those install paths open |
| P12 | `claude plugin eval` | Exists (GA). Each case runs in a fresh session, N times (default 3); graders: regex, tool_used, tool_order, file_exists, llm, baseline; compares with-plugin vs no-plugin; HTML + JSON output; non-zero exit below threshold | [plugin-evals](https://code.claude.com/docs/en/plugins/plugin-evals.md) | Eval layer uses it |
| P13 | Shell that runs hook commands on Windows | **Tested** from Git Bash and from PowerShell: hooks ran under Git Bash (bash 5.3; `%OS%` not expanded, so not cmd) both times, so the terminal you launch `claude` from does not matter. **Docs:** Git for Windows is optional; with it, hooks and the Bash tool use Git Bash; **without it Claude Code falls back to PowerShell**. A per-hook `"shell"` field exists. A `cmd.exe` launch was not tested (quoting problem in the harness) | experiment + [setup](https://code.claude.com/docs/en/setup.md#install-on-native-windows), [tools-reference](https://code.claude.com/docs/en/tools-reference.md) | Hooks call `sh .../tools/bdd/bdd`, so hard enforcement on Windows needs Git for Windows (D11). Without it the plugin still works in soft mode |
| P14 | Does the transcript record where a prompt came from? | **Tested, undocumented fields.** Each user entry has `promptId` (= hook `prompt_id`) and origin metadata: typed interactive → `promptSource: "typed"`, `origin.kind: "human"`; headless `-p` → `promptSource: "sdk"`; task notification → `promptSource: "system"`, `origin.kind: "task-notification"`; CronCreate prompt and ScheduleWakeup prompt → `promptSource: "system"`, `turnOrigin: "scheduled"`, `isMeta: true`, no `origin`; subagent/peer message → `promptSource: "system"`, `origin.kind: "peer"`. **Real incident in this planning session:** two model-scheduled wakeups carrying the text of an earlier user message were indistinguishable from the user to the model itself; only these fields told them apart | experiment (this repo's own session + probe) | Provenance check: look up `prompt_id` in the transcript and accept only `origin.kind == "human"` (or `promptSource == "sdk"` in headless runs, labelled `headless`). Undocumented → re-verify on every Claude Code upgrade (re-check before each release) |
| P15 | Codex skill format | **Tested:** Codex 0.142 discovers `~/.codex/skills/<name>/SKILL.md` and project `.agents/skills/<name>/SKILL.md`; same `name`/`description` frontmatter; the model is given the SKILL.md absolute path. Feature flags: `hooks` stable, `multi_agent` stable, `plugin_hooks` **removed** | `codex debug prompt-input`, `codex features list` | Soft mode works in Codex. Skill names are not namespaced there → install with `greenlight-` prefix. Hard mode in Codex would need user-configured hooks (not plugin-shipped) — v2 |
| P16 | Other prompt-injection paths | **Tested:** `/loop` is a model-invocable skill and schedules via `CronCreate` (`{"cron": "*/7 * * * *", "prompt": …}`); ToolSearch for "remote trigger" returns only `SendMessage` (no RemoteTrigger tool in Claude Code 2.1.286) | experiment | Guard `--inject` matcher = `CronCreate\|ScheduleWakeup\|SendMessage\|Skill` |

## Harness pitfall (Windows)

Git Bash rewrites a leading-slash argument such as `/loop 7m say hi` into
`C:/Program Files/Git/loop 7m say hi` before `claude -p` sees it (MSYS path conversion).
`/probe:approve …` was not rewritten, probably because of the colon, but don't rely on that.
Eval and probe scripts must set `MSYS_NO_PATHCONV=1` when passing slash commands to
`claude -p`. Interactive typing is unaffected.

## Measured on this Windows machine

| Measurement | Result |
|---|---|
| Interpreters present | `python` and `py` (3.14.6); **no `python3`** |
| `python -c pass` cold-ish start | 130–360 ms |
| `python -I -c pass` (isolated mode) | 82–125 ms |
| Git Bash `sh -c` spawn alone | ~115 ms |
| sh wrapper → python | 126–158 ms |

Consequences:
- Always start the CLI with `python -I` (isolated mode is ~2–3× faster here and ignores
  user site-packages, which also helps determinism).
- The hook budget is **< 200 ms on macOS/Linux, < 300 ms on Windows**, measured with `bdd doctor`.
  PreToolUse runs on every Edit/Write/Bash, so this matters.
- Hooks run under Git Bash on Windows when Git for Windows is installed (P13), so the sh wrapper works there; without Git, hard enforcement is unavailable (D11).
| P17 | Windows console encoding | **Tested:** `claude -p` output is UTF-8, but Python on a Windows pipe decodes/encodes with the console code page (cp950 here) and writes CRLF; a probe crashed with `UnicodeDecodeError`. | experiment | The CLI forces UTF-8 + LF on stdout/stderr and runs with `-X utf8`; scripts that read tool output must pass `encoding="utf-8"` |
