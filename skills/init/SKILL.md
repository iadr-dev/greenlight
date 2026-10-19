---
name: init
description: Check that this machine and repository are ready for greenlight (Python 3.11+, sh, git, hook latency) and report what to fix. Use when the user runs /greenlight:init or asks to set up or diagnose greenlight.
---

# greenlight init

Scaffolding for a repository (stack detection, adapter, `.bdd/`) is not available yet.
For now this command only checks the environment.

1. Run the doctor and show its output unchanged:

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" doctor
   ```

2. For every `WARN` or `FAIL` line, repeat its `fix:` text and offer to help apply it.
   Do not change anything on the machine without asking first.
3. For the `deny rules` line: the snippet in its `fix:` has to be added to `.claude/settings.json` by the
   person (greenlight's guard refuses edits to settings files, and so must you). Show it and explain that
   Claude Code applies deny rules before any hook, so they hold even when a shell command is spelled in a way
   the guard cannot read. Do not try to write the file yourself.
4. If the command itself cannot run (exit code 127), the machine has no Python 3.11+.
   Relay the message the wrapper printed.
