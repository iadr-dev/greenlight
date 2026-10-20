# Concepts

## The idea

A feature request becomes **rules** and **examples** that a person approves, then **red tests**, then **green code**.
People own the contract (what the feature must do); the AI does the mechanical work in between. Every step the AI
cannot be trusted with is a check done by a program, not by a prompt: the `bdd` command line.

## Identifiers and traceability

Every feature, rule and example carries a tag that is the same in the notes, the Gherkin and the tests:

| Tag | Meaning | Example |
|---|---|---|
| `@FEAT-n` | the feature | `@FEAT-007` |
| `@R-n.m` | a business rule | `@R-007.1` |
| `@EX-n.m.k` | an example (scenario) of that rule | `@EX-007.1.2` |

`bdd trace FEAT-n` prints the matrix rule → examples → tasks → tests and lists gaps (a rule without examples, an
example without a test).

## Phases and gates

Phases: discover, specify, test-design, examples, system-map, refine, bind, tasks, implement, verify, done.

- **Human gates** (`rules`, `examples`) are passed only when you type `/greenlight:approve`.
- **Machine gates** (discover, test-design, system-map, refine, bind, tasks, implement, verify) are passed by the
  orchestrator running `bdd gate`, which refuses unless the facts are true right now: approvals valid and unchanged,
  locks intact, no integrity violation open, and for `bind` a valid red run, for `verify` a green one.

## Red, then green

`bdd run FEAT-n` runs the feature's tests and records the result. `bdd classify` sorts every failure:
a failure for the intended reason (an assertion, a missing seam) is an *expected failure*; a failure from a broken
test (import error, unmapped step) is a *test defect* and blocks the gate. A scenario that passes before
implementation must be tagged `@existing` (the behaviour is already there) or it blocks. The run that proved the red
is kept as evidence and later runs cannot replace it.

## Mutation check (optional)

Green tests prove that code and tests agree, not that the tests would notice a wrong change. A project can enable a
mutation tool (`[adapters.mutation]`, see [adapters](adapters.md)); `bdd mutate FEAT-n` then mutates only the production
files the feature changed and the verify gate requires a current result at or above the threshold. It is the check that
answers code written to satisfy the tests instead of the rules. Off by default.

## Stability check (optional)

A scenario that passes in one run and fails in the next is flaky, and a green run of it proves little. A project can ask
for the check with `[stability] runs = 3` in `.bdd/config.toml` (2 to 50). `bdd stability FEAT-n` then reruns the feature
that many times (the first in the usual order, the others shuffled with fresh seeds when the adapter can), records every
run, and flags any scenario whose result changed. The verify gate requires a current result without a flaky scenario;
without the table nothing changes. The runs leave the last `bdd run` alone, so the gates still read the run they always
did. It shows that scenarios behave the same in the orders and repetitions tried; a rare race can still hide, and more runs
only make that less likely.

## Engineering standards and quality checks

Languages, frameworks and conventions differ too much for greenlight to carry rules of its own, so it leaves them to the
project:

- `.bdd/standards.md` (made by `bdd init`, or `bdd init --standards` in an existing project) states the language and
  toolchain version, style, quality rules and deprecation policy. Only you can edit it and mark it `Status: APPROVED`;
  agents cannot write it, and `bdd doctor` warns while it is missing or a draft. The implementer, the step-engineer and the
  auditor read it. The declared toolchain is the standard: a new project starts on the current stable release, an existing
  one is never upgraded silently, and an agent never upgrades or adds a toolchain, framework or dependency on its own.
- `[adapters.quality.NAME]` tables in `.bdd/config.toml` name the project's own tools (formatter, linter, type checker,
  a deprecation check). `bdd check FEAT-n` runs them without a shell, records the result, and the implement and verify
  gates require a current, passing result. Without the tables nothing changes. Deprecation warnings should be errors where
  the toolchain supports it; the practice card of each language names the switch.
- Practice cards for Python, TypeScript (with Expo and Next.js), Kotlin, Swift, Go and Rust list the toolchain commands,
  the deprecation switches and the usual pitfalls, and tell the implementer to read the library's current documentation
  rather than recall an API.
- The auditor's checklist (section Q) judges the diff against the standards, the recorded result and the documentation.

## APIs and databases

Interfaces and data outlive the code that first used them, so the engineering standards have an API section (schema file, versioning, error shape, pagination, authorization, idempotency) and a data section (engine, keys and constraints, types for money and time, indexes, soft delete and retention, migrations, no query per record). The system map copies the contract from the project's schema file and draws the affected tables in the design view's ER diagram, so you see keys and relations before binding. The `data` profile adds one vocabulary instruction, `{operation} ran at most {count:int} queries`: a scenario that seeds several records and limits the queries makes an N+1 problem a failing test before the code exists. The practice cards `api-design`, `database-schema`, `database-migrations`, `database-performance` and `database-engines` hold the detail, and the auditor's checklist section D judges the contract, the migrations, the schema, the query counts and bounded results.

