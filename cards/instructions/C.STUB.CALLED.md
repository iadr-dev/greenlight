---
id: C.STUB.CALLED
kind: instruction
apply_when: the request sent to an external dependency matters, not only its answer
---
## Semantics

Verify an outbound call to a stubbed dependency.

Kind: **then**. Profile: base. Carries: table or docstring.

## In practice

Verify an outbound call to a stubbed dependency: the dependency received that operation with those fields.

## Patterns

- `{dependency} received {operation} with:`

## Good and bad Gherkin

Good:

```gherkin
Then payments received charge with:
  | amount | currency |
  | 900    | EUR      |
```

Bad:

```gherkin
Then the HTTP library was called once
```

## Python adapter

`world.stubs.assert_received(dependency, operation, expected)`; subset match over the recorded requests.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Asserting call counts or order that the rule does not define.
- Verifying calls to something that was never stubbed: the Given must stub it.
- Checking the stub instead of the behaviour; keep it for requests the dependency really needs.
