---
id: C.CLOCK.ADVANCE
kind: instruction
apply_when: "the outcome depends on time passing: expiry, timeouts, retries, reminders"
---
## Semantics

Advance the injected clock.

Kind: **when**. Profile: base. Carries: none.

## In practice

Move the injected clock forward; nothing really waits.

## Patterns

- `{duration} passes`

## Good and bad Gherkin

Good:

```gherkin
When 31 days passes
```

Bad:

```gherkin
When we wait a month
```

## Python adapter

`world.clock.advance(text)`; accepts `30 minutes`, `2 days`, `1h 30m`. Needs the clock to have been set first.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Advancing without setting the clock first (the step refuses).
- Durations that straddle a daylight-saving change or month end without saying so.
- Real sleeping. If the application waits on real time internally, give it a seam.