What this proves is narrow and stated plainly: a query count shows "no query per record here", a query plan shows that a query can use an index, a migration lint shows known risky statements. None of it shows how the system behaves with production volume or load; load testing is outside what greenlight checks.

## Locks

Approving the examples locks the feature files; passing the bind gate locks the steps, drivers and the adapter's
plumbing (`bdd lock FEAT-n --scope bind --bound`). A changed locked file blocks the implement and verify gates. The
implementer can write production code but not tests.

## Adopting existing code

`/greenlight:adopt` describes behaviour the system already has. The feature has kind `adopt`: every scenario is tagged
`@existing`, the tests pass from the start, the bind gate pins the production source, and the implement and verify gates
refuse if a scenario is not `@existing` or the production source changed (`bdd adopt FEAT-n --check` shows why). Rules
state what was observed and cite where; code that looks wrong becomes a question for you, not a rule or a fix. An
adoption proves the behaviour is described, locked and traceable, not that it is right.

## Autonomy levels

| Level | Asks you |
|---|---|
| `guided` | at every human gate, after test design, and shows the design view before binding |
| `standard` | for the rules and the examples |
| `auto` | the two approvals are recorded automatically; blocking questions still come to you |
| `autopilot` | nothing; assumptions are recorded and the report is marked UNREVIEWED |

Machine gates are never skipped at any level. Switch with "you decide" in the conversation (recorded with your words).

## Hard and soft enforcement

With hooks active (the normal case) enforcement is **hard**: a guard blocks writes to locked files and to the
approval and evidence data, the tripwire detects tampering by its effect after every tool call, and approvals are
verified against the transcript. Without hooks (for example Git for Windows is missing, or another tool runs the
skills) enforcement is **soft**: violations are detected after the fact, not prevented, and the report says so.
greenlight never presents soft enforcement as hard: `bdd doctor` warns about it, `bdd state show` and the report name it
with the reasons, and a self-reported approval says it was not verified by a hook.

There are three ways to install greenlight, and they differ in what is prevented:

| Install | Hooks | Enforcement |
|---|---|---|
| The plugin (`/plugin install greenlight@greenlight`) | yes | hard: the guard, the tripwire and the approval hook are active |
| `bdd install-skills claude` | no | soft: Claude Code runs the skills as `/greenlight-<skill>` but not the plugin's hooks |
| `bdd install-skills codex` or `agents-md` | no | soft: Codex and other tools run the skills or read the `AGENTS.md` block, with no hooks |

```sh
bdd install-skills claude       # skills under ~/.claude/skills (add --project for .claude/skills)
bdd install-skills codex        # skills under .agents/skills (add --user for ~/.agents/skills)
bdd install-skills agents-md    # a marked block in AGENTS.md for any tool that reads it
bdd install-skills codex --uninstall   # removes exactly what the command wrote, and the folders it leaves empty
```

All support `--dry-run`, never overwrite a differing file without `--force`, never write outside the target folder
or through a link, and tell the agent to leave approvals to you. `--uninstall` removes only files that carry the
installation note and the marked block (the file itself only when nothing else is in it). With no hook to record what
you typed, you set `enforcement = "soft"` in `.bdd/config.toml` and confirm in plain words; the agent records it with
`bdd approve --self-reported`; `enforcement = "hard"` refuses that. Run the locks check in CI (see [CI](ci.md)) to
catch afterwards what nothing prevents.

### Enforcement in Codex

Codex runs hooks too, from the person's own hook file, so greenlight can block and detect there. It cannot call the result
*hard*. In Codex the agent and you run as the same user in the same shell, and a hook is an ordinary command that anything
able to run commands could call with a made-up payload: nothing proves who typed an approval or that a gate was recorded
under a hook, and whatever an agent could have written (a session file, a log) proves nothing either. So:

- **Locks: hooks active, best effort.** `bdd install-hooks codex` shows the three entries it would add (before a tool runs,
  after it, and when you submit a prompt); `--apply` writes them into `~/.codex/hooks.json` (or `--project` for the repo's
  `.codex/hooks.json`) without touching your own entries, and `--uninstall` removes exactly those. Codex asks you to trust new
  hooks. Then shell commands and patches are checked against the locks, and text sent to a running command is allowed only as polling or as a very small set of answers (`y`, `n`, `yes`, `no`, `q`, a number of one to three digits, a single Enter): interactive input into long-running sessions is restricted inside projects, which is the price of failing closed, so run anything else as a normal tool call; the rest of the checks apply (every project a call
  touches, every reading of the command), Codex's own hook and settings files are watched by the tripwire, tools greenlight
  has not looked at are refused (list one you have checked in `[approvals] codex_allowed_tools`), and agents may not run
  greenlight's hook commands, start a nested `codex`, set `CODEX_HOME`, type `$greenlight-approve` through a tool, or write
  under Codex's home, its sessions or any `.codex` folder. The Claude Code guard refuses the same things.
