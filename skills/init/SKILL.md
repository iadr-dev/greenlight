---
name: init
description: Set this repository up for greenlight - check the machine, pick and apply a test adapter, and prove the sample feature runs green. Use when the user runs /greenlight:init or asks to set up or diagnose greenlight.
---

# greenlight init

Prepare a repository for spec-driven development. Do the steps in order and show command output unchanged.
Do not change anything on the machine without asking first.

1. **Check the machine.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" doctor
   ```

   For every `WARN` or `FAIL` line, repeat its `fix:` text and offer to help. If the command cannot run (exit
   code 127) the machine has no Python 3.11 or newer: relay the message the wrapper printed and stop.
   The `deny rules` line (once the project exists) has a JSON snippet that only the person can add to
   `.claude/settings.json`; show it, explain that Claude Code applies deny rules before any hook so they hold
   even when a shell command is spelled in a way the guard cannot read, and do not try to write the file.

2. **Find the adapter.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" init --detect
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" adapter list
   ```

   Recommend one adapter from what was detected and say why. If nothing fits, say so plainly: only the adapters
   listed exist today. If the project's test runner can write a JUnit XML report, offer `generic-junit` (it is never
   suggested by detection) and tell the person they will replace its sample run command with their runner's. Ask the person to confirm the adapter and the starting autonomy level
   (`guided` reviews every gate, `standard` asks only for rules and examples; `auto` and `autopilot` are for
   trusted or hands-off work). Wait for the answer.

3. **Set the repository up.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" init --adapter NAME --autonomy LEVEL
   ```

   It creates `.bdd/` (configuration, glossary, an ignore file for machine-local data) and copies the adapter's
   files into the project without overwriting anything. List what it created.

4. **Install the adapter's requirements** if its guide says so (for `python-pytest-bdd`: `pytest` and
   `pytest-bdd`). Show the command and ask before running it; prefer the project's own tool (`uv`, `pip`,
   `poetry`).

5. **Prove it works.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" init --smoke
   ```

   It runs the sample feature and cleans up after itself. If it fails, show the output and the likely cause
   (missing requirements, wrong interpreter); do not go on until it is green.

6. **Say what comes next**: start a feature with `/greenlight:feature "<what you want>"`, see where things stand
   with `/greenlight:status`. Mention that approvals of rules and examples are typed by the person as
   `/greenlight:approve FEAT-n rules` and `/greenlight:approve FEAT-n examples`, and that the AI cannot give them.
