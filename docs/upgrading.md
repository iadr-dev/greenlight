# Upgrading

## The plugin

Update greenlight from the `/plugin` menu (marketplace `greenlight`), or remove and add it again:

```text
/plugin marketplace add iadr-dev/greenlight
/plugin install greenlight@greenlight
```

Restart the Claude Code session afterwards so the hooks and skills are reloaded. `/greenlight:init` (or `bdd doctor`)
re-checks the machine.

An update is not an integrity violation. The integrity check records which folder and which version of the plugin it
watches; at the first prompt after Claude Code runs a new version from its own plugin cache (with nothing open), it takes the new plugin's files as the baseline and `bdd doctor` says
`integrity: plugin updated from 1.2.1 to 1.2.2; baseline refreshed`. A plugin file edited in place, its version
included, is still reported. Violations an older greenlight opened for an update close by themselves at the first tool
call after you move to this version.

## Upgrading with features in progress

A new version does not edit your approved rules, examples, locks or recorded runs on its own, and a gate that already
passed stays recorded. What changes is which checks run the next time a command or a gate runs, so a feature in progress
may be asked for something it was not asked for before. Nothing here needs an edit of a JSON file.

1. Update the plugin and restart the session, as above. `bdd doctor` should print `integrity: plugin updated from X to Y`.
2. Run `bdd status`. It lists each feature with its phase and what it is waiting for.
3. If any feature was bound before 1.2.2, run `bdd migrate --dry-run`. When it says it would move the shared files of
   the bind locks into the plumbing lock, run `bdd migrate`. It makes a backup (`.bdd-backup-plumbing`), moves the shared
   test files into `.bdd/plumbing.lock.json` and leaves each feature its own steps and drivers. It refuses while a
   locked file differs from its lock, so restore that file first. Old locks keep working until then, and the gates that
   read them say `run bdd migrate`.
4. Continue each feature with `/greenlight:feature FEAT-001`. What happens depends on its phase:

| The feature is in | What the new version asks | What you do |
|---|---|---|
| discover, specify, test design | The test-design gate asks for the edge example of a `boundary-value` rule (`T009`) | Add the example, or the one-line reason, to `test-design.md` |
| examples, refine | `bdd lint` refuses two record tables of one entity with different columns (`L026`) | Fix the tables, or list the entity under `[lint] projected_records` in `.bdd/config.toml`; see [record tables](vocabulary.md#record-tables) |
| bind | `bdd classify` makes the red invalid when an `@existing` scenario failed in it | Remove the tag from the scenario that does not work yet; once the examples are approved, use `/greenlight:change` |
| implement | The gate refuses a review that has no record of the code it read | Nothing: the feature skill runs each task's reviewer once more, and the new report is sealed |
| verify | The same review check at the verify gate, and the auditor's `bdd classify FEAT-001 --run red` (checklist E4) | Go back with `/greenlight:change FEAT-001 "rerun the reviews"`, which reopens implement; approvals already given stay valid |
| done | Nothing reopens | CI runs `bdd lint` over every feature file, so `L026` can turn it red: fix the tables, or list the entity under `[lint] projected_records` |

`.bdd/config.toml` is protected from the agents, and a change to it during a session opens an integrity violation, so
edit it yourself outside the session, or accept the change with `/greenlight:approve integrity #n <reason>`. The review
check applies only where the plugin's hooks run; without them the reports are judged as before.

A plumbing change of your own is a different thing: `bdd unlock --plumbing --reason "..."`, edit, then
`bdd lock --plumbing --reason "..."`, after which every bound feature reruns its scenarios once. See
[troubleshooting](troubleshooting.md).

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
