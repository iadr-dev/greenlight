---
id: C.STATE.GLOBAL
kind: instruction
apply_when: the interface behaves differently depending on what the browser or app has stored
---
## Semantics

Initialize client-side global state or storage.

Kind: **given**. Profile: ui. Carries: table.

## In practice

Set up what the client already knows before the person opens a page: a stored preference, a draft, a feature the person has seen. One row per entry, with `key` and `value` columns. It is the Given counterpart of `the application state includes:`.

## Patterns

- `the application state is:`

## Good and bad Gherkin

Good:

```gherkin
Given the application state is:
  | key   | value |
  | theme | dark  |
```

Bad:

```gherkin
Given localStorage.setItem("theme", "dark") was called
```

## Playwright adapter

The entries are written to the browser's local storage (a `storage` column with `session` uses session storage) by a script that runs before the page's own scripts, once per browser context, so the page finds them on its first load. State that lives on the server belongs in a seeding step (`C.ENTITY.SEED`), not here.

These notes describe the `ts-playwright-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Using it for server data, so the scenario passes only on a machine where the server already has it.
- Values that are objects: give the JSON text; it is stored as written.
- Setting the state after the page was opened; it has no effect on a page that has already read its storage.
