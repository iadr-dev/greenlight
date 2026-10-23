# Engineering standards

Status: DRAFT

<!-- Edited and approved by the person; no agent can write this file. When you have read and changed it to describe how
     this project's code is written, change the status line above to `Status: APPROVED`. The implementer, the
     step-engineer and the auditor read it on every feature. A change to it makes the recorded quality results out of
     date, so they are run again. Delete what does not apply; keep it short enough to be read.
     Each rule is marked [tool] (enforced by a linter, type checker, test or CI step) or [review] (enforced by the
     auditor reading the change). A [tool] rule whose tool is not named in an `[adapters.quality.NAME]` table is checked
     by the auditor until it is. The numbers below are defaults: change them to what this project uses.
     Fill in every <placeholder> or delete the line; `bdd doctor` warns while an approved file still has one. -->

## Language and toolchain

<!-- The declared toolchain is the standard. A new project starts on the current stable release, or on the current
     long-term-support line where the ecosystem has one (Node.js, Java, .NET); look it up on the vendor's release page
     when you fill this in rather than copying a number from an example. An existing project keeps its version until
     you decide to upgrade (an agent never upgrades a toolchain, framework or dependency on its own). -->
- Language and version: <the exact version, for example "Python 3.14", "Go 1.27", "Java 25 (LTS) with Kotlin 2.4", ".NET 10 (LTS)">
- Build and package tool: <uv, Gradle, SwiftPM, pnpm, go modules, cargo>; where the project is free to choose, a fast tool that installs from a lock file (uv for Python, pnpm for JavaScript and TypeScript, cargo, go modules, Gradle with its build cache) rather than a slower default.
- Frameworks: <for example FastAPI, Expo SDK n, Next.js n (app router)>
- Project type: <new | existing>; an existing project keeps its conventions unless this file says otherwise.

## Style

- Formatter: <ruff format, ktlint, swift-format, prettier, gofmt, rustfmt>; code is formatted, never hand-aligned. [tool]
- Naming: names say what a thing is or does, in the domain's own words. No abbreviations except those the domain uses. Booleans read as questions (`isActive`, `has_access`). [review]
- Casing follows the language's convention: <snake_case functions / PascalCase types, or the stack's equivalent>. [tool]
- Comments explain why, never what (doc comments excepted, see below). No commented-out code, no TODO without an issue reference. [review]
- Public functions, classes and modules have a short doc comment stating purpose, inputs, outputs and errors. [review]

## Clean code

- One function does one thing, at one level of abstraction. Target: under 30 lines and cyclomatic complexity under 10. [tool]
- At most 4 parameters; beyond that, pass a named object. No boolean flag parameters that switch behaviour; write two functions. [review]
- Nesting is at most 3 levels deep; use early returns and guard clauses instead of deep `if` trees. [tool where supported]
- No magic numbers or strings; give them a named constant or enum. [review]
- No dead code: unused functions, parameters, imports, variables and feature flags are deleted, not kept "just in case". [tool]
- Prefer immutable data and pure functions; mutation and side effects are confined to a few named places. [review]
- A function either returns a value or causes an effect, not both (command-query separation) unless the language idiom says otherwise. [review]
- Prefer composition over inheritance. Inheritance is allowed only for a true "is-a" relationship or to implement an interface. [review]
- A file holds one main concept and stays under about 300 lines; a class under about 200. Past that, split by responsibility. [tool where supported, else review]

## No duplicated code (DRY)

- Duplicated logic is removed. A rule, calculation, query, validation, mapping or constant exists in exactly one place. [review]
- Rule of three: the first copy is tolerated, the second is noted, the third is extracted. Extract earlier when the copies must change together.
- Do not merge code that merely looks alike. Two blocks that change for different reasons stay separate; a wrong shared abstraction costs more than a copy.
- Before writing new code, search the code base for an existing function, type or module that already does the job and reuse it. The report names what was reused. [review]
- Duplication detector (for example jscpd, PMD CPD, `dupl`, pylint `duplicate-code`): <tool and threshold, for example fail above 3% duplicated lines or any block over 10 lines>. [tool]
- Test code is held to the same rule: shared setup goes into fixtures, builders or helpers, not copy-pasted.

## Architecture

