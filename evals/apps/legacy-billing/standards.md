# Engineering standards

Status: APPROVED

Approved by the person running the evaluation, for the evaluation runs of this reference app. It is copied into the
project's `.bdd/standards.md` by the evaluation harness, acting as that person.

Each rule is marked [tool] (enforced by a linter, type checker, test or CI step) or [review] (enforced by the auditor
reading the change). A [tool] rule whose tool is not named in an `[adapters.quality.NAME]` table is checked by the
auditor until it is.

## Language and toolchain

- Language and version: Python 3.12 (the version `requirements.txt` was compiled for).
- Build and package tool: uv, with the pinned, hashed `requirements.txt`; packages are installed by the person, never by an agent.
- Frameworks: Flask with Flask-WTF (CSRF protection).
- Project type: existing, and under adoption: the code is described as it is and **no production file changes**. Code that looks wrong is a question for the person, never a fix.

## Style

The rules in this section and in the next three apply to new code: the step and driver code written for the
scenarios. Existing production code is judged against them only as a reported observation, never changed.

- Formatter: ruff format (line length 120); code is formatted, never hand-aligned. [tool]
- Naming: names say what a thing is or does, in the domain's own words (invoice, line total, late fee, cents). Booleans read as questions. [review]
- Casing follows PEP 8: `snake_case` functions and variables, `PascalCase` classes, `UPPER_CASE` module constants. [tool]
- Comments explain why, never what (doc comments excepted). No commented-out code, no TODO without an issue reference. [review]
- Public functions and modules have a short docstring stating purpose, inputs, outputs and errors. [review]

## Clean code

- One function does one thing, at one level of abstraction. Target: under 30 lines and cyclomatic complexity under 10. [review]
- No magic numbers: a threshold or a rate gets a named constant, as `billing/fees.py` and `billing/pricing.py` already do. [review]
- No dead code: unused functions, parameters, imports and variables are deleted. [tool]

## No duplicated code (DRY)

- A calculation, validation or constant exists in exactly one place; a step that needs a figure reads it from the scenario, not from a copy of the production constant. [review]
- Shared test setup goes into fixtures or helpers, not copy-pasted.

## Architecture

- Layers: `billing/pricing.py` and `billing/fees.py` hold the pure business rules; `billing/app.py` is the HTTP face that reads the query string and calls them. [review]
- Scenarios exercise the behaviour through the most realistic seam: the HTTP routes for what the routes expose, the pure functions for rules the routes do not reach. [review]

## Folder and file structure

- The existing layout is kept: `billing/` for the application and `tests/` for the greenlight scenarios. [review]
- Fixtures and test data live with the tests and are never imported by `billing/`. [review]

## Error handling and logging

- The existing error shape is described, not changed: a route refuses a missing or invalid parameter with status 400 and `{"error": "..."}`. [review]
- No secrets in tests or logs; `BILLING_SECRET_KEY` is never written into a scenario or a fixture. [review]

## Quality rules

- Linter and type checker: ruff check and mypy for new code, run by `bdd check` once they are in `[adapters.quality]`; until then the auditor checks the diff against them. [tool]
- Lint suppressions need an inline reason and are named in the report. [review]
- Test layers: the greenlight scenarios in `tests/` are the only tests; they are deterministic and independent of order. [review]
- Test names state the behaviour, and tests assert outcomes, not implementation details. [review]
- Coverage: not measured; every rule must have its scenarios (`bdd trace`), and every recorded behaviour of the adopted area is either a rule or a question for the person. [review]

## Deprecation policy

- New code uses the current, non-deprecated API of Python 3.12 and Flask.
- A deprecation warning that existing production code or a dependency raises is reported as a should-fix for the person, never fixed during adoption. [review]
- Before using a library API, its current documentation is read, not recalled from memory.

## API

- Schema file: none; the routes are `GET /invoice` and `GET /late-fee`, both reads that store nothing.
- Error shape: status 400 with `{"error": "..."}` for a missing or invalid parameter.
- Authentication and authorization: none, as the app is today.
- Money is whole cents everywhere, as integers.

## Dependencies

- No dependency is added during adoption; a missing test tool is the person's decision and is named in the report.
