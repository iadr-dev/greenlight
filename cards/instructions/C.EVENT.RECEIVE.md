---
id: C.EVENT.RECEIVE
kind: instruction
apply_when: the system reacts to an inbound message, webhook or queue event
---
## Semantics

Deliver an inbound message or webhook.

Kind: **when**. Profile: base. Carries: table or docstring.

## In practice

Deliver the event synchronously to the application's own handler; the scenario never waits for a broker.

## Patterns

- `the {event} event is received with:`

## Good and bad Gherkin

Good:

```gherkin
When the payment-settled event is received with:
  | order | amount |
  | 17    | 1000   |
```

Bad:

```gherkin
When a message is put on the Kafka topic payments and we wait five seconds
```

## Python adapter

`System.deliver_event(event, payload)`; call the handler directly or through an in-memory transport.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Sleeping until a consumer picks the message up: flaky and slow (`bdd scan` E3).
- Delivering only well-formed events. Add malformed and duplicate deliveries (negative-cases card).
- Assuming order between events; deliver in the order the rule defines, and test the other order.