- **Approvals typed in Codex** (`$greenlight-approve FEAT-001 rules`) are recorded with the grade `codex` and the origin
  `codex-unverified`. They are never accepted on their own: refused in a project that says `enforcement = "hard"`, and in every other mode unless you opt in with `[approvals] accept_codex = true` in `.bdd/config.toml`. The CI check (`bdd approve --check`) fails on one until that acceptance is committed, so a reviewer has to accept it (pull request review and branch protection). Accepted, they are labelled "codex, not provenance-verified" in status, the report and the pull
  request description, and never called verified.
  `bdd approve FEAT-001 --check` flags them for the reviewer, and what Codex's session file shows about them is kept as
  supporting evidence only. The guarantee is the committed record reviewed in CI and branch protection.
- **Grade:** a feature with work done in Codex is reported soft, with the reason (`/greenlight:status`, the report,
  `bdd doctor`). If your Codex keeps its home somewhere other than `~/.codex`, say where in `[approvals] codex_home`;
  greenlight never trusts the environment for that. Per-agent write limits do not exist in Codex, and the text checks on shell
  commands are best effort: a differently spelled command can get past them, which is what the tripwire, your deny rules and CI
  are for. The text checks are frozen: they will not grow into a complete shell parser. Known gaps include commands built
  up from variables or `eval`, scripts written first and run later, aliases or wrappers that run `codex` under another
  name, and projects that a command finds by searching rather than by naming a path. Also: a project is found from the paths a command names, not from the operand of `cd` or `git -C` or from a bare word that is a folder; glob spellings of Codex's state folder or session file names in shell text, glob or link spellings in the
  Claude Code guard's Codex-state check. Rely on the tripwire, your deny rules
  and CI (`bdd approve --check`, `bdd lock --check --require`) for those.

## Agents

Six agents do the phase work: product-analyst, qa-designer, system-analyst, step-engineer, implementer and
spec-auditor. Each has an explicit tool list and write permissions (the implementer cannot touch tests, the auditor
cannot write at all). They read files, never chat history, and report instead of recording; the orchestrator
(`/greenlight:feature`) records everything.

## Features across several repositories

When one feature needs work in more than one repository (an API and a web app, a library and its consumers), one
repository is the home: it holds the brief, the rules, the approvals and the report. The others are listed in the home's
`.bdd/config.toml`:

```toml
[workspace]
web = "../shop-web"
```

Each member is a greenlight project of its own, with the scenarios, steps, locks and recorded runs for its share of the
rules, tagged with the same `@FEAT-n`, `@R-` and `@EX-` ids. Ids come from the home (`bdd state next-id`); a member
learns one with `bdd --in web state init FEAT-n --title "..."`. `bdd --in NAME COMMAND` runs any command inside a member,
and `--workspace` repeats `lock --check`, `run`, `classify` and `status` in every repository (`bdd trace --workspace`
shows one matrix). The home's bind, implement and verify gates read each member's own evidence: a valid red and a green
run, intact locks, no open integrity violation. A member that is not on this machine, or not readable, is **not observed
here**; it cannot back a gate and the report says so. Approving the examples also covers each member's feature files and
configuration, so a member's spec cannot be unlocked, edited and locked again without you approving again. The guard and the tripwire protect a member through the paths of
the tool calls a session makes into it; Claude Code does not tell hooks which extra directories a session includes, so
a member the session never touches is protected only by its locks and by CI.

## Changing approved work

`/greenlight:change FEAT-n "<what and why>"` is the one sanctioned route: it releases the affected locks, revokes the
affected approvals (they must be given again), forgets later gate results, and records the change in the feature's
history. Editing a locked file by any other route is a violation.

## Where things live

| Path | What |
|---|---|
| `.bdd/config.toml` | settings and the adapter's tables (edited by you; protected from agents) |
| `.bdd/glossary.md`, `.bdd/vocabulary.toml` | domain words and project steps |
| `.bdd/features/FEAT-n-slug/` | brief, rules, test design, system map, design, tasks, report, state, locks |
| `tests/` (adapter dependent) | feature files, steps and drivers |
| `.bdd/.runs/`, `.integrity/`, `.enforcement/` | machine-local evidence, not committed |

See also [the vocabulary](vocabulary.md) and [adapters](adapters.md).

## The pull-request description

`bdd pr FEAT-n` prints a description for the pull request from the recorded facts: the problem statement from the brief,
the rules and examples with their scenarios and tasks, the gates and approvals with how each was given, the locks, the
enforcement level (and why it is soft, if it is), the red and latest runs as counts, the quality, mutation and stability
results when they exist, the assumptions, the auditor's verdict and findings, and the cost. A feature that ran on
autopilot starts with an UNREVIEWED notice. Nothing is sent anywhere, no command lines, absolute paths or session
identifiers are printed, and `--write` saves it as `PULL_REQUEST.md` in the project root (for another name, redirect the output with `>`). Paste it into the pull request; the
description is only as current as the records, so run it after the verify phase.

## Shared vocabularies

A team can share domain steps between projects by including a vendored file or submodule in `.bdd/vocabulary.toml`. The
files are pinned by hash and read-only for agents; see [the vocabulary](vocabulary.md).
