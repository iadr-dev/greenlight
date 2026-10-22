# Engineering standards

Status: APPROVED

Approved by the person running the evaluation, for the evaluation runs of this reference app. It is copied into the
project's `.bdd/standards.md` by the evaluation harness, acting as that person.

Each rule is marked [tool] (enforced by a linter, type checker, test or CI step) or [review] (enforced by the auditor
reading the change). A [tool] rule whose tool is not named in an `[adapters.quality.NAME]` table is checked by the
auditor until it is.

## Language and toolchain

- Language and version: TypeScript 5.7 (pinned in `package.json`), compiled to ES2022 modules (`NodeNext`), on Node.js 22 or newer (`engines`).
- Build and package tool: npm with the committed `package-lock.json`; `npm ci` is run by the person, never by an agent.
- Frameworks: none; the library uses only the language and Node's standard library. Tests use Node's own test runner (`node:test`).
- Project type: existing. The library is one module, `src/money.ts`; its conventions are kept unless this file says otherwise.

## Style

- Formatter: none is configured; new code follows the existing style of `src/money.ts` (two-space indent, double quotes, semicolons). [review]
- Naming: names say what a thing is or does, in the domain's own words (amount, currency, minor units, rate). Booleans read as questions (`isCurrency`). [review]
- Casing: `camelCase` functions and variables, `PascalCase` types and classes, `UPPER_CASE` module constants, as the module does. [review]
- Comments explain why, never what (doc comments excepted). No commented-out code, no TODO without an issue reference. [review]
- Exported functions, types and constants have a `/** ... */` doc comment stating purpose, inputs, outputs and errors. [review]

## Clean code

- One function does one thing, at one level of abstraction. Target: under 30 lines and cyclomatic complexity under 10. [review]
- At most 4 parameters; beyond that, pass a named object. No boolean flag parameters that switch behaviour. [review]
- No magic numbers or strings: digits, limits and rates get a named constant, as `MINOR_DIGITS` does. [review]
- No dead code: unused exports, parameters, imports and variables are deleted. [tool]
- Values are immutable (`readonly` fields, no mutation of arguments); functions are pure. [review]

## No duplicated code (DRY)

- A rule, calculation, validation or constant exists in exactly one place; new code reuses `parse`, `MINOR_DIGITS` and `MoneyError` instead of copying them. [review]
- Do not merge code that merely looks alike; two blocks that change for different reasons stay separate.
- Duplication detector: none is run in this project; duplication is checked by review. [review]
- Test code is held to the same rule: shared setup goes into helpers.

## Architecture

- Layers: none; the library is a set of pure functions over the `Money` value. [review]
- No clock, file, network or environment access in the library. [review]
- The public surface is what `src/money.ts` exports; a new export is named in the report. [review]

## Folder and file structure

- The existing layout is kept: `src/` for the library, `unit/` for its unit tests (`*.test.ts`), `tests/` for the greenlight scenarios; compiled output goes to `dist/` and is never committed. [review]
- Fixtures and test data live with the tests and are never imported by `src/`. [review]

## Error handling and logging

- Invalid input throws `MoneyError` with a message that names the value; no other error type is introduced without a reason. [review]
- No silent `catch`; the library does not log. [review]

## Quality rules

- Type checker: `tsc -p .` with `strict` on, as `tsconfig.json` sets; the build fails on a type error. [tool]
- No `any`, no non-null assertions and no unchecked casts without a written reason. [review]
- Suppressions (`@ts-ignore`, `@ts-expect-error`) need an inline reason and are named in the report. [review]
- Every behaviour change has a scenario; a bug fix has a regression scenario or unit test that fails without the fix. [review]
- Test layers: the unit tests in `unit/` and the greenlight scenarios in `tests/`; both are deterministic and independent of order. [review]
- Coverage: not measured; every rule must have its scenarios (`bdd trace`). [review]
- Arithmetic on money is exact: amounts are integers of minor units, and a rule that needs fractions states how it rounds. [review]

## Deprecation policy

- Code uses the current, non-deprecated API of TypeScript 5.7 and Node.js.
- TypeScript has no compiler switch that refuses a deprecated API, and no linter is configured, so the auditor checks the diff against the current documentation. [review]
- Before using a library or Node API, its current documentation is read, not recalled from memory.

## API

- The library's exported functions and types are its interface; changing the signature or meaning of an existing export is breaking and is named in the report.
- Errors: every refusal throws `MoneyError`.

## Dependencies

- A new dependency, runtime or dev, is a decision the person makes; it is named in the report, never added silently.
- The library has no runtime dependencies, and none is added for a feature the language already covers.
