---
id: C.CLOCK.SET
kind: instruction
apply_when: "the outcome depends on the current date or time: expiry, schedules, age, cut-offs"
---
## Semantics

Freeze or inject time. All time-dependent steps use this clock.

Kind: **given**. Profile: base. Carries: none.

## In practice

All time-dependent steps use the injected clock. A scenario that depends on time and does not set it will break on some other day.

## Patterns

- `the current time is {datetime}`

## Good and bad Gherkin

Good:

```gherkin
Given the current time is 2026-03-01T09:00:00Z
```

Bad:

```gherkin
Given the coupon was created yesterday
```

## Python adapter

`world.clock.set(...)`; ISO 8601, a missing zone means UTC. Freezes the process clock too when `time-machine` is installed, otherwise the application must read `world.clock.now()`.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Relative dates ("yesterday") that move with the real clock.
- Time zones: write the zone, and test the zone boundary with the boundary-value card.
- An application that reads the system clock directly with no seam and no `time-machine`: the step passes but nothing changes. Note the seam in `system.md`.
- Setting the clock after the data that depends on it was created.
