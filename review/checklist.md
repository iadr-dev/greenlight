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
| S7 | A design view exists, `bdd design` is clean, and the code follows it or the difference is explained | no | `bdd design FEAT-n`, then compare `design.md` with the diff |
| S8 | Adoption features only (`bdd state show` says `kind: adopt`): every scenario is `@existing`, `bdd adopt FEAT-n --check` is clean, and no rule describes behaviour the code does not have | yes | `bdd adopt FEAT-n --check`, then read each rule against the code it cites |

## Q - Code quality and standards

| ID | Check | Blocking | How |
|---|---|---|---|
| Q1 | `.bdd/standards.md` exists and is approved (`Status: APPROVED`); a missing or draft file is reported, and the code is then judged against the code base's own conventions | no | read `.bdd/standards.md`, `bdd doctor` |
| Q2 | The changed production code follows the declared language and toolchain version, style and quality rules; no toolchain, framework or dependency was upgraded or added without the person | yes when the standards are approved, otherwise no | read the diff against `.bdd/standards.md`, the lock files and manifests in the diff |
| Q3 | When `[adapters.quality]` is configured, the recorded result is current and every check passed | yes when configured, otherwise not applicable | `bdd check FEAT-n --check` |
| Q4 | The diff uses no deprecated or removed API: no deprecation warning is silenced or ignored, and the calls into libraries match their current documentation | yes | the deprecation check where configured; otherwise read the diff against the current documentation (project docs, or a documentation tool such as context7) |
| Q5 | Nothing was suppressed to pass a check: no blanket `noqa`, `eslint-disable`, `@Suppress`, `#[allow]`, `// nolint` or `@ts-ignore` added without a stated reason | yes | search the diff for suppression markers |

## D - API contract and data

| ID | Check | Blocking | How |
|---|---|---|---|
| D1 | When the project has a schema file (OpenAPI, GraphQL, protobuf), its diff matches the approved rules and every breaking change is named and was approved; without a schema file this item is not applicable | yes | the diff of the schema file, the recorded `api-breaking` check where configured, the `api-design` card |
| D2 | Every migration in the diff is reversible or says why not, does not edit an applied migration, and avoids steps that lock a large table or break the version still running during a deploy; no migration in the diff means not applicable | yes | read the migrations against the data section of `.bdd/standards.md` and the `database-migrations` and `database-engines` cards |
| D3 | Every new table, key, constraint and index follows the data section of the standards, and each new index names the query or scenario that needs it; money, time and personal data columns are typed and recorded as the standards say | no | read the schema change against `database-schema` and the ER diagram in `design.md` |
| D4 | When the adapter declares the `data` profile and the feature touches a collection (otherwise not applicable), every operation that returns or processes a collection has a scenario with at least three seeded records and a `ran at most N queries` step, and N does not grow with the records; the evidence is the green run, not the code | yes | read the feature files and `bdd classify FEAT-n`; the `C.QUERY.COUNT` and `database-performance` cards |
| D5 | Results are bounded and ordered (a page size with a maximum, a stable order), transactions hold no network call, and no cache lacks an invalidation rule | no | read the diff against the `database-performance` card |

## L - Locks, gates and approvals

| ID | Check | Blocking | How |
|---|---|---|---|
| L1 | The spec and bind locks pass | yes | `bdd lock FEAT-n --check --require` |
| L2 | Every human approval is hook-grade (hard) or labelled self-reported (soft), and its hashes match the current files | yes | `bdd state show FEAT-n` and `bdd approve FEAT-n --verify` |
| L3 | The red gate was recorded before any production-code change | yes | the red record in `state.json` (commit, clean source digest) against `git log`; `bdd classify FEAT-n --run red` |
| L4 | Every mid-run autonomy switch has the person's words recorded | no | `bdd state show FEAT-n` |
| L5 | No integrity violation is open or was left unexplained | yes | `bdd status`, `.bdd/.integrity/violations.json` |
| L6 | Every unlock in `lock.json` history matches a change recorded in `state.json` (reason `change: ...`), and the specification was approved again afterwards | yes | `lock.json` history against `state.json` `changes` and approvals |

## E - Execution

| ID | Check | Blocking | How |
|---|---|---|---|
| E1 | All scenarios of the feature are green, and the full suite is green | yes | `bdd classify FEAT-n --expect green`, then the project's full test command |
| E2 | The shuffled and the isolated runs are green | yes | `bdd run FEAT-n --shuffle`, `--isolated`, then the plain run last |
| E3 | No fixed waits; where time, concurrency, network or UI are involved, repeated runs on one commit agree | no | `bdd scan` finding `E3`; the `stability-rerun` card |
| E4 | Scenarios tagged `@existing` really passed before implementation | yes | the red classification and the git history |
| E5 | Optional: the mutation check on the changed files, with survivors explained. When `[adapters.mutation]` is configured the recorded result must be current and at or above the threshold; without the table this item is not applicable | yes when configured, otherwise no | `bdd mutate FEAT-n --check`; the `mutation-check` card |

## A - Assumptions (autopilot and any recorded assumption)

| ID | Check | Blocking | How |
|---|---|---|---|
| A1 | Each assumption has a rationale and the alternatives it rejected | yes | `bdd state show FEAT-n` |
| A2 | No assumption contradicts something the person stated | yes | compare with `brief.md` |
| A3 | High-risk assumptions (money, authorisation, personal data, data loss) are flagged at the top of the report | yes | read the assumptions |

## Verdict

PASS when no blocking item has a cross and none is UNVERIFIABLE for want of evidence the auditor could have
gathered; otherwise FINDINGS, grouped as must fix, should fix and unverifiable.
