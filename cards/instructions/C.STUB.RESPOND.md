---
id: C.STUB.RESPOND
kind: instruction
apply_when: "the system calls something outside it: a payment provider, an email service, another team's API"
---
## Semantics

Stub an external dependency deterministically. Unstubbed external calls fail the scenario.

Kind: **given**. Profile: base. Carries: table or docstring.

## In practice

Make the dependency answer deterministically. Unstubbed external calls fail the scenario, and real network connections are blocked, so a forgotten stub is loud.

## Patterns

- `{dependency} responds to {operation} with:`

## Good and bad Gherkin

Good:

```gherkin
Given payments responds to charge with:
  """
  {"status": "declined"}
  """
```

Bad:

```gherkin
Given the real payment sandbox is used
```

## Python adapter

`world.stubs.respond(dependency, operation, response)`; route the application's outbound call through `world.stubs.call(...)` or point `respx`/`responses` at it. Only dependencies listed in `system.md` may be stubbed (`bdd scan` S4).

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Stubbing the system under test itself. Stub the boundary, never the subject.
- A stub that always succeeds, so failure handling is never tested; add a declined or timeout example.
- A stub response shaped unlike the real one: keep it to what the real contract promises.
- Verifying nothing about the call. Pair it with `X received Y with:` when the request matters.
