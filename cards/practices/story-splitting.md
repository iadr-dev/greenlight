---
id: story-splitting
kind: practice
apply_when: a request carries more than a handful of rules, several kinds of users, or more than one independent outcome
output: thin vertical slices, each with its own rules and examples, in the order they should be built
phase: specify
pairs_with: [request-decoder, blocking-questions]
---
## Intent

A feature that is too big cannot be reviewed, tested or approved in one go. Split it into slices that each
deliver something a person can use, so every slice has a short list of rules and a clear definition of done.

## How to apply

1. Check the size: more than about eight rules, rules for different users, or a mix of "create", "change",
   "cancel" and "report" suggest splitting.
2. Split along the **workflow** (first step, then the next), the **rules** (the simplest rule first, then
   the exceptions), the **data variations** (one currency, then more), or the **operations** (create before
   change before delete). Avoid splitting by technical layer: a slice must work end to end.
3. Each slice must be independent enough to build and demo alone, valuable on its own, small enough to hold
   in your head, and testable: you can write examples for it. If two slices cannot be tested separately,
   they are one slice.
4. Put the thinnest end-to-end path first. Later slices add rules and exceptions to it.
5. Give each slice its own feature id when it will be approved separately, and keep the trace tags intact.

## Worked example

"Saved cards" becomes: (1) pay with the only saved card, (2) choose among several, (3) handle an expired card,
(4) remove a card. Slice 1 touches the whole path, so it proves the plumbing before the rest.

## Known pitfalls

- Splitting into "backend", "frontend", "database". None of those is usable alone.
- Slices that depend on each other in a loop. Break the loop by moving the shared rule into the earlier slice.
- Letting a slice grow back: every new rule goes through the same question of which slice it belongs to.
- Leaving the splits implicit. Write the slice list and its order in the brief, so the person approves it.
