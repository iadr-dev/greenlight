---
id: C.UI.ACT
kind: instruction
apply_when: a person does something on a page or a screen such as clicking, typing, choosing, uploading, swiping or scrolling
---
## Semantics

Perform a user action on a logical component. Selectors live in drivers, never in features.

Kind: **when**. Profile: ui. Carries: table or docstring (optional).

## In practice

One action on one named component: clicks, fills, selects, uploads, types, toggles, swipes or scrolls. Components are named the way a person would say it ("the save button", "the email field"). When the action needs data, give it in a table with a `value` column (a `file` column for uploads, a `direction` column for a swipe or a scroll) or in a doc string. A swipe is the finger's direction (swiping left moves the finger to the left, as a person turns a card away); a scroll is the view's direction (scrolling down shows what is below). The direction is up, down, left or right.

## Patterns

- `{actor} {action:enum(clicks,fills,selects,uploads,types,toggles,swipes,scrolls)} {target}`
- `{actor} {action:enum(clicks,fills,selects,uploads,types,toggles,swipes,scrolls)} {target} with:`

## Good and bad Gherkin

Good:

```gherkin
When alice fills email field with:
  | value           |
  | alice@mail.test |
And alice clicks save button
When alice scrolls order list with:
  | direction |
  | down      |
And alice swipes first order card with:
  | direction |
  | left      |
```

Bad:

```gherkin
When alice types "alice@mail.test" into #email and clicks button[type=submit]
```

## Playwright adapter

`TARGETS` in `operations.ts` maps the logical name to a role and name, a label, a text or a test id, in that order of preference: what a user perceives, not markup. `fills` replaces the content, `types` presses the keys one by one, `selects` chooses an option by value or label, `uploads` takes a path relative to the project, `toggles` flips a checkbox. An unmapped name throws `NotMapped`; a selector that matches several elements fails with a strict mode violation, which is a test defect: make the target more specific.

These notes describe the `ts-playwright-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Selectors, element ids or coordinates in the feature: lint rejects them. Use logical names.
- Several actions in one step. One action per step keeps the cause of a failure clear.
- A target that is only found by position ("the second button"): name what it is for.
- Waiting with a fixed sleep after an action. Assert on the visible result instead; the checks wait for it.
