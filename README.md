# greenlight

**AI × BDD spec-driven development for Claude Code.** greenlight turns a feature request into human-approved,
executable specifications, and then into working code. People approve the contract (rules and examples); the AI does
the mechanical work in between, under gates it cannot talk its way past.

```text
request ─▶ rules ─▶ examples ─▶ system map + design ─▶ red tests ─▶ green code ─▶ audit report
            you       you          (checked)           (proved)     (proved)       (evidence)
```

- **You approve the contract.** Rules and examples are approved only by what you type
  (`/greenlight:approve FEAT-n rules`), verified against the session transcript.
- **Tests come first, and red must be real.** A recorded run must fail for the intended reason before any code is
  written; a broken test is not a red.
- **Evidence is bound.** Approved specs, steps, drivers and the test runner's own settings are locked; the interpreter,
  environment and recorded runs are checked; a tripwire notices tampering whatever command caused it.
- **Other agent tools too.** `bdd install-skills claude|codex|agents-md` installs the instructions for Claude Code
  without the plugin, for Codex, and for anything that reads `AGENTS.md`, in soft mode (detected, not prevented), with
  the same `bdd` checks; `--uninstall` takes them away again.
- **Deterministic work is code, not prompts.** Lint, trace, locks, gates and classification are the `bdd` command line
  (Python 3.11+, standard library only).
- **Traceable.** `@FEAT-n`, `@R-n.m` and `@EX-n.m.k` tags tie every rule to its examples, tests and code.

> Status: pre-release (0.1.0 in preparation). One adapter exists: `python-pytest-bdd`. See
> [CHANGELOG.md](CHANGELOG.md).

## Install

```text
/plugin marketplace add iadr-dev/greenlight
/plugin install greenlight@greenlight
```

Requires Python 3.11+ (standard library only) and a POSIX `sh`: native on Linux and macOS, Git for Windows on Windows.
It does not matter whether you start `claude` from PowerShell, cmd or Git Bash; with Git installed, hooks always run in
Git Bash. Without Git for Windows greenlight still works, but only with soft enforcement.

## Use

```text
/greenlight:init                                  # check the machine, pick an adapter, prove the sample runs
/greenlight:feature "what you want"               # run a feature through the phases
/greenlight:approve FEAT-001 rules                # you, after reading rules.md
/greenlight:approve FEAT-001 examples             # you, after reading the scenarios
/greenlight:adopt "orders module"                 # describe code that already exists, change nothing
/greenlight:status                                # where everything stands
/greenlight:change FEAT-001 "what changes, why"   # change approved work, keeping the history
```

## Documentation

- [Quickstart](docs/quickstart.md): install to verified feature
- [Concepts](docs/concepts.md): phases, gates, locks, autonomy levels, enforcement
- [Vocabulary](docs/vocabulary.md): the step phrases scenarios are written from
- [Adapters](docs/adapters.md): test stacks, which Python runs the tests
- [CI](docs/ci.md): re-check locks, the green run and traceability in a pipeline
- [Upgrading](docs/upgrading.md), [FAQ](docs/faq.md), [Troubleshooting](docs/troubleshooting.md)
- [A filled-in example feature](docs/examples/order-discounts)
- For contributors: [CLAUDE.md](CLAUDE.md), [design decisions](docs/dev/decisions.md), [platform notes](docs/dev/platform-notes.md)

## License

MIT
