---
id: database-migrations
kind: practice
apply_when: writing, reviewing or running a change to a database schema or its data
output: migrations that are small, applied in order, reversible or explained, safe on a live table, and tested against the engine used in production
phase: implement
pairs_with: [database-schema, database-engines]
---
## Intent

A migration runs once, on data the tests never saw, often while the application is serving traffic. The risks are
locks that block writes, steps that cannot be undone, and an application version that cannot run against the schema it
meets during a deploy. Design the change so that old and new code both work in between.

## How to apply

1. Read the migration policy in `.bdd/standards.md` and the migrations folder. Never edit a migration that has been
   applied anywhere; add a new one.
2. One concern per migration. Change structure and move data in separate steps.
3. Make the change in compatible steps (expand, then contract):
   - add the new column or table, nullable or with a default the engine adds without rewriting the table;
   - deploy code that writes both and reads the new one;
   - backfill existing rows in batches, outside a long transaction;
   - add the constraint, then remove the old column in a later migration after the code stopped using it.
4. Every migration is reversible, with a working down step, or says in its header why not (dropping data cannot be
   undone) and what the person decided about that.
5. Check the risky operations for the engine in use (see `database-engines`): taking a lock that blocks writes on a
   large table, rewriting a table, adding a constraint that validates every row while locked, creating an index without
   the online option.
6. Prove it: apply all migrations to an empty database, then up, down and up again, with the engine the application
   uses in production (a container in CI), not a lookalike. Where the tool has a drift check, run it (it fails when the
   models and the migrations disagree).
7. To have greenlight run them, add tables to `.bdd/config.toml`, wrapping anything that needs a glob or a pipe in a
   script the project owns (commands run without a shell):

   ```toml
   [adapters.quality.migrations-drift]
   command = 'alembic check'

   [adapters.quality.migration-lint]
   command = 'sh tools/lint_migrations.sh'
   ```

   Other tools with such a check: `python manage.py makemigrations --check --dry-run` (Django), `flyway validate`,
   `atlas migrate lint`, and `squawk` for PostgreSQL migration files.

## Known pitfalls

- Editing a migration after it ran on another machine; the histories diverge silently.
- A column added `NOT NULL` with no default to a table with rows, or a default that rewrites a large table on an engine
  that does not add it as metadata.
- A backfill inside the same transaction as the structure change, holding locks for the whole run.
- Dropping or renaming a column in the same release that stops using it: the previous version still running during the
  deploy fails.
- A down step that was never run, or one that silently loses data.
- Testing migrations on SQLite when production runs another engine; the locking and the types differ.
- Seed data in a migration that tests then depend on; a scenario creates its own data.
