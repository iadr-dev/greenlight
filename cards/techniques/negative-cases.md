---
id: negative-cases
kind: technique
apply_when: always, for every rule that takes input or depends on who is asking or on the state of the system
output: for each rule, at least one example of it being refused or failing safely, or a written reason why none exists
cost: low
pairs_with: [equivalence-partitioning, state-transition]
---
## Intent

Rules describe what is allowed; the system is only safe if what is not allowed is checked as well. Every rule
with inputs needs an example in which it says no, and the example shows what the person sees and that
nothing was changed.

## How to apply

1. For each rule ask four questions: what if the input is missing or malformed, what if the caller is not
   allowed, what if the thing is in the wrong state, what if it happens twice?
2. Turn each answer that matters into an example with a specific, observable result: the logical error
   (`the request is rejected with validation error`) and, where relevant, `no order records changed`.
3. Where the honest answer is "this cannot happen", write the reason in the test-design file as an exclusion.
   A rule with neither a negative example nor an exclusion is incomplete.
4. Vary one thing at a time so the failure points to one cause.
5. Look for abuse as well as mistakes: a value that is valid on its own but forbidden for this caller.

## Worked example

Rule R-007.1: orders of 1000 or more get 10% off.

| Question | Example |
|---|---|
| malformed input | a negative total is rejected with validation error, no order records changed |
| not allowed | a guest cannot place the order, rejected with sign-in required |
| wrong state | a cancelled order cannot be discounted again |
| twice | submitting the same order twice creates one order |

## Known pitfalls

- Checking only that an error appeared, not which one and not that the data stayed unchanged.
- Vague expected results such as "it fails gracefully": name the observable result.
- Negative examples copied from the happy path with one word changed, which test the framework, not the rule.
- Skipping them because the code already validates input. The example is what keeps the validation there.
