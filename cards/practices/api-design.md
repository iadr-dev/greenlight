---
id: api-design
kind: practice
apply_when: designing, changing or judging an HTTP, GraphQL or RPC interface that other code depends on
output: an interface that follows the project's API rules, with its schema file updated on purpose and any breaking change named
phase: system-map
pairs_with: [language-typescript, language-python, database-performance]
---
## Intent

An API is a promise to callers you cannot see. A change that looks harmless in the code (a renamed field, a stricter
check, a new required parameter) breaks them. The schema file is the record of the promise, so it changes on purpose
and the change is reviewed as such.

## How to apply

1. Read the API section of `.bdd/standards.md` and the project's schema file (`openapi.yaml`, `schema.graphql`, a
   `.proto` file). If there is one, copy its operations into the Contracts section of `system.md`; if there is none,
   say so there instead of inventing one.
2. Decide for each operation the points the standards file names, and write them in `rules.md` when they are
   behaviour a person should approve:
   - **Versioning**: where the version lives and what counts as breaking (removing or renaming a field, changing a
     type, making an optional input required, narrowing an enum an input accepts, widening one a client reads).
   - **Errors**: one error shape for the whole API, with a stable machine-readable code and a human message (RFC 9457
     problem details is a good default); scenarios check the logical error, never raw status codes.
   - **Pagination**: every collection is paged with a default and a maximum page size; prefer a cursor for data that
     changes; state the order, because a page without an order is not stable.
   - **Idempotency**: an operation that creates or charges can be repeated safely, with an idempotency key, or says
     why not.
   - **Authorization**: every operation says who may call it, and a scenario shows a caller who may not.
3. Run the contract checks the project has. To have greenlight run them, add tables to `.bdd/config.toml`:

   ```toml
   [adapters.quality.api-lint]
   command = 'spectral lint openapi.yaml'

   [adapters.quality.api-breaking]
   command = 'oasdiff breaking openapi.base.yaml openapi.yaml --fail-on ERR'
   ```

   Commands run without a shell, so a glob or a pipe belongs in a small script the project owns. The base file for
   the breaking-change check is the schema at the commit the feature started from (for protobuf, `buf breaking
   --against` does the same against a git ref).
4. A deliberate breaking change is a rule the person approved, with the version or deprecation step it needs. The
   schema diff goes in the report.

## Known pitfalls

- A schema file edited by hand to match the code after the fact. Generate one from the other, or check that they agree.
- Treating an added required field in a response as safe: clients with strict parsers fail on it; additions to a
  request are safe only when optional.
- Returning 200 with an error body, or a different error shape per endpoint.
- Pagination by offset on data that changes, which skips and repeats records; and a collection with no maximum page size.
- Numbers for money or identifiers that exceed what JSON clients read exactly: send them as strings.
- Documenting authorization in prose only; there must be a scenario where the wrong caller is rejected.
- Changing a published operation to fix an internal need. Add a new one and deprecate the old with a date.
