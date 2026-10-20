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

## Using another tool than Claude Code

`bdd install-skills codex` (or `agents-md`) installs greenlight's instructions for Codex and other agent tools. They
run without hooks, so enforcement is soft; see [concepts](concepts.md).

## 6. Change your mind later

```text
/greenlight:change FEAT-001 "coupons stack up to two, not one"
```

reopens the feature at the earliest phase the change touches, tells you which approvals you will have to give again,
and redoes only that work. See [concepts](concepts.md).
