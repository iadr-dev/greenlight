---
id: database-schema
kind: practice
apply_when: designing or changing tables, columns, keys, constraints or indexes
output: a schema whose keys, constraints, types and indexes follow the project's data rules and each of which has a reason
phase: system-map
pairs_with: [database-migrations, database-performance, database-engines]
---
## Intent

The schema outlives the code. A constraint the database enforces cannot be forgotten by a new code path, and an index
without a query that needs it only slows every write. Design the data from the rules and the scenarios, and draw it in
the ER diagram of `design.md` before it is built.

## How to apply

1. Read the data section of `.bdd/standards.md`, the existing schema or migrations, and the approved rules. Draw the
   entities, keys and relations in `design.md` (an `erDiagram`) so the person sees them before binding.
2. Keys: every table has a primary key; foreign keys are declared, not implied by a naming habit; natural keys that
   can change are unique constraints, not primary keys.
3. Constraints say what the rules say: `NOT NULL` unless absence has a meaning, `UNIQUE` for what must not repeat,
   `CHECK` for ranges and states. A rule that is "never" belongs in the database as well as in the code.
4. Types: money as integer minor units or an exact decimal, never a float; instants as timestamps with a time zone
   stored in UTC; identifiers as one consistent type; text with a length only when the rule has one.
5. Normalise to the point where each fact is stored once. Denormalise only for a measured reason, named in the design,
   with the rule that keeps the copies equal.
6. Indexes: one per foreign key that is joined or filtered on, and one per query that filters or sorts a table that
   will be large, with the equality columns first. Write next to each index the query or scenario that needs it.
7. Soft delete, audit columns (who and when) and retention are decisions in the standards file; follow it. Mark
   columns that hold personal data and say how long they are kept and how they are removed.
8. To have greenlight run a schema or migration lint, add a table such as `[adapters.quality.schema-lint]` with the
   project's tool; see `database-migrations`.

## Known pitfalls

- A float or a string for money; a local timestamp without a zone; a boolean column that is nullable (three values).
- A JSON column for data the rules query, join or constrain.
- One "type" column plus many nullable columns used by some types only: separate tables or a proper subtype design.
- No index on a foreign key, so deleting a parent scans the child table.
- Indexing every column "to be safe": each index costs every insert and update.
- Random UUIDs as the clustered primary key on an engine that stores rows in key order, which fragments the table; use
  an ordered identifier there.
- Soft delete without a filter in every query and a unique constraint that still allows a deleted duplicate.
- Personal data in a column nobody listed, so the retention rule cannot be applied.
