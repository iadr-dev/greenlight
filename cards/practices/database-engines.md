---
id: database-engines
kind: practice
apply_when: the schema, a migration or a query has to behave well on PostgreSQL, MySQL or SQLite
output: engine-specific choices for types, locking, indexes and plans that match the engine the project runs in production
phase: implement
pairs_with: [database-schema, database-migrations, database-performance]
---
## Intent

The rules in the other database cards hold everywhere; the commands and the traps differ by engine. Check these
against the engine and the version the project declares in `.bdd/standards.md`, and test against that engine, not
against a different one that happens to be easier to start.

## How to apply

### PostgreSQL

1. Use `timestamptz` for instants, `numeric` for exact decimals, and `jsonb` with a GIN index only for data the rules
   do not constrain.
2. Create indexes on live tables with `CREATE INDEX CONCURRENTLY` (it cannot run inside a transaction block, so the
   migration tool needs its non-transactional mode for that step). Partial indexes (`WHERE deleted_at IS NULL`) keep
   soft-delete tables small.
3. Add a constraint to a large table in two steps: `ADD CONSTRAINT ... NOT VALID`, then `VALIDATE CONSTRAINT`, which
   does not block writes. Set a `lock_timeout` for migrations so a blocked change fails instead of queueing writes
   behind it.
4. Read plans with `EXPLAIN (ANALYZE, BUFFERS)`.

### MySQL (InnoDB)

1. Use `utf8mb4`; the table is stored in primary key order, so choose a short, ever-increasing primary key.
2. Prefer online DDL (`ALGORITHM=INPLACE, LOCK=NONE`, or `INSTANT` where the version supports it) and state the
   algorithm in the migration so an unsupported change fails instead of locking silently.
3. A comparison between different types or collations can stop an index from being used; read the plan with
   `EXPLAIN`, and `EXPLAIN ANALYZE` from version 8.0.18.
4. Keep `ONLY_FULL_GROUP_BY` and strict mode on, as in production.

### SQLite

1. Foreign keys are off until `PRAGMA foreign_keys = ON` on each connection; turn it on in the connection setup.
2. Columns are loosely typed unless the table is declared `STRICT` (3.37 and later).
3. `ALTER TABLE` is limited (older versions cannot drop or retype a column); migrations rebuild the table.
4. One writer at a time; WAL mode helps readers. Use it for tests only when production is SQLite as well.

## Known pitfalls

- Testing on SQLite while production runs PostgreSQL or MySQL: types, locking, case rules and error messages differ
  and hide bugs.
- A concurrent index build inside a transactional migration, which the engine refuses.
- Assuming the default isolation level is the same on every engine.
- Time zone settings on the server or the connection changing what a naive timestamp means.
- Upgrading the engine version to get a feature without the person deciding it; the declared version is the standard.
