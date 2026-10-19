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
