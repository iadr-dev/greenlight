# Adoption path: describe what the code already does

For bringing one bounded part of an existing code base under greenlight: a module, an API area, a command. The result
is rules and examples that say what the system does today, tests that prove it, and locks, so that later changes are
made through the normal flow with a safety net. No production code is written or changed.

## When to use it

- The behaviour exists and is not yet covered by greenlight features.
- One bounded area at a time (a handful of rules). Larger areas are split by the product-analyst into slices; adopt the
  first and list the rest in the brief.
- If the person wants the behaviour to *change*, that is a normal feature (`/greenlight:feature`), not an adoption.

## How it differs from a normal feature

The feature is created with `bdd state init FEAT-n --title "<area>" --adopt`. The phases and agents are the same, with
these differences:

| Phase | Difference |
|---|---|
| discover | The product-analyst reads the code and its documentation (read-only) and writes the brief as *what the area does today*. The person's words name the area; there is no request to decode. |
| specify | Each rule states an observed behaviour in business language and cites where it was observed (`file:line`). Code that looks like a bug is not turned into a rule: it is a question for the person, and the rule records what the code does. |
| test-design | Techniques are applied to the behaviour found: the boundaries, branches and error paths that exist in the code. |
| examples | **Every scenario is tagged `@existing`.** Expected values come from reading the code and are confirmed by the run: a scenario that fails shows the reading was wrong, so fix the scenario, never the code. |
| system-map, refine | As usual. The seams exist already; there is nothing to leave as `ExpectedMissing`. |
| bind | `bdd run FEAT-n` and `bdd classify FEAT-n --expect red` are valid because every scenario is `@existing` and passes. Record with `--record-red`: it pins the production source, which must not change from here. |
| tasks | There are no tasks. Pass the gate with `--detail adopt=true`. |
| implement | There is no implementer. The orchestrator runs `bdd run`, `bdd classify --expect green` and `bdd adopt FEAT-n --check`, and passes the gate with `--detail adopt=true`. The gate refuses if a scenario is not `@existing` or the production source differs from the bind gate. |
| verify | The spec-auditor works as usual, plus checklist item S8. |

## Steps for the orchestrator

1. `bdd state next-id`, then `bdd state init FEAT-n --title "<area>" --adopt --autonomy LEVEL`.
2. Run discover, specify, test-design, examples, system-map, refine and bind with the agents and playbooks of the
   normal flow, adding to every task: "this is an adoption: describe existing behaviour, tag every scenario
   `@existing`, change no production code".
3. The person still approves the rules and the examples by typing `/greenlight:approve FEAT-n rules|examples`.
   Under `auto` and `autopilot` the usual rules apply, and the report says the adoption is UNREVIEWED.
4. At bind: `bdd lock FEAT-n --scope bind --bound`, then `bdd gate FEAT-n bind --result pass --record-red`.
5. `bdd gate FEAT-n tasks --result pass --detail adopt=true`.
6. `bdd run FEAT-n`, `bdd classify FEAT-n --expect green`, `bdd adopt FEAT-n --check`, then
   `bdd gate FEAT-n implement --result pass --detail adopt=true`.
7. Verify with the spec-auditor, write `report.md`, `bdd gate FEAT-n verify --result pass` if the verdict is PASS.

## What does not change

Human approvals of the rules and the examples, the locks, the guard, the tripwire, the red-then-green evidence and the
independent audit are all unchanged.

## Pitfalls

- Writing a rule for what the code *should* do. An adoption describes what it does; a disagreement goes to the person.
- Fixing a bug during adoption. The source is pinned; use `/greenlight:feature` or `/greenlight:change` afterwards.
- Expected values copied from a run without reading why the code gives them: the scenario then proves nothing.
- Adopting too much at once. Several small features trace and review better than one large one.
