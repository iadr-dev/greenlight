---
id: boundary-value
kind: technique
apply_when: a rule has a threshold, limit, range, cut-off time or size, or a count that changes behaviour
output: for every boundary, one example just outside, on, and just inside each edge
cost: low
pairs_with: [equivalence-partitioning, decision-table]
---
## Intent

Bugs cluster at the edges of a range, where `<` is written instead of `<=`. Test the edge itself and its
immediate neighbours, not the middle of the range.

## How to apply

1. List every boundary the rule implies. "Orders of 1000 or more get 10% off" has one boundary at 1000.
   "Between 18 and 65 inclusive" has two. Time cut-offs ("before noon"), sizes, counts and dates are
   boundaries too.
2. For each boundary, write the value one step below, the value on the edge, and the value one step above.
   A step is the smallest unit the system distinguishes: one cent, one second, one character, one item.
3. Say in the example name which side of the boundary it checks, and name the technique in the
   test-design file so the auditor can see why the example exists.
4. Take one boundary at a time: keep every other input in the ordinary middle of its range.
5. For ranges that are open on one side, test the single edge and one value far away.

## Worked example

Rule R-007.1: orders of 1000 or more get 10% off.

| Example | Order total | Expected |
|---|---|---|
| just below the threshold | 999.99 | no discount |
| exactly on the threshold | 1000.00 | 10% off |
| just above the threshold | 1000.01 | 10% off |

## Known pitfalls

- Testing only one side. Both sides of every threshold need an example, and so does the edge itself.
- Guessing the step. Money is not always cents (tax may allow fractions), text length is not always bytes.
  Read the rule or ask; do not assume `0.01`.
- Dates and times: include the cut-off instant, time zones that straddle it, and the leap day when a
  calendar is involved. A start that falls after its end is a boundary of its own.
- Text: an empty value, whitespace only, one character, the maximum, one over, and non-ASCII characters
  (bytes, code points and visible characters differ).
- Several boundaries in one example hide which one failed. Vary one at a time.
