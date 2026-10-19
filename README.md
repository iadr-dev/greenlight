# greenlight

**AI × BDD spec-driven development for Claude Code.** greenlight turns a feature request
into human-approved, executable specifications, and then into working code. People approve
the contract (rules and examples); the AI does the mechanical work in between, under gates
it cannot talk its way past.

> Status: early development. Only `/greenlight:init` (an environment check) exists so far.
> See [CHANGELOG.md](CHANGELOG.md).

## Install

```text
/plugin marketplace add iadr-dev/greenlight
/plugin install greenlight@greenlight
```

Requires Python 3.11+ (standard library only) and a POSIX `sh`: native on Linux and macOS,
Git for Windows on Windows. It does not matter whether you start `claude` from PowerShell,
cmd or Git Bash; with Git installed, hooks always run in Git Bash. Without Git for Windows
greenlight still works, but only with soft enforcement. Run `/greenlight:init` to check
your machine.
