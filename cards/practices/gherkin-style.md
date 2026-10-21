---
id: gherkin-style
kind: practice
apply_when: writing or reviewing the scenarios of a feature file, before showing them to the person
output: scenarios that one person can read in a minute each, with one behaviour apiece and no wording that the lint cannot judge
phase: examples
pairs_with: [test-data, request-decoder]
---
## Intent

`bdd lint` judges the wording of a scenario (the vocabulary, implementation details, trace tags) and warns about its
shape (the order of the steps, length, placeholder data, layout). What it cannot judge is whether a scenario says
something worth saying. This card is that part. The ideas are the common ones of the public "Gherkin guidelines for
AI" by Andrew Knight (AutomationPanda), restated for greenlight's closed vocabulary.

## How to apply

1. **One behaviour per scenario.** If the title needs "and", it is two scenarios. A scenario that goes Given, When,
   Then, When, Then is two behaviours (the lint warns, `L015`).
2. **Do not bundle independent concerns.** Function, speed, accessibility and security are separate scenarios, each
   with its own title, unless the one behaviour really spans them. "Checkout succeeds and finishes in under two
   seconds" is two examples.
3. **State over navigation.** Start from the situation that matters (`alice is signed in as member`) and not from a
   tour of the screens that leads there, unless the path itself is what the rule is about.
4. **Minimal but sufficient `Given`.** Include what a reader needs to understand the outcome and nothing that does not
   change it. If removing a step changes neither the title's meaning nor the result, remove it.
5. **Title the behaviour, not the mechanics.** `A big order gets 10% off`, not `Test discount calculation 2`.
6. **`Scenario Outline` only for the same behaviour with different inputs.** Boundaries and partitions of one rule
   belong in one outline. Rows that exercise different rules are separate scenarios. One row is a scenario (the lint
   warns, `L019`).
7. **Use the person's words and real values.** `Green tea 50g` and `1000.00` say more than `foo` and `100` (the lint
   warns about the obvious placeholders, `L017`; see the `test-data` card).
8. **A `Then` that a reader can check.** Say which figure, record or message changes. The vocabulary's own `the request
   succeeds` is fine because its meaning is fixed in one place; a new `Then it works` is not.
9. **Keep the file readable.** Two spaces per level, lines under 120 characters, no blank line between the steps of
   one scenario and one between scenarios (`L021` to `L024`), a kebab-case file name (`L025`).

## Worked example

Too much in one scenario:

```
Scenario: Checkout
  Given alice is signed in as member
  When alice calls place order with:
    | total |
    | 1000  |
  Then the response contains:
    | discount |
    | 100      |
  When alice calls place order with:
    | total |
    | 10    |
  Then the response contains:
    | discount |
    | 0        |
```

Two scenarios, each with its title and one behaviour:

```
Scenario: An order of 1000 or more gets 10% off
  Given alice is signed in as member
  When alice calls place order with:
    | total   |
    | 1000.00 |
  Then the response contains:
    | discount |
    | 100.00   |

Scenario: An order below 1000 gets no discount
  Given alice is signed in as member
  When alice calls place order with:
    | total  |
    | 999.99 |
  Then the response contains:
    | discount |
    | 0.00     |
```

## Known pitfalls

- Silencing a style warning in `[lint] ignore` because it is tedious. It is there because the scenario is harder to
  read or review as written; silence a code only when the project has a stated reason.
- Splitting a scenario until each has one step. A scenario still needs the context to be understood on its own.
- Turning every pair of examples into a `Scenario Outline`. A table of unrelated rows hides what each one is for.
- Adding a `Background` for steps that one scenario needs (`L018`); it makes that scenario unreadable without scrolling.
- Writing the title last as a label for the steps. Write it first; if it is hard to write, the behaviour is not clear yet.