- Layers: <for example api -> service -> domain <- repository>. Dependencies point inward only; the domain depends on nothing outside itself. [tool: <import-linter | ArchUnit | dependency-cruiser | Go internal packages | module boundaries>]
- Domain and business rules contain no framework, database, HTTP, file or clock code. Input and output happen at the edges and are passed in. [tool/review]
- Depend on abstractions, not implementations: services receive their collaborators through an interface (or abstract class, protocol, trait) injected via the constructor or function parameters, never created inside with `new` or a global lookup. [review]
- Define an interface where there are, or will realistically be, two or more implementations, or where a test needs a substitute (repository, gateway, clock, message sender, file store). Do not create an interface for a class with one implementation and no boundary; that is ceremony.
- Interfaces are small and owned by the code that uses them (interface segregation): a caller depends only on the methods it calls. [review]
- Any implementation can replace another through its interface without callers changing or special-casing (Liskov); no `instanceof` / type checks on an abstraction. [review]
- Add behaviour by adding a new implementation or module, not by editing a growing `if/else` or `switch` over types (open/closed). [review]
- A module exposes a small public surface; other modules import only that surface, never its internals. No circular dependencies between modules or packages. [tool]
- Configuration is read in one place at startup and passed down; code does not read environment variables or files directly. [review]
- Clients of outside systems (HTTP APIs, payment, storage, messaging, AI providers) are wrapped behind our own interface at the boundary, so replacing one touches one module. Frameworks and language-level libraries (the web framework, the UI toolkit, the standard library) are used directly: wrapping them is ceremony. [review]
- Significant decisions (a new layer, a new dependency, a pattern change, a rejected alternative) are recorded in `docs/decisions/NNNN-title.md` (context, decision, consequences). An agent does not reverse a recorded decision without the person's approval.

## Folder and file structure

- Organised by <feature | layer>. Where the framework requires a layout (Next.js and Expo Router `app/`, Go `cmd/` and `internal/`,
  Android Gradle modules, Spring packages), the framework's layout wins and the layers below live inside it. Otherwise, recommended: by
  feature at the top, layers inside:
  ```
  src/
    <feature>/
      api/          # transport: routes, controllers, DTOs, request/response mapping
      service/      # use cases and orchestration
      domain/       # entities, value objects, rules, interfaces (ports)
      infra/        # implementations of the interfaces: database, HTTP clients, queues
    shared/         # only code used by two or more features, with a stated purpose
    config/         # configuration loading
  tests/            # <mirrors src/ | colocated as *_test / *.spec>
  migrations/       # database migrations (omit if no database)
  docs/decisions/   # architecture decision records
  ```
- Each folder has one reason to exist and a name that says it. No `utils`, `helpers`, `common`, `misc` or `manager` dumping grounds; name code for what it does. [review]
- A feature depends on another feature only through its public interface. `shared/` never imports from a feature. [tool]
- File names match the main thing they contain; one main concept per file, as the language's idiom allows (a Kotlin sealed hierarchy, a small Python module or a Go package may hold several types). [review]
- Generated code lives in `<path>`, is marked as generated, is never edited by hand, and is excluded from formatting and duplication checks.
- Fixtures, test data and mocks live with the tests (under `tests/`, or next to colocated test files where the language puts tests beside the code, as Go `_test.go` and Rust `#[cfg(test)]` do), and are never imported by production code. [review]
- A new folder or layer is added only when the structure above cannot hold the code; the reason goes in the report.

## Error handling and logging

- No silent exception handling: never swallow an error, never use an empty `catch`. Handle it, or translate it and rethrow with context. [tool]
- Use specific error types from the domain (`OrderNotFound`, not a generic `Error`). Errors are translated to the API error shape at the edge only. [review]
- Validate input at the boundary and trust validated data inside. Fail fast on invalid state. [review]
- Logging uses levels (`error`, `warn`, `info`, `debug`) with structured fields. No secrets, tokens or personal data in logs. [review]
- An error is logged once, where it is finally handled; code that translates and rethrows it adds context but does not log it. [review]

## Quality rules

- Linter and type checker: <ruff and mypy, detekt, SwiftLint, eslint and tsc, go vet, clippy>, run by `bdd check` once they are in `[adapters.quality]`. Strict mode is on. [tool]
- Public functions have types; no `any`, untyped dynamic values or unchecked casts without a written reason. [tool]
- Lint suppressions (`noqa`, `@SuppressWarnings`, `eslint-disable`, `// nolint`) need an inline reason and are named in the report. [review]
- No unused code, no new global state, no hidden singletons. [tool/review]
- Every behaviour change has a test; every bug fix has a regression test that fails without the fix. [review]
- Test layers: unit (fast, no network, no real clock, no real database), integration (real database or service on the production engine), and <end-to-end, if any>. Tests are deterministic and independent of order. [review]
- Test names state the behaviour (`rejects_expired_token`), and tests assert outcomes, not implementation details. [review]
- Coverage: <for example at least 80% lines on changed code; domain code at least 90%>. Coverage is a floor, not the goal. [tool]
- Security: parameterised queries only, no string-built SQL; no secrets in the repository, checked by a secret scanner (<gitleaks, trufflehog>); dependencies scanned for known vulnerabilities (<npm audit, pip-audit, cargo audit, govulncheck, OWASP dependency-check>). [tool]
- Every rule about who may do what has a test that a caller without the right is refused. [review]

