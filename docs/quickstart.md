# Quickstart

From an empty checkout to a verified feature. Most of the time is the AI working; yours goes on reading and approving.

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

It runs `bdd doctor` and shows every warning with its fix, recommends a test adapter for what it finds (for example
`python-pytest-bdd` for a Python project whose dependency files name pytest, FastAPI, Flask, Django or Starlette;
[adapters](adapters.md) describes all nine adapters), and asks you to confirm the adapter and a starting autonomy level. It then creates `.bdd/` and the adapter's
`tests/` skeleton without overwriting anything, offers the optional helper plugins once, and proves the sample feature
runs green. It never installs packages without asking; for `python-pytest-bdd` you need `pytest` and `pytest-bdd` in the
project's environment (a `.venv` in the project is found automatically; otherwise `bdd init --python PATH` records the
interpreter).

Doctor runs before `.bdd/` exists, so it shows only the machine checks. Run `bdd doctor` again after init to get the
project checks. Some of those warnings are normal on the first run. `enforcement: no hook has run in this project yet`
goes away at the first edit or shell command of a session with the plugin, `integrity: no baseline yet` at the next
prompt, and `codex hooks` appears only where Codex is installed. `deny rules` stays until you add the shown JSON to
`.claude/settings.json`, merged into any `permissions.deny` list already there. Only you can add it, because the agent
may not edit that file, and the project's file, committed, is the best place because the team shares it.

Commit `.bdd/` (the machine-local `.enforcement/`, `.integrity/` and `.runs/` folders are ignored for you).

### Running `bdd` yourself

The skills and hooks run `bdd`; you rarely need to. `bdd` is not on your `PATH`, so from a terminal call
`sh "<plugin folder>/tools/bdd/bdd" <command>`, where the plugin folder is the `installPath` of `greenlight@greenlight` in
`claude plugin list --json`. Every `bdd ...` line below means that. To check the adapter choice by hand:

```sh
bdd init --detect       # the adapters that fit this repository, and why
bdd init --smoke        # run the adapter's sample feature and clean up
```

## 3. Ask for a feature

```text
/greenlight:feature "Orders of 1000 or more get 10% off; a customer can use at most one coupon"
```

greenlight recommends an autonomy level (say `guided` the first time) and then runs the phases. Feature ids are
zero-padded, so the first feature is `FEAT-001`.

1. **discover**: a short brief; blocking questions come back to you.
2. **specify**: business rules (`R-` lines).
3. **test design**: which cases the rules need, checked for coverage.
4. **examples**: Gherkin scenarios in the project vocabulary.
5. **system map**: where each step lands in your code, plus a small Mermaid diagram (`design.md`).
6. **refine and bind**: steps and drivers are written; the scenarios run and must fail for the right reason (red).
7. **tasks and implement**: the work is split into tasks, and the code is written until the scenarios pass. `bdd route`
   names, for each task, who writes it and who reviews it.
8. **verify**: an independent auditor checks the evidence and returns a report, which is saved as `report.md`.

For a change of one rule, add `--quick` to take the short path (`phases/quick.md`). The approvals and the red gate stay.

## 4. Approve the contract (you, by typing)

The work stops for you at the rules and at the examples. At `guided` it also stops after test design, and shows the
design view (`design.md`) before binding; at `standard` it stops only twice. At `auto` the approvals are recorded for
you, and at `autopilot` nothing is asked and the report is marked UNREVIEWED; see [concepts](concepts.md). Read
`rules.md`, then type:

```text
/greenlight:approve FEAT-001 rules
```

To see what you are about to approve in plain words, and after a change only what changed since your last approval,
ask for the summary (the feature skill shows it before it asks):

```sh
bdd approve FEAT-001 rules --summary
```

Later, read the scenarios in `tests/features/`, then:

```text
/greenlight:approve FEAT-001 examples
```

Add `reject <reason>` to send the work back. Send one approval per message. The AI cannot give these approvals: a hook
records what you typed and checks it against the session transcript. Once the examples are approved, the feature files
are locked.

