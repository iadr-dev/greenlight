---
id: mutation-check
kind: practice
apply_when: verifying that tests written or helped by an AI would really catch a defect, once the implementation is green
output: a mutation score for the changed production files, the surviving mutants, and an example added for every survivor that matters
phase: verify
pairs_with: [stability-rerun, negative-cases]
---
## Intent

A green test only proves that the code and the test agree. Mutation testing changes the code in small ways
(flip a comparison, drop a call) and checks that some test fails. A mutant that survives is a defect the tests
would not notice. For AI-written tests it answers the question "are these tests independent of the
implementation?".

## How to apply

1. Run the project's mutation tool on the production files this feature changed, not on the whole code base
   (mutmut, Stryker, PIT, cargo-mutants, go-mutesting or the stack's equivalent). Where the adapter has an
   `[adapters.mutation]` table, `bdd mutate FEAT-n` does exactly this and records the result (the Python adapter ships
   a mutmut wrapper, the Playwright adapter a Stryker wrapper; see their guides); otherwise record the tool and the
   command in `system.md`.
2. Read the score. A low kill rate on tests that were written together with the code means they mirror it
   and do not check it; treat that as a finding for the auditor.
3. Go through the survivors. For each: is it a real behaviour the rules care about (add an example and
   re-run the red-to-green check), an equivalent mutant that changes nothing observable (note it, skip it), or
   code that no rule asks for (question it)?
4. Feed the survivors that matter back to the qa-designer as missing examples. Do not edit locked steps to
   kill them; that is a change request.
5. Keep a ratchet: the score for these files may go up between runs, never down. Do not chase 100%.

## Worked example

Mutating `total >= 1000` to `total > 1000` in the discount code survives: no example sits on the threshold.
Add "exactly 1000 gets the discount" (the boundary-value card) and the mutant dies.

## Known pitfalls

- Running it on everything: slow and noisy. Scope it to the changed files.
- Lowering the threshold or excluding files to make a number pass.
- Killing a mutant by asserting the exact value the code returns today (a snapshot). That is the same
  coupling the check exists to find.
- Counting equivalent mutants as failures. Review them by hand; a few are expected.
- Treating a high score as proof that the rules are right. It says only that the tests would notice a change.
