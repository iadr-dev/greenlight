---
id: C.UI.OPEN
kind: instruction
apply_when: the scenario starts on a page of a web, mobile or desktop interface
---
## Semantics

Navigate to a logical page.

Kind: **when**. Profile: ui. Carries: nothing.

## In practice

Name the page the way the glossary does ("the orders page", "the checkout page"). The driver maps the name to an address, so the feature never contains a URL. Opening a page is the first action of most UI scenarios; the person acting is named, because each person gets a browser session of their own.

## Patterns

- `{actor} opens the {page} page`

## Good and bad Gherkin

Good:

```gherkin
When alice opens the orders page
```

Bad:

```gherkin
When alice goes to https://shop.example.com/orders?tab=open
```

## Playwright adapter

`PAGES` in `operations.ts` maps the logical name to a path under `System.baseUrl()` or to a complete URL. An unmapped name throws `NotMapped` (a test defect). A page that answers 404, 405 or 501 fails the step with `status 404`, which is an expected failure in the red phase, and so is a base URL the system does not provide yet (`ExpectedMissing`). Each actor has a browser context of their own; sign the actor in (`C.ACTOR.AUTH`) before they open their first page.

These notes describe the `ts-playwright-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Addresses, query strings or fragments in the feature: lint rejects them. Use the page name.
- Signing in after the first page was opened: the browser session is made when the person first acts.
- Opening a page and asserting on it in the same step; the Then step is where the check belongs.
- Pages that need data: seed it in a Given step, never by clicking through other pages first.
