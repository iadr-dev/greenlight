# greenlight

```text
                               ___       __    __
   ____ _________  ___  ____  / (_)___ _/ /_  / /_
  / __ `/ ___/ _ \/ _ \/ __ \/ / / __ `/ __ \/ __/
 / /_/ / /  /  __/  __/ / / / / / /_/ / / / / /_
 \__, /_/   \___/\___/_/ /_/_/_/\__, /_/ /_/\__/
/____/                         /____/
```

**AI × BDD spec-driven development for Claude Code.** greenlight turns a feature request into human-approved,
executable specifications, and then into working code. People approve the contract (rules and examples); the AI does
the mechanical work in between, under gates it cannot talk its way past (with the plugin's hooks; without them, in
soft mode, a violation is detected after the fact, not prevented).

```text
request ─▶ rules ─▶ examples ─▶ system map + design ─▶ red tests ─▶ green code ─▶ audit report
            you       you          (checked)           (proved)     (proved)       (evidence)
```

- **You approve the contract.** Rules and examples are approved only by what you type
  (`/greenlight:approve FEAT-n rules`), verified against the session transcript. You choose how much you are asked
  (see *Autonomy levels* below); at `autopilot` nothing is asked and the report is marked UNREVIEWED.
- **Tests come first, and red must be real.** A recorded run must fail for the intended reason before any code is
  written; a broken test is not a red. A feature reopened after its code exists proves its new red against the code
  as it was (`bdd run --against-red`), never by hiding the code.
- **Evidence is bound.** Approved specs, steps, drivers and the test runner's own settings are locked; the interpreter,
  environment and recorded runs are checked; a tripwire notices tampering whatever command caused it.
- **Your engineering standards are part of the gate.** `.bdd/standards.md` (language and toolchain, clean code,
  architecture, API and data rules, deprecation policy) is approved by you; your own formatter, linter and type checker
  run as `bdd check`; optional mutation and stability checks (`bdd mutate`, `bdd stability`) test the tests.
- **Seven test stacks.** Python (pytest-bdd), TypeScript web UIs (Playwright), Go (godog), .NET (Reqnroll), Spring Boot
  and Kotlin/Android (Cucumber-JVM, also on a real device), and any runner that writes a JUnit report.
- **Other agent tools too.** `bdd install-skills claude|codex|agents-md` installs the instructions for Claude Code
  without the plugin, for Codex, and for anything that reads `AGENTS.md`, in soft mode (detected, not prevented), with
  the same `bdd` checks; `bdd install-hooks codex` adds best-effort blocking through Codex's own hooks. Work done in
  Codex is never graded hard: CI and branch review are the guarantee.
- **Existing code and several repositories.** `/greenlight:adopt` describes code that already exists without changing
  it; a feature can span repositories (`[workspace]`); teams can share a pinned vocabulary.
- **Deterministic work is code, not prompts.** Lint, trace, locks, gates and classification are the `bdd` command line
  (Python 3.11+, standard library only).
- **Traceable.** `@FEAT-n`, `@R-n.m` and `@EX-n.m.k` tags tie every rule to its examples, tests and code.

> Status: 1.0. Measured results and the known limits are in the [CHANGELOG](CHANGELOG.md); the evaluation harness is
> described in [evals/README.md](evals/README.md).

## How it works

1. **Set up once.** `/greenlight:init` checks the machine, picks a test adapter and proves a sample feature runs. You
   describe and approve your engineering standards in `.bdd/standards.md`.
2. **Ask for a feature.** `/greenlight:feature "what you want"` runs the phases: discover, specify (rules), test design,
   examples (Gherkin scenarios), system map and design, then refine and bind.
3. **Approve the contract.** You read `rules.md` and the scenarios and approve each by typing
   `/greenlight:approve FEAT-n rules|examples`. Approved examples lock the feature files.
4. **Red, then green.** The steps and drivers are written and run; every new scenario must fail for the intended
   reason before any code is written. Then the code is written until the scenarios pass.
5. **Verify.** An independent auditor checks the evidence and writes `report.md`; `Verdict: PASS` means every rule has
   examples, every example has a passing test, and nothing approved or bound changed afterwards.
