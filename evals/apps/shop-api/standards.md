# Engineering standards

Written by the person running the evaluation, for the evaluation runs of this reference app. It is copied into the
project's `.bdd/standards.md` by the evaluation harness, acting as that person.

Each rule is marked [tool] (enforced by a linter, type checker, test or CI step) or [review] (enforced by the auditor
reading the change). A [tool] rule whose tool is not named in an `[adapters.quality.NAME]` table is checked by the
auditor until it is.

## Language and toolchain

- Language and version: Python 3.12 (the version the project's virtual environment is created with).
- Build and package tool: uv; packages are installed by the person, never by an agent.
- Frameworks: FastAPI with Pydantic 2 models; the HTTP client in tests is httpx through FastAPI's `TestClient`.
- Project type: existing. The app is one module, `app/main.py`; its conventions are kept unless this file says otherwise.

## Style

- Formatter: ruff format (line length 120); code is formatted, never hand-aligned. [tool]
- Naming: names say what a thing is or does, in the domain's own words (order, item, product, total). No abbreviations except `sku` and `qty`, which the code already uses. Booleans read as questions. [review]
- Casing follows PEP 8: `snake_case` functions and variables, `PascalCase` classes, `UPPER_CASE` module constants. [tool]
- Comments explain why, never what (doc comments excepted, see below). No commented-out code, no TODO without an issue reference. [review]
- Public functions and modules have a short docstring stating purpose, inputs, outputs and errors. [review]

## Clean code

- One function does one thing, at one level of abstraction. Target: under 30 lines and cyclomatic complexity under 10. [review]
- At most 4 parameters; beyond that, pass a Pydantic model or a dataclass. No boolean flag parameters that switch behaviour. [review]
- Nesting is at most 3 levels deep; use early returns and guard clauses. [review]
- No magic numbers or strings: a threshold, a rate or a status text gets a named module constant. [review]
- No dead code: unused functions, parameters, imports and variables are deleted. [tool]
- Prefer pure functions for business rules (a discount is computed by a function of its inputs, not inside the route handler); the route handler reads the request, calls the rule and builds the response. [review]
- A function either returns a value or causes an effect, not both, except the route handlers, which do both by nature. [review]

## No duplicated code (DRY)

- A rule, calculation, validation or constant exists in exactly one place. [review]
- Do not merge code that merely looks alike; two blocks that change for different reasons stay separate.
- Before writing new code, search `app/` for a function that already does the job and reuse it. [review]
- Duplication detector: none is run in this project; duplication is checked by review. [review]
- Test code is held to the same rule: shared setup goes into fixtures or helpers.

## Architecture

- Layers: none beyond what the app has: route handlers in `app/main.py`, business rules as pure functions next to them or in a second module of `app/` when they grow past a screen. [review]
- Business rules contain no FastAPI, HTTP or clock code; the request data they need is passed in. [review]
- No new interface or abstraction for code with one implementation and no boundary. [review]
- Configuration, if any is added, is read in one place at startup. [review]
- A new dependency, layer or pattern change is a decision the person makes and is named in the report.

## Folder and file structure

- The existing layout is kept: `app/` for the application, `unit/` for its unit tests (unittest), `tests/` for the greenlight scenarios. [review]
- No `utils`, `helpers` or `common` modules; name code for what it does. [review]
- Fixtures and test data live with the tests and are never imported by `app/`. [review]

## Error handling and logging

- No silent exception handling: never swallow an error, never `except: pass`. [tool]
- A request the app refuses is answered with an `HTTPException` with a specific status (422 for invalid input, 404 for an unknown record) and a `detail` that names the problem. [review]
- Input is validated at the edge by the Pydantic models; code inside trusts validated data. [review]
- No secrets or personal data in logs. [review]

## Quality rules

- Linter and type checker: ruff check and mypy, run by `bdd check` once they are in `[adapters.quality]`; until then the auditor checks the diff against them. [tool]
- Public functions have type hints; no `Any` or unchecked casts without a written reason. [tool]
- Lint suppressions (`noqa`, `type: ignore`) need an inline reason and are named in the report. [review]
- No new global mutable state beyond the in-memory `PRODUCTS` and `ORDERS` stores the app already has. [review]
- Every behaviour change has a scenario; a bug fix has a regression scenario or unit test that fails without the fix. [review]
- Test layers: the unit tests in `unit/` (fast, no network) and the greenlight scenarios in `tests/`. Tests are deterministic and independent of order. [review]
- Test names state the behaviour, and tests assert outcomes, not implementation details. [review]
- Coverage: not measured in this project; every rule must have its scenarios (`bdd trace`). [review]
- Security: no secrets in the repository; dependencies are the ones the person installed, and none is added. [review]

## Performance

- No optimisation without a measurement that justified it. [review]
- Every list the API returns is bounded by the data the app holds; a new list endpoint states its limit. [review]

## Deprecation policy

- Code uses the current, non-deprecated API of Python 3.12, FastAPI and Pydantic 2 (for example `model_dump`, not `dict`; `Field(min_length=...)`, not `min_items`).
- Deprecation warnings raised from the project's own code are errors when tests run with `-W error::DeprecationWarning:app`. A warning that a dependency raises about itself is a should-fix for the person, not a finding against the change. [tool]
- Before using a library API, its current documentation is read, not recalled from memory.

## API

- Schema file: none committed; FastAPI generates the OpenAPI document from the code. A change to an existing response field is breaking and is named in the report.
- Versioning: none; the app has one version and its clients are the tests.
- Error shape: FastAPI's `{"detail": ...}`, with 422 for invalid input and 404 for an unknown record.
- Pagination: none; the product list is small and fixed.
- Authentication and authorization: none; every operation is open, as the app is today.
- Idempotency: placing an order is not idempotent, as it is today; a request for idempotency would be a new rule.
- Request and response models are separate from the stored dictionaries; responses are built explicitly.

## Dependencies

- A new dependency is a decision the person makes; it is named in the report, never added silently.
- Before adding one, check that the standard library or FastAPI already does the job.
