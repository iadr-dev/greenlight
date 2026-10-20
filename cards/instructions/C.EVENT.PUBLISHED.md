---
id: C.EVENT.PUBLISHED
kind: instruction
apply_when: the system must emit a message or event for others to consume
---
## Semantics

Outbound message or event captured by a test double.

Kind: **then**. Profile: base. Carries: table or docstring.

## In practice

Outbound events are captured by a test double of the broker; check that the expected event, with the listed fields, was published.

## Patterns

- `the {event} event is published with:`

## Good and bad Gherkin

Good:

```gherkin
Then the order-placed event is published with:
  | order | total |
  | 17    | 900   |
```

Bad:

```gherkin
Then a message appears on the broker eventually
```

## Python adapter

`System.published(event)` returns the captured payloads; matching is subset-based over the list.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Checking that something was published but not its content.
- Forgetting to test that nothing is published on the refusal path.
- Coupling to the transport (topic names, serialisation) instead of the logical event.
