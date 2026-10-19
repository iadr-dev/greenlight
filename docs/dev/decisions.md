# Decisions

Record of design decisions. Add a row (or a section below) for every new one, with the reason.

| # | Decision | Status / rationale |
|---|---|---|
| D1 | File formats | **Decided:** TOML for human-edited files (`config.toml`, `vocabulary.toml`, `adapter.toml`) via stdlib `tomllib`; JSON for tool-owned files (`core.json`, `state.json`, `lock.json`, card index); flat YAML-style frontmatter only where Claude Code/Codex require it. Requires **Python 3.11+**, which is fine because 3.10 reached end-of-life in Oct 2026 |
| D2 | Python vs Node for the CLI | Python stdlib behind the `tools/bdd/bdd` wrapper; revisit if Windows hook latency or interpreter discovery is poor |
| D3 | Where `.feature` files live | **Decided:** adapter default paths, overridable per adapter in `config.toml` |
| D4 | Gherkin language default | **Decided:** follow the user's language (`language = "auto"`); IDs, tags and file names stay ASCII |
| D5 | Plugin name | **Decided:** `greenlight` for plugin, marketplace and GitHub repo (`iadr-dev/greenlight`). Commands `/greenlight:<skill>`, agents `greenlight:<agent>`, soft-mode stubs `greenlight-<skill>`. Chosen over bdd-forge/bdd-x-ai because "AI × BDD" names are common and "greenlight" describes the approval gate and red → green |
| D6 | License | **Decided:** MIT |
| D7 | Human approval mechanism | **Decided:** `UserPromptSubmit` hook with whole-prompt strict match + `disable-model-invocation: true` + guard denying scheduled approve text + transcript origin check (tests showed system-injected prompts also fire the hook — platform-notes P6, P14) |
| D8 | Orchestrator placement | **Decided:** `feature` skill in the main session, because subagents can't ask the user (P2) |
| D9 | Wrapper location | **Decided:** `tools/bdd/bdd`, not top-level `bin/`, so claude.ai/Cowork can still install the plugin (P11) |
| D10 | Skill count | **Decided:** 6 user-typed skills; phases are playbooks in `phases/` |
| D11 | Windows shells | **Decided:** hooks are POSIX `sh` commands, so hard enforcement on Windows requires Git for Windows (Claude Code then runs hooks in Git Bash whichever terminal launched it, platform-notes P13). Without Git, Claude Code uses PowerShell for hooks and the `sh` wrapper cannot run: greenlight works in soft mode and `bdd doctor` says how to get hard mode. Linux and macOS use their native `sh`. All CLI output is UTF-8 with LF endings regardless of terminal (P17) |
| D12 | Guard failure modes | **Decided:** the guard *fails closed* when it cannot read lock data (corrupt or newer-schema `lock.json` blocks edits with an explanation), because treating an unreadable lock as "no lock" would let a corrupted file switch enforcement off. It *fails open* with a visible warning for anything else it cannot evaluate (unparseable hook input, unexpected error), so a bug in greenlight never locks a person out of their own project |
| D13 | Shell-command protection | **Decided:** best effort, matched on file names anywhere in the command text (any quoting or slash style, including paths built inside a Python one-liner), only when the command also looks like a write. It cannot foresee everything a shell can do (`git checkout main` may revert a file), so the hash check at the implement and verify gates is the guarantee and the hook is the first line of defence |
