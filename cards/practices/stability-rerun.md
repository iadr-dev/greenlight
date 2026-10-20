---
id: stability-rerun
kind: practice
apply_when: a scenario failed intermittently, or before declaring a feature done when it touches time, concurrency, the network or a UI
output: results of several runs on the same commit, shuffled and isolated, with each unstable scenario classified as product, test, environment or data
phase: verify
pairs_with: [test-data, mutation-check]
---
## Intent

A scenario that sometimes passes is worse than one that always fails: it teaches the team to ignore red.
Rerun on the same commit, then find out which kind of instability it is before touching anything.

## How to apply

1. Run the feature's scenarios several times on the unchanged commit (`bdd run FEAT --shuffle`, then
   `--isolated`; three to five repeats is usually enough).
2. If every run agrees, the scenario is stable. If results differ, the commit did not change, so the cause
   is in the run.
3. Classify each unstable scenario: **product** (a real race or an ordering bug in the code), **test** (a
   fixed sleep, a shared record, an assertion on something unordered), **environment** (a port, a clock, a
   service that is slow or down), or **data** (a collision, a leftover row, a time-dependent value).
4. Report the classification and the evidence (which runs, which order, what differed) and propose the fix.
   Do not apply it silently, do not quarantine the scenario and do not loosen a timeout: those hide the
   problem. Test fixes are a change request to the locked steps.
5. The scan for fixed waits (`bdd scan`, E3) and the test-data card cover the usual test and data causes.

## Worked example

Scenario "two coupons stack once" passes alone but fails when shuffled after "coupon expires": both use
coupon code SAVE10 and the first leaves it marked used. Classification: data. Proposed fix: generate the
code per scenario.

## Known pitfalls

- Rerunning until green and calling it fixed.
- Fixing the symptom with a retry or a longer wait, which makes the suite slower and the defect rarer.
- Blaming the environment without evidence. Show that the failure follows the machine, not the order.
- Changing the commit between reruns, which makes the comparison meaningless.
- Quarantining by deleting or skipping the scenario: it is a rule that is no longer being checked.
