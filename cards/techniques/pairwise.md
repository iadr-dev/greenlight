---
id: pairwise
kind: technique
apply_when: many independent inputs each with several values, where trying every combination is too many and the rule does not link them
output: a small set of examples in which every pair of values from two different inputs appears at least once
cost: medium
pairs_with: [equivalence-partitioning]
---
## Intent

Most defects come from one input or the interaction of two. Covering every *pair* of values needs far fewer
examples than every combination, and is the right trade when the inputs are independent configuration-like
choices (browser, locale, payment type, plan).

## How to apply

1. List the inputs and, for each, the classes that matter (from the equivalence-partitioning card).
2. Confirm they are independent. If one input changes what another means, that is a decision table, not a
   pairwise problem.
3. Generate a covering set with a tool or by hand so that every pair of values appears together at least once.
   Four inputs with three values each need about nine examples instead of eighty-one.
4. Add by hand the combinations the rule singles out (a known bad pairing, the most common real-world
   combination), and any constraint that makes a pair impossible should be removed from the set.
5. Record the generated table in the test-design file so the set can be reproduced.

## Worked example

Checkout with plan (free, pro), payment (card, invoice) and locale (en, de): the four combinations of plan and
payment each appear with both locales in four examples instead of eight, and the two interesting pairs
(pro with invoice in de, free with card in en) are listed first.

## Known pitfalls

- Using pairwise for rules that combine inputs: it samples, so it misses a defect that needs three particular
  values together. High-risk combinations get their own examples.
- Forgetting invalid pairs. A pair that cannot occur in production must be excluded, not tested.
- Generating and never looking: read the set and confirm each example is realistic.
- Treating pairwise as the whole design. It sits on top of the classes and boundaries, it does not replace them.
