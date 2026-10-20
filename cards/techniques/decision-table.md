---
id: decision-table
kind: technique
apply_when: the outcome depends on a combination of several conditions, such as eligibility, pricing tiers or approval rules
output: a table of every combination of conditions with its outcome, and one example per row that matters
cost: medium
pairs_with: [equivalence-partitioning, boundary-value]
---
## Intent

When conditions combine, the rule is a table, not a sentence. Writing the table forces every combination to
have an answer, and the empty cells are the missing requirements.

## How to apply

1. List the conditions and the values each can take (usually yes/no, sometimes a few classes).
2. Write one row per combination. With three yes/no conditions that is eight rows; with more, merge rows whose
   outcome does not depend on a condition (mark it "any") and say so.
3. Fill in the outcome for each row from the rule. **A row nobody can answer is a requirement bug**: stop and
   ask the person, do not invent the answer.
4. Turn each row into one example, named after the combination. Rows that differ in no outcome may share an
   example only if you wrote down why.
5. Check the table for contradictions (two rows that can both be true with different outcomes).

## Worked example

Rule R-021.1: free shipping needs a member account and an order of 50 or more, unless the item is oversized.

| Member | Total 50 or more | Oversized | Outcome |
|---|---|---|---|
| yes | yes | no | free shipping |
| yes | yes | yes | paid shipping (oversized) |
| yes | no | no | paid shipping |
| no | yes | no | paid shipping |
| no | no | no | paid shipping |
| yes | no | yes | *unanswered: ask* |

## Known pitfalls

- Skipping the combination that nobody mentioned. It is the one most likely to be wrong.
- Letting "any" hide a real dependency. Use it only after checking that the outcome truly does not change.
- Too many conditions. More than five or six means the rule needs splitting; split it with the person, then
  tabulate each part.
- Writing the examples in prose instead of one example per row, which loses the trace from row to scenario.
