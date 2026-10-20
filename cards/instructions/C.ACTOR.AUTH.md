---
id: C.ACTOR.AUTH
kind: instruction
apply_when: "a rule depends on who is asking: roles, permissions, ownership"
---
## Semantics

Establish an authenticated session or token for a named actor.

Kind: **given**. Profile: base. Carries: none.

## In practice

Establish the session or token for a named actor so later steps can act as them. The actor name is a label used by When steps; the role decides what they may do.

## Patterns

- `{actor} is signed in as {role}`

## Good and bad Gherkin

Good:

```gherkin
Given alice is signed in as member
```

Bad:

```gherkin
Given the user logs in with password hunter2 and gets a JWT
```

## Python adapter

`System.authenticate(actor, role)` returns the HTTP headers that prove it; the world keeps them per actor and the API driver sends them with that actor's calls.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Putting credentials or tokens in the feature file. They belong in the driver or the environment.
- Signing in through the UI form for every API scenario: slow and it tests login again.
- Using one shared admin for every scenario, so permission rules are never exercised.
- Forgetting the unauthenticated case, which needs its own example (a guest).
