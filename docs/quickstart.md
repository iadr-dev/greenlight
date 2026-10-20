# Quickstart

From an empty checkout to a verified feature in about ten minutes of your time (most of the rest is the AI working).

## 1. Install

```text
/plugin marketplace add iadr-dev/greenlight
/plugin install greenlight@greenlight
```

You need Python 3.11 or newer (nothing to install: greenlight uses only the standard library) and a POSIX `sh`:
built in on Linux and macOS, Git for Windows on Windows. See [troubleshooting](troubleshooting.md) if `doctor` complains.

## 2. Set up the repository

Open Claude Code in your project and run:

```text
/greenlight:init
```

It checks your machine, recommends a test adapter for what it finds (today: `python-pytest-bdd`), asks you to confirm
the adapter and a starting autonomy level, creates `.bdd/` and the adapter's `tests/` skeleton without overwriting
anything, and proves the sample feature runs green. It never installs packages without asking; for
`python-pytest-bdd` you need `pytest` and `pytest-bdd` in the project's environment (a `.venv` in the project is
found automatically; otherwise `bdd init --python PATH` records the interpreter).

Commit `.bdd/` (the machine-local `.enforcement/`, `.integrity/` and `.runs/` folders are ignored for you).

## 3. Ask for a feature

```text
/greenlight:feature "Orders of 1000 or more get 10% off; a customer can use at most one coupon"
```

greenlight recommends an autonomy level (say `guided` the first time) and then runs the phases:

1. **discover**: a short brief; blocking questions come back to you.
2. **specify**: business rules (`R-` lines).
3. **test design**: which cases the rules need, checked for coverage.
4. **examples**: Gherkin scenarios in the project vocabulary.
5. **system map and design**: where each step lands in your code, plus a small Mermaid diagram (`design.md`).
6. **refine and bind**: steps and drivers are written; the scenarios run and must fail for the right reason (red).
7. **tasks and implement**: the code is written until the scenarios pass.
8. **verify**: an independent auditor checks the evidence and writes `report.md`.

## 4. Approve the contract (you, by typing)

Twice, the work stops and waits for you. Read `rules.md`, then type:

```text
/greenlight:approve FEAT-001 rules
```

Later, read the scenarios in `tests/features/`, then:

```text
/greenlight:approve FEAT-001 examples
```

Add `reject <reason>` to send the work back. The AI cannot give these approvals: a hook records what you typed and
checks it against the session transcript. Once the examples are approved, the feature files are locked.

## 5. Look around

```text
/greenlight:status          # where everything stands and what it is waiting for
/greenlight:status FEAT-001 # one feature, with its traceability matrix
```

When the report says `Verdict: PASS`, every rule has examples, every example has a passing test, nothing approved or
bound changed afterwards, and the evidence is in `.bdd/features/FEAT-001-*/report.md`.

## Without the plugin, or from another tool

The plugin gives hard enforcement. Where it is not an option, `bdd install-skills` installs the same skills as plain
files and the project runs in soft mode (violations are detected, not prevented):

```sh
bdd install-skills claude        # Claude Code without the plugin: /greenlight-feature, /greenlight-status, ...
bdd install-skills codex         # Codex: $greenlight-feature, ...
bdd install-skills agents-md     # any tool that reads AGENTS.md
```

Add `--dry-run` to look first and `--uninstall` to take it all away again; see [concepts](concepts.md).

## Hand the result to reviewers

`bdd pr FEAT-001 --write` saves a pull-request description from the recorded facts (rules, examples, evidence,
assumptions, the auditor's verdict). Paste it into the pull request; see [concepts](concepts.md).

## Starting from existing code

To put code that already exists under greenlight before you change it, describe one area first:

```text
/greenlight:adopt "the orders module"
```

The flow is the same, except that every scenario describes what the code does today (tagged `@existing`), the tests
pass from the start and no production code is touched. You still approve the rules and the examples.

## State your engineering standards

`bdd init` also creates `.bdd/standards.md` (in an existing project: `bdd init --standards`). Read it, describe your
language and toolchain version, style, quality rules and deprecation policy, and change `Status: DRAFT` to
`Status: APPROVED`. If you use a formatter, linter or type checker, name it in `[adapters.quality.NAME]` tables so
`bdd check` and the gates enforce it; see [adapters](adapters.md).

## 6. Change your mind later

```text
/greenlight:change FEAT-001 "coupons stack up to two, not one"
```

reopens the feature at the earliest phase the change touches, tells you which approvals you will have to give again,
and redoes only that work. See [concepts](concepts.md).
