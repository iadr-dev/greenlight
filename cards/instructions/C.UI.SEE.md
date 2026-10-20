---
id: C.UI.SEE
kind: instruction
apply_when: checking what a person sees on a page after an action
---
## Semantics

Visible state of a logical component (text, items, enabled or disabled).

Kind: **then**. Profile: ui. Carries: table or docstring.

## In practice

Name the component and list what it shows. A table with `text`, `value`, `enabled`, `checked` or `visible` columns checks those properties; a table with an `item` column and one row per entry checks a list in order. The check includes that the component is visible, unless the table says `visible` is false.

## Patterns

- `{actor} sees {target} showing:`

## Good and bad Gherkin

Good:

```gherkin
Then alice sees total showing:
  | text   |
  | 900.00 |
```

Bad:

```gherkin
Then the element .cart-total contains "900.00" within 3 seconds
```

## Playwright adapter

`ui.assertShows` uses Playwright's web-first assertions (`toHaveText`, `toHaveValue`, `toBeEnabled`, `toBeChecked`, `toBeVisible`), which retry until the condition holds or the timeout in `bdd.config.ts` runs out. A component that does not exist yet fails with `expect(locator).toBeVisible()`, which is an expected failure in the red phase. An unknown column throws `NotMapped`.

These notes describe the `ts-playwright-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Checking markup (classes, attributes) instead of what the person sees.
- Waiting before checking. The assertion already waits; a fixed sleep only slows the run down.
- A list checked as a single text. Use an `item` column so each entry is compared.
- Asserting only that something is visible when the scenario is about its content.
