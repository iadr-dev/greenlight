---
id: C.UI.NOT_SEE
kind: instruction
apply_when: something must be hidden, removed or withheld from a person
---
## Semantics

The logical component is not visible.

Kind: **then**. Profile: ui. Carries: nothing.

## In practice

Use it for what a person must not be shown: an admin button for a customer, an error after the problem was fixed, a banner that was dismissed. Pair it with a Then that shows the person is on the right page, otherwise a page that failed to load would pass.

## Patterns

- `{actor} does not see {target}`

## Good and bad Gherkin

Good:

```gherkin
Then alice sees orders list showing:
  | item    |
  | order 1 |
And alice does not see delete button
```

Bad:

```gherkin
Then nothing is wrong
```

## Playwright adapter

`ui.assertHidden` uses `toBeHidden`, which passes when the element is absent or invisible and waits for it to become so. The target must still be mapped in `TARGETS`; an unknown name throws `NotMapped` instead of passing silently.

These notes describe the `ts-playwright-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- A negative check on a page that never loaded: always show something that is there as well.
- Mapping the target to a selector that is wrong, so that it is "not visible" for the wrong reason.
- Checking hidden through styling when the feature is about permission: the data should not be in the page at all.
