---
id: database-performance
kind: practice
apply_when: writing or judging code that reads or writes the database, especially lists, joins, loops over records and anything on a hot path
output: data access with no query per record, bounded results, the indexes its queries need, short transactions and a query-count scenario for each collection
phase: implement
pairs_with: [database-schema, database-engines, api-design]
---
## Intent

Most slow database code is correct code that asks too many questions, asks for too much, or asks without an index.
Three of these can be shown by a test with a handful of rows, so make them scenarios: the number of queries, the size
of a result, and the plan of a key query.

## How to apply

1. For every operation that returns or processes a collection, write a scenario that seeds at least three records and
   ends with `<operation> ran at most N queries` (instruction `C.QUERY.COUNT`). Choose N from the design: one for the
   list plus one for each related collection loaded together. If the code needs more as the records grow, it is an N+1
   problem; load the related data in one step instead:
   - SQLAlchemy `selectinload` or `joinedload`; Django `select_related` (single-valued) and `prefetch_related`;
   - Prisma `include`; JPA a fetch join or an entity graph; GORM `Preload`; Entity Framework `Include`.
2. Bound every query that can return many rows: a `LIMIT`, a page size with a maximum, an order that makes pages
   stable. Prefer keyset (cursor) pagination to large offsets. Select the columns you need, not every column.
3. Index what the queries filter, join and sort on (see `database-schema`). Check the plan of the key queries on data
   with realistic volume: `EXPLAIN` before, and `EXPLAIN ANALYZE` where the engine has it. A plan on ten rows says
   little, because a sequential scan is correct there. If the project wants this as a check, it owns a script that runs
   `EXPLAIN` for a listed set of queries and fails on a full scan of a large table, wired as
   `[adapters.quality.query-plans]`.
4. Keep transactions short: no network call, no user input and no slow computation while one is open; take locks in a
   consistent order.
5. Use a connection pool and size it: pool size per process times the number of processes must stay below the
   database's connection limit; put a pooler in front when there are many short-lived processes.
6. Cache only with a stated invalidation rule (what changes it, how long it may be stale). A cache that nobody can
   explain is a bug waiting for its first stale read.

## Known pitfalls

- A query inside a loop over query results, often hidden behind a property or a serializer field.
- A query-count limit copied from today's behaviour, or a scenario with one or two rows: the problem cannot show.
- `OFFSET` pagination over a large, changing table; `COUNT(*)` on every page request.
- A sort or filter on an expression, a function or a cast of an indexed column, so the index is unused.
- A leading wildcard `LIKE '%x'` that no ordinary index can serve.
- Reading a row, changing it in the application and writing it back without a lock or a version check (lost updates).
- Treating a passing query-count or plan check as a speed guarantee. It proves "no N+1 here" and "this query can use
  an index", not behaviour at production volume; load testing is outside what greenlight checks.
