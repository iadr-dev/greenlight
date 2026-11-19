# Phase 5: System map

Agent: **system-analyst** (may read the whole code base). Cards: the instruction cards of the steps used,
`standard-values`, `api-design`, `database-schema`, `database-performance`, `security`.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- The approved feature files, `rules.md`, `test-design.md`.
- The approved product design when there is one: the screen rows of the feature (`bdd design FEAT-n --screens`), their
  screen files, `.bdd/architecture.md`; and `.bdd/sources.toml`, the services the project uses and where their
  documentation is.
- The code base and the adapter's `guide.md`.
- `templates/system.md` and `templates/design.md`.

## Steps

1. For every step of every scenario, find the interface it exercises in this code base: the API operation, the
   command, the library function, the entity and how a test seeds and reads it, the event or job, the screen and
   the components on it, the client-side state a screen starts from.
2. Write `system.md` from `templates/system.md`: a table of logical names to where they live, the data, the
   **Dependencies** (every external system a test may stub, one per line), how time reaches the code, events
   and jobs.
3. List the seams that do not exist yet: what the implementer will have to build, and what each must do. These
   stay as `ExpectedMissing` until then.
4. Where a step maps to nothing, list it as a design decision, not a guess. If the feature files themselves
   need to change, raise a change request (see `templates/change-requests.md`) instead of editing them.

5. Write `design.md` from `templates/design.md`: the views this feature needs (a flowchart of components and data
   flow, a sequence diagram of the key interaction, a class or ER diagram of the domain or data) as Mermaid, each
   small enough to review in a minute. Show what exists and mark what will be built. Name the interfaces a diagram
   shows with `%% interface: <logical name>` comments.

5a. Write the technical design, the fourteen tables of `templates/design.md`, before any code exists:
   - **Design trace.** `bdd design FEAT-n --screens` lists the screen rows of the approved design that name the
     feature, with their states and fields. Trace every field and element of each to its rule, its API field and its
     component. A field the person's design shows and no rule covers is a question for the person, not a field to drop.
   - **Building blocks.** For each field with an API field, its standard and library from the card `standard-values`
     (phone E.164 with libphonenumber and a country-code picker, country ISO 3166-1 with names from the platform,
     money ISO 4217 in integer minor units, time zone IANA, address in the country's format), and the documentation
     you read.
   - **External services.** For each SDK or API call, read the service's current documentation from what
     `.bdd/sources.toml` names for it: its official page, its MCP server or documentation lookup (context7,
     microsoft-docs, the vendor's own) when installed, or its command-line tool. Report each source; the orchestrator
     records it with `bdd docs FEAT-n --service NAME --source URL` (or `--mcp SERVER --query TEXT`, or `--cli COMMAND`).
     Name the call's quota, cost and what happens when it fails.
   - **Architecture and patterns.** Where each new piece lives in the layers of `.bdd/architecture.md`, and the
     project's own patterns to copy, each with a file that shows it (`feature-dev`'s code-explorer helps when it is
     installed).
   - **API contract, data and performance, security and privacy.** The schema fragment and what older clients get; a
     migration with its rollback, an index for each query, a budget for each operation (every endpoint is one);
     an authorisation row for each endpoint, the rate limits, personal data and how long it is kept.
   - **Errors and resilience, state and offline, accessibility and language, observability, configuration and
     delivery, test strategy.** One table each. Every state of each screen row is in *State and offline*.
   A section that does not apply holds one row, `n/a` and the reason. Run `bdd design FEAT-n` and fix what it reports.

6. Fill the Contracts section of `system.md` from the project's schema file when there is one (OpenAPI, GraphQL,
   protobuf): copy what the feature uses exactly, and mark what it adds or changes. When there is none, say so.
   For a feature that touches the database, draw the affected tables in the `erDiagram` of `design.md` with their
   keys and the cardinality of each relation, and name the migration folder. Read the cards `api-design` and
   `database-schema`, and the data section of `.bdd/standards.md`.

## Output files

`system.md` and `design.md`.

## Gate

Every step maps to an interface, or is listed as a design decision, and `bdd design FEAT-n` is clean: the gate runs the
same checks and refuses an untraced screen row, a field with no building block, an outside call without evidence, a
query without an index and the other gaps by section and row. A feature started before the technical design has no
`technical_design` marker in its state and is checked for its diagrams only. Then:

```sh
bdd gate FEAT-n system-map --result pass
```

## Pitfalls

- Guessing an interface that does not exist. Say it does not exist.
- Listing as a dependency something the system owns. Only external systems may be stubbed.
- Mapping to the database when an API or service exists: use the most realistic seam.
- A diagram that shows a wish instead of the code: draw what you read, and mark new parts as new.
- Forgetting how time reaches the code. Without a clock seam the time steps do nothing.
- Building what the API needs instead of what the person's design shows: in the Fieldly run the inventory listed a tax
  ID, an invoice footer and bank details, and the API built a phone, an address and a time zone. Trace the screen first.
- A field kept as free text where a standard exists (a phone of up to 40 characters). Name the standard and the library.
- A call to an SDK written from memory. Read the current page, record it, and name the version.
