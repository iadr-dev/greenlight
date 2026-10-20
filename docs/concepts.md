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

## Locks

Approving the examples locks the feature files; passing the bind gate locks the steps, drivers and the adapter's
plumbing (`bdd lock FEAT-n --scope bind --bound`). A changed locked file blocks the implement and verify gates. The
implementer can write production code but not tests.

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
greenlight never presents soft enforcement as hard.

## Agents

Six agents do the phase work: product-analyst, qa-designer, system-analyst, step-engineer, implementer and
spec-auditor. Each has an explicit tool list and write permissions (the implementer cannot touch tests, the auditor
cannot write at all). They read files, never chat history, and report instead of recording; the orchestrator
(`/greenlight:feature`) records everything.

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
