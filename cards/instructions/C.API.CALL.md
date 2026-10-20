---
id: C.API.CALL
kind: instruction
apply_when: the action under test is a request to a service
---
## Semantics

Invoke an API operation by logical name (mapped in the driver) and store the response.

Kind: **when**. Profile: api. Carries: table or docstring optional.

## In practice

Invoke an API operation by logical name and keep the response. The table or doc string is the request data; fields that appear in the path are used there and not sent twice.

## Patterns

- `{actor} calls {operation} with:`
- `{actor} calls {operation}`

## Good and bad Gherkin

Good:

```gherkin
When alice calls place order with:
  | item | qty |
  | tea  | 2   |
```

Bad:

```gherkin
When alice sends POST /orders with {"item": "tea"}
```

## Python adapter

`API` in `operations.py` maps the logical name to a method and path; `System.http()` returns the client. An unmapped name raises `NotMapped` (a test defect); a 404, 405 or 501 fails the next Then with `status 404`, which is an expected failure in the red phase.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Paths, verbs and status codes in the feature: lint rejects them. Use logical names.
- Several calls in one When. One action per scenario keeps the cause of a failure clear.
- Sending fields the operation does not define; the API should reject them and the driver should not hide it.
- Reusing another actor's session by accident. Name the actor.
