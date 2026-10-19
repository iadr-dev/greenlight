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

Requires Python 3.11+ (standard library only) and `sh` (Git Bash on Windows). Run
`/greenlight:init` to check your machine.