## Performance

- Measure before optimising. An optimisation names the benchmark, profile or scenario that justified it, and the result before and after. [review]
- Budgets: <for example p95 latency under 300 ms per endpoint, startup under 2 s, bundle under 250 KB, memory under 512 MB>. A budget that is exceeded is named in the report. [tool where measured]
- No query per record; every operation that returns a collection has a query-count scenario (see Data). [tool]
- Every collection returned or held in memory is bounded: paginated, streamed or capped. No unbounded lists, caches or queues. [review]
- No blocking I/O or heavy computation on <the async event loop, the UI thread, request handlers>; move it to a worker or an async call. [review]
- Pick the data structure for the access pattern (lookup by key is a map, not a scan). Avoid repeated work in loops; hoist what does not change. [review]
- A cache names what it stores, its maximum size, its expiry and what invalidates it. No cache without one. [review]
- Slow external calls have timeouts, and retries use backoff with a limit. [review]

## Concurrency

- Shared mutable state is avoided; where it exists it has one owner and is guarded (a lock, an actor, a channel, a single thread), and the reason is written next to it. [review]
- Asynchronous work can be cancelled and has a timeout; no fire-and-forget task whose failure nobody sees. [review]
- Operations that can run twice (retries, redelivered messages, double clicks) are safe to run twice. [review]

## Observability

- Logs are structured (see Error handling). Requests and messages carry a correlation id from the edge through every log line and outgoing call. [review]
- Metrics and traces: <for example OpenTelemetry, with the metrics that say the feature works: requests, errors, latency>, or "none" for a library. [review]

## User interface

<!-- Delete this section if the project has no user interface. -->
- Accessibility: <for example WCAG 2.2 AA>; every control has an accessible name, works from the keyboard (or screen reader on mobile), and contrast meets the level. [tool where an accessibility checker runs, else review]
- No user-facing text is hard-coded in components; it comes from <the translation files>, even if only one language ships today. [review]
- Loading, empty and error states are designed for every screen that fetches data. [review]

## Deprecation policy

- Code uses the current, non-deprecated API of the declared toolchain and of every library it calls.
- Deprecation warnings are errors where the toolchain supports it (<the switch for this stack>). [tool]
- Before using a library API, the current documentation is read (the project's docs, or a documentation tool such as context7), not recalled from memory.

## API

<!-- Delete this section if the project exposes no interface to other code. Read with the `api-design` card. -->
- Schema file: <openapi.yaml, schema.graphql, a .proto file, or none>; it changes on purpose, and a breaking change is named in the report.
- Versioning and deprecation: <where the version lives, what counts as breaking, how long a deprecated operation stays>
- Error shape: <one shape for every error, for example RFC 9457 problem details, with a stable code>
- Pagination: <cursor or page, default and maximum page size, the order that makes pages stable>
- Authentication and authorization: <how a caller proves who it is; every operation states who may call it>
- Idempotency: <operations that create or charge accept an idempotency key, or say why not>
- Request and response types (DTOs) are separate from domain entities; the domain model is never exposed directly.

## Data

<!-- Delete this section if the project has no database. Read with the `database-schema`, `database-migrations`,
     `database-performance` and `database-engines` cards. -->
- Engine and version used in production: <for example PostgreSQL 16>; tests run against the same engine, not a lookalike.
- Schema: keys and foreign keys are declared; constraints state the rules (`NOT NULL`, `UNIQUE`, `CHECK`); each fact is stored once unless a measured reason says otherwise.
- Types: money as <integer minor units or exact decimal>, instants as <timestamps with a time zone in UTC>, identifiers as <one type>.
- Indexes: every foreign key that is joined or filtered on gets one; any other index needs a named query or scenario that uses it, and none exist without one.
- Queries: no query per record (a query-count scenario for every operation that returns a collection), every result is bounded, transactions are short.
- Database access goes through repository interfaces; SQL and ORM code appear only in the `infra` layer.
- Soft delete, audit columns and retention: <the policy, and which columns hold personal data and for how long>
- Migrations: <tool>; never edit an applied migration; every migration is reversible or says why not; risky changes are done in compatible steps; tested up, down and up on the production engine.

## Dependencies

- A new dependency is a decision the person makes; it is named in the report, never added silently.
- Before adding one, check that the language's standard library or an existing dependency does not already do the job.
- Dependencies are pinned through a lock file; licences are <allowed list>; unmaintained or vulnerable packages are not added.
- <size or security rules, if any>
