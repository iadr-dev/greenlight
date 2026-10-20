# Report: FEAT-000 <title>

<!-- Written by the spec-auditor from artifacts only. Verdict is PASS (no failed blocking item) or FINDINGS. -->

Verdict: PASS | FINDINGS
Autonomy: standard (switches: none)
Enforcement: hard | soft (violations are detected, not prevented: <reasons>)
Review status: reviewed | UNREVIEWED (autopilot)

## Assumptions and rules

<autopilot only: the assumption list and the rule list first, so one pass reviews the whole feature>

## Traceability

<the output of `bdd trace FEAT-000`>

## Design

<the Mermaid blocks of design.md, or `no design view` and why>

## Workspace

<only when the project has a `[workspace]`: each member, whether it was observed here, and what `bdd workspace check FEAT-000 --gate verify` said; a member that was not observed is listed as such>

## Gates, locks and approvals

- Gates: <gate results from state.json, with who or what recorded them>
- Locks: <`bdd lock FEAT-000 --check` result for spec and bind>
- Approvals: <each human approval, its origin, and whether its hashes match the current files>
- Integrity violations: <open or closed, from `bdd status`>

## Checklist

<!-- One line per item of review/checklist.md: ID, ✓ / ✗ / UNVERIFIABLE, and evidence (file:line, scenario tag,
     command output). A ✗ without evidence is not allowed, and neither is a ✓ on a general impression. -->
| ID | Result | Evidence |
|---|---|---|
| T1 | ✓ | <evidence> |

## Findings

- Must fix:
- Should fix:
- Unverifiable:

## Cost

<tokens and time per phase, from state.json>