6. **Hand over.** `bdd check FEAT-n` runs your formatter, linter and type checker; `bdd pr FEAT-n --write` writes a
   pull-request description from the recorded facts; CI re-checks locks, approvals and traceability.
7. **Change later** with `/greenlight:change`, which reopens at the earliest phase the change touches.

### Autonomy levels

| Level | Asks you |
|---|---|
| `guided` | at every human gate, after test design, and shows the design view before binding |
| `standard` | for the rules and the examples |
| `auto` | the two approvals are recorded automatically; blocking questions still come to you |
| `autopilot` | nothing; assumptions are recorded and the report is marked UNREVIEWED |

Machine gates are never skipped at any level. Start with `guided`.

## Install

```text
/plugin marketplace add iadr-dev/greenlight
/plugin install greenlight@greenlight
```

Requires Python 3.11+ (standard library only) and a POSIX `sh`: native on Linux and macOS, Git for Windows on Windows.
It does not matter whether you start `claude` from PowerShell, cmd or Git Bash; with Git installed, hooks always run in
Git Bash. Without Git for Windows greenlight still works, but only with soft enforcement.

Each adapter also needs its own stack on the machine, which greenlight never installs for you: `pytest` and `pytest-bdd`
for Python; Node.js with npm for the TypeScript adapters (web UI and Node services; CI uses Node 22); Go 1.24 or newer; the Flutter SDK for the Flutter adapter; the .NET 10 SDK; a JDK
with Maven or Gradle for Spring Boot and Kotlin/Android (CI uses JDK 21). `/greenlight:init` checks your machine.

greenlight writes `.bdd/` (commit it; its machine-local `.enforcement/`, `.integrity/` and `.runs/` folders are
ignored) and the adapter's `tests/` skeleton into your repository, and never overwrites an existing file. To remove it,
delete those folders; `bdd install-skills ... --uninstall` removes the skills it installed outside the plugin.

## Use

```text
/greenlight:init                                  # check the machine, pick an adapter, prove the sample runs
/greenlight:feature "what you want"               # run a feature through the phases
/greenlight:approve FEAT-001 rules                # you, after reading rules.md
/greenlight:approve FEAT-001 examples             # you, after reading the scenarios
/greenlight:adopt "orders module"                 # describe code that already exists, change nothing
/greenlight:status                                # where everything stands
/greenlight:change FEAT-001 "what changes, why"   # change approved work, keeping the history
bdd check FEAT-001                                # your formatter, linter and type checker
bdd pr FEAT-001                                   # a pull-request description from the recorded facts
bdd report FEAT-001 --out reports/FEAT-001.html   # a readable HTML report of the feature, for non-developers
```

## Known limits

- At `autopilot` nobody reviews the rules or the examples; the report says so. At `standard` a person must approve the
  rules, so an unattended run stops there.
- Without hooks (no Git for Windows, Codex, `AGENTS.md`) enforcement is soft, and work done in Codex is never graded hard.
- The Python mutation check (`bdd mutate`) needs WSL on Windows, because mutmut does not run natively there; nothing else
  does.
- A Next.js project that uses Turbopack has its `node_modules` copied, not linked, when `bdd run --against-red` re-proves
  a red, which costs disk space and time.
- Measured results from end-to-end runs, and what they do not show, are in the [CHANGELOG](CHANGELOG.md).

## Documentation

- [Quickstart](docs/quickstart.md): install to verified feature
- [Concepts](docs/concepts.md): phases, gates, locks, autonomy levels, enforcement
- [Vocabulary](docs/vocabulary.md): the step phrases scenarios are written from
- [Adapters](docs/adapters.md): test stacks, which Python runs the tests, quality and mutation checks
- [CI](docs/ci.md): re-check locks, the green run, approvals and traceability in a pipeline
- [Upgrading](docs/upgrading.md), [FAQ](docs/faq.md), [Troubleshooting](docs/troubleshooting.md)
- [A filled-in example feature](docs/examples/order-discounts)
- For contributors: [CLAUDE.md](CLAUDE.md), [design decisions](docs/dev/decisions.md), [platform notes](docs/dev/platform-notes.md)

## License

MIT
