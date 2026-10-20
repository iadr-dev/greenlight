# Auditor checklist

Used by the spec-auditor in the verify phase. Every item gets one line in `report.md`: its id, a check mark, a
cross or UNVERIFIABLE, and **evidence** (a file and line, a scenario tag, or command output). A cross without
evidence is not allowed, and neither is a check mark given on a general impression. If an input is missing the
item is UNVERIFIABLE; never guess.

`Blocking` = a cross on this item makes the verdict FINDINGS (it goes under *must fix*). Other crosses are
*should fix*.

Line format:

```text
T3 ✗ EX-007.2.* covers 100 and 101 but not 99 for threshold ">= 100" (boundary-value pitfall 1) - tests/features/discounts.feature:41
L2 ✓ 2 approvals, hook-grade, hashes match state.json
E3 UNVERIFIABLE - no UI scenarios in this feature
```

## T - Test design

| ID | Check | Blocking | How |
|---|---|---|---|
| T1 | Every rule has at least one example, or an exclusion with a reason | yes | `bdd trace` gaps `T001`; read the exclusions |
| T2 | The chosen techniques fit the `apply_when` of their cards, and the card ids are recorded | no | compare `test-design.md` with `bdd cards list` |
| T3 | The Known pitfalls of every cited card are respected (for example both sides of every threshold) | yes | read each cited card's pitfalls against the examples |
| T4 | Every rule with inputs has a negative example or a stated exclusion | yes | `negative-cases` card; read the examples |
| T5 | No example has a vague expected result ("works correctly", "properly"); each one is observable and traceable to a rule | yes | read the Then steps |

## S - Specs and steps

| ID | Check | Blocking | How |
|---|---|---|---|
| S1 | Lint is clean; no implementation detail in the features | yes | `bdd lint` |
| S2 | Every `then` step definition asserts | yes | `bdd scan` finding `S2`, then read the step |
| S3 | Domain steps use the drivers of the core instructions they compose | no | read `.bdd/vocabulary.toml` and the step modules |
| S4 | Drivers stub only the dependencies declared in `system.md` | yes | `bdd scan` finding `S4` |
| S5 | No test is a tautology, compares a value with itself, checks only a status code, or swallows a failure; for each test, name the smallest realistic bug that should make it fail, and it would | yes | read the steps and drivers; judge each as strong, weak or fake in the notes |
| S6 | Mocks sit only at declared external boundaries, never on the system under test; tests were not written from the implementation | yes | read the drivers and the diff |

## L - Locks, gates and approvals

| ID | Check | Blocking | How |
|---|---|---|---|
| L1 | The spec and bind locks pass | yes | `bdd lock FEAT-n --check --require` |
| L2 | Every human approval is hook-grade (hard) or labelled self-reported (soft), and its hashes match the current files | yes | `bdd state show FEAT-n` and `bdd approve FEAT-n --verify` |
| L3 | The red gate was recorded before any production-code change | yes | the red record in `state.json` (commit, clean source digest) against `git log` |
| L4 | Every mid-run autonomy switch has the person's words recorded | no | `bdd state show FEAT-n` |
| L5 | No integrity violation is open or was left unexplained | yes | `bdd status`, `.bdd/.integrity/violations.json` |

## E - Execution

| ID | Check | Blocking | How |
|---|---|---|---|
| E1 | All scenarios of the feature are green, and the full suite is green | yes | `bdd classify FEAT-n --expect green`, then the project's full test command |
| E2 | The shuffled and the isolated runs are green | yes | `bdd run FEAT-n --shuffle`, `--isolated`, then the plain run last |
| E3 | No fixed waits; where time, concurrency, network or UI are involved, repeated runs on one commit agree | no | `bdd scan` finding `E3`; the `stability-rerun` card |
| E4 | Scenarios tagged `@existing` really passed before implementation | yes | the red classification and the git history |
| E5 | Optional: the mutation check on the changed files, with survivors explained | no | the `mutation-check` card |

## A - Assumptions (autopilot and any recorded assumption)

| ID | Check | Blocking | How |
|---|---|---|---|
| A1 | Each assumption has a rationale and the alternatives it rejected | yes | `bdd state show FEAT-n` |
| A2 | No assumption contradicts something the person stated | yes | compare with `brief.md` |
| A3 | High-risk assumptions (money, authorisation, personal data, data loss) are flagged at the top of the report | yes | read the assumptions |

## Verdict

PASS when no blocking item has a cross and none is UNVERIFIABLE for want of evidence the auditor could have
gathered; otherwise FINDINGS, grouped as must fix, should fix and unverifiable.
