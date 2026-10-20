---
id: C.JOB.RUN
kind: instruction
apply_when: behaviour is driven by a scheduled or background job
---
## Semantics

Execute a scheduled or background job synchronously.

Kind: **when**. Profile: base. Carries: none.

## In practice

Run the job to completion synchronously, after the clock and data are set.

## Patterns

- `the {job} job runs`

## Good and bad Gherkin

Good:

```gherkin
When the nightly-settlement job runs
```

Bad:

```gherkin
When we wait until 02:00 for the scheduler
```

## Python adapter

`System.run_job(job)`; call the job's entry point directly. Advance the clock first with `{duration} passes` if the job depends on time.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Relying on the real scheduler or on real time passing.
- A job that is not idempotent: add an example that runs it twice.
- Forgetting the data the job must leave alone (`no X records changed`).
