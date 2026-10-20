# Upgrading

## The plugin

Update greenlight from the `/plugin` menu (marketplace `greenlight`), or remove and add it again:

```text
/plugin marketplace add iadr-dev/greenlight
/plugin install greenlight@greenlight
```

Restart the Claude Code session afterwards so the hooks and skills are reloaded. `/greenlight:init` (or `bdd doctor`)
re-checks the machine.

## Your project's `.bdd/`

`.bdd/` has a schema version (`version` in `.bdd/config.toml`; absent means 1).

- A project **newer** than the installed greenlight is refused by every command with a message to upgrade greenlight.
- A project **older** than the installed greenlight is refused by the commands that read or write its data until you run:

```sh
bdd migrate --dry-run     # say what would happen, change nothing
bdd migrate               # copy .bdd/ to .bdd-backup-v<N>, run the steps, bump the version after each
```

If a step fails the project stays at the last good version and the backup is untouched. The hooks never run this
check, so an out-of-date project does not block your prompts. There has been no schema change yet: version 1 is the
first.

## Adapter files

Files the adapter copied into your project (`tests/steps/core_steps.py`, drivers, `pytest.ini`) are yours after
copying and are never overwritten. A new greenlight may ship improved templates; compare them with
`adapters/<name>/templates/` and merge what you want. The CHANGELOG says when a template changed.

## After a Claude Code upgrade

Hooks run under Git Bash on Windows. After upgrading Claude Code, `bdd doctor` re-measures the hook latency (budget:
300 ms on Windows, 200 ms on macOS and Linux) and checks the tools greenlight needs.