If you change your mind mid-run, say "you decide" and the level moves to `autopilot` with your words recorded
(`bdd mode FEAT-001 --switch autopilot --reason "..."`); approvals already given stay yours.

### When the tripwire stops the work

After the tool calls that can change files, a tripwire compares protected files (settings, hooks, the plugin's own files,
`.bdd/config.toml`, the test environment) with what it recorded. Undo a change you did not make, for example with
`git checkout`. Accept a change you made on purpose with one line you type, which the message gives you:

```text
/greenlight:approve integrity #3 I reinstalled the test tools
```

It closes exactly the violations listed, and the reason is kept in the report. See [troubleshooting](troubleshooting.md).

## 5. Look around

```text
/greenlight:status          # where everything stands and what it is waiting for
/greenlight:status FEAT-001 # one feature, with its traceability matrix
```

When the report says `Verdict: PASS`, no blocking item of the auditor's checklist failed. Every rule has examples, every
example has a passing test, the approvals and the red run were as required, the reviews are done and current, the
standards are met and nothing approved or bound changed afterwards. The evidence is in
`.bdd/features/FEAT-001-*/report.md`.

## Without the plugin, or from another tool

The plugin gives hard enforcement. Where it is not an option, `bdd install-skills` installs the same skills as plain
files and the project runs in soft mode (violations are detected, not prevented):

```sh
bdd install-skills claude        # Claude Code without the plugin: /greenlight-feature, /greenlight-status, ...
bdd install-skills codex         # Codex: $greenlight-feature, ...
bdd install-skills agents-md     # any tool that reads AGENTS.md
```

Add `--dry-run` to look first and `--uninstall` to take it all away again; see [concepts](concepts.md).
`bdd install-skills codex` (or `agents-md`) installs greenlight's instructions for Codex and other agent tools. They
run without hooks, so enforcement is soft; see [concepts](concepts.md). `bdd install-hooks codex` (it only shows what it would write; `--apply` writes) adds best-effort blocking and detection through Codex's own hook file, and `bdd install-hooks codex --uninstall` removes it. Work done in Codex is still reported as soft. To take approvals typed in Codex (`$greenlight-approve FEAT-001 rules`), which are not provenance-verified, opt in with `accept_codex = true` under `[approvals]` in `.bdd/config.toml`, and have `bdd approve --check` and your branch protection review the committed record in CI.

## Hand the result to reviewers

`bdd pr FEAT-001 --write` saves a pull-request description, `PULL_REQUEST.md` in the project root, from the recorded
facts (rules, examples, evidence, assumptions, the auditor's verdict). Paste it into the pull request; see
[concepts](concepts.md).

`bdd report FEAT-001 --out reports/FEAT-001.html` saves the same facts as one readable HTML page, with what every scenario did,
for a product owner or a reviewer who will not use a terminal.

To have CI re-check locks, approvals and traceability, copy your adapter's `ci/github-actions.yml` to
`.github/workflows/greenlight.yml`; see [CI](ci.md).

## Starting from existing code

To put code that already exists under greenlight before you change it, describe one area first:

```text
/greenlight:adopt "the orders module"
```

The flow is the same, except that every scenario describes what the code does today (tagged `@existing`), the tests
pass from the start and no production code is touched. You still approve the rules and the examples.

## State your engineering standards

`bdd init` also creates `.bdd/standards.md` (in an existing project: `bdd init --standards`) with greenlight's default
engineering standards. They are in force at once and need no approval; a placeholder you leave means what the project
already uses. If you want, edit them to describe your language and toolchain version, style, quality rules and
deprecation policy; agents cannot. `bdd check` runs your formatter, linter and type checker only once you name them in
`[adapters.quality.NAME]` tables in `.bdd/config.toml` (`bdd init` writes none, and `bdd check` says so); see
[adapters](adapters.md).

## 6. Change your mind later

```text
/greenlight:change FEAT-001 "coupons stack up to two, not one"
```

reopens the feature at the earliest phase the change touches, tells you which approvals you will have to give again,
and redoes only that work. See [concepts](concepts.md). After updating greenlight with features in progress, see
[upgrading](upgrading.md).
