---
id: C.QUERY.COUNT
kind: instruction
apply_when: a list or a lookup must not run one query per record, or a data access must stay within a query budget
---
## Semantics

Check how many database statements the last action ran, through a counter the project installs on its data access. A list of several records that needs one query per record is the classic N+1 failure; the scenario must seed enough records for it to show.

Kind: **then**. Profile: data. Carries: none.

## In practice

Seed at least three records of whatever the operation lists, and give the limit as a number that does not depend on how many there are. A loading that runs one query for the list and one for each record passes with two records and fails with five at the same limit. Choose the limit from the design (one query for the list, one more per related collection that is loaded together), not from what the code does today.

## Patterns

- `{operation} ran at most {count:int} queries`

## Good and bad Gherkin

Good:

```gherkin
Given the following order exist:
  | id | customer |
  | 1  | alice    |
  | 2  | bob      |
  | 3  | carol    |
When alice calls list orders
Then list orders ran at most 2 queries
```

Bad:

```gherkin
Then list orders ran at most 50 queries
```

## Python adapter

`System.queries_executed()` returns the statements run since the scenario began; install a `QueryCounter` from `tests/drivers/queries.py` on the application's engine (`hook_sqlalchemy`) or connection (`django_wrapper`) when the system is built. `World.act()` notes the count before each action and the step compares the difference with the limit. Without the seam the step fails as an expected failure; every other scenario is unaffected. Savepoints and transaction control are not counted. Actions that run in another process (a command line tool) cannot be counted this way.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- A limit copied from the current behaviour, which makes the scenario a snapshot of the problem it should prevent.
- Too few seeded records: with one or two rows an N+1 problem is invisible.
- A cache warmed by an earlier step in the same scenario, so the first read is not the one being counted.
- Counting a test database that differs from the production engine in a way that changes the statements (an ORM that batches on one engine and not on another).
- Reading the pass as a statement about production speed. It shows that this action does not run a query per record, not how fast it is with a million rows.
