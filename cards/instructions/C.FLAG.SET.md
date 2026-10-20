---
id: C.FLAG.SET
kind: instruction
apply_when: behaviour is switched by a feature flag or a setting
---
## Semantics

Configure a feature flag or setting for the scenario.

Kind: **given**. Profile: base. Carries: none.

## In practice

Set the flag for this scenario only; both states of a flag that changes a rule deserve examples.

## Patterns

- `the {flag} feature flag is {state:enum(on,off)}`

## Good and bad Gherkin

Good:

```gherkin
Given the new-checkout feature flag is on
```

Bad:

```gherkin
Given the environment variable NEW_CHECKOUT=1 is exported
```

## Python adapter

`System.set_flag(flag, enabled)`; reset in `System.reset()` so flags never leak into the next scenario.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Leaving the flag set for later scenarios. Reset it.
- Testing only the new path. The off state is still shipped.
- Naming the flag by its implementation key instead of its logical name; map it in the driver.
