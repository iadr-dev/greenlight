# Engineering standards

Written by the person running the evaluation, for the evaluation runs of this reference app. It is copied into the
project's `.bdd/standards.md` by the evaluation harness, acting as that person.

Each rule is marked [tool] (enforced by a linter, type checker, test or CI step) or [review] (enforced by the auditor
reading the change). A [tool] rule whose tool is not named in an `[adapters.quality.NAME]` table is checked by the
auditor until it is.

## Language and toolchain

- Language and version: JavaScript (ES modules, JSX), on Node.js 20.9 or newer (`engines`).
- Build and package tool: npm with the committed `package-lock.json`; `npm ci` is run by the person, never by an agent.
- Frameworks: Next.js 16.4 with the app router, React 19.3 (pinned in `package.json`).
- Project type: existing. Its conventions are kept unless this file says otherwise.

## Style

- Formatter: none is configured; new code follows the existing style (two-space indent, single quotes, semicolons). [review]
- Naming: names say what a thing is or does, in the domain's own words (cart, order, product, total). Booleans read as questions. [review]
- Casing: `camelCase` functions and variables, `PascalCase` React components, `UPPER_CASE` module constants, as `lib/store.js` does. [review]
- Comments explain why, never what. No commented-out code, no TODO without an issue reference. [review]
- A module starts with a one-line comment saying what it holds, as `lib/store.js` does. [review]

## Clean code

- One function or component does one thing. Target: under 30 lines and cyclomatic complexity under 10. [review]
- No magic numbers or strings: limits, prices and messages get a named constant. [review]
- No dead code: unused exports, parameters, imports and variables are deleted. [review]
- The shop's rules are pure functions over a plain state object in `lib/store.js`; pages and route handlers call them and render or answer. A rule never lives in a page. [review]

## No duplicated code (DRY)

- A rule, calculation, validation or message exists in exactly one place; new code reuses `lib/store.js` and `lib/session.js` instead of copying them. [review]
- Do not merge code that merely looks alike; two blocks that change for different reasons stay separate.
- Duplication detector: none is run in this project; duplication is checked by review. [review]

## Architecture

- Layers: pages and API route handlers under `app/` (transport and rendering), rules and state in `lib/store.js`, the session in `lib/session.js`. Dependencies point from `app/` to `lib/`, never back. [review]
- State stays in memory and deterministic; nothing calls the network. [review]
- The test endpoints under `app/api/test/` answer only when `SHOP_TEST_ENDPOINTS=1`, and production pages never depend on them. [review]

## Folder and file structure

- The framework's layout wins: the app router in `app/` (one folder per page or route), shared code in `lib/`, unit tests in `test/` (`*.test.js`), and `tests/` for the greenlight scenarios. [review]
- No `utils` or `helpers` modules; name code for what it does. [review]
- Fixtures and test data live with the tests and are never imported by `app/` or `lib/`. [review]

## Error handling and logging

- No silent `catch`. A refused action shows the user one of the `MESSAGES` in an element with `role="alert"`, as the pages do today. [review]
- Input from a form or a request body is checked in the route handler before it reaches the rules. [review]
- No secrets or personal data in logs. [review]

## Quality rules

- Build: `npm run build` must succeed with no errors and no warnings from the project's own code. [tool]
- Every behaviour change has a scenario; a bug fix has a regression scenario or unit test that fails without the fix. [review]
- Test layers: the unit tests in `test/` (rules without a server) and the greenlight scenarios in `tests/`, which drive a real browser against the built app; both are deterministic and independent of order. [review]
- Coverage: not measured; every rule must have its scenarios (`bdd trace`). [review]
- Security: a page or route that needs a signed-in user checks the session on the server and sends a visitor to `/login`, as `/cart` does; a test that a visitor is refused exists for every such rule. [review]

## Performance

- Every list a page renders is bounded by the data the app holds; a new list states its limit. [review]
- No optimisation without a measurement that justified it. [review]

## User interface

- Accessibility: every control has an accessible name (a visible label or button text), forms work from the keyboard, and errors are announced through `role="alert"`. [review]
- The app ships one language, English, and keeps user-facing text in `MESSAGES` and in the page components, as it does today; translation is out of scope. [review]
- Empty and error states are shown for every page that lists data (an empty cart says so). [review]

## Deprecation policy

- Code uses the current, non-deprecated API of Next.js 16 and React 19 (the app router, server components and route handlers; no `pages/` router, no `getServerSideProps`).
- No linter is configured (Next.js 16 removed `next lint`), so deprecated APIs are found by the build's warnings and by the auditor reading the diff against the current documentation. [review]
- Before using a Next.js or React API, its current documentation is read, not recalled from memory.

## Dependencies

- A new dependency, runtime or dev, is a decision the person makes; it is named in the report, never added silently.
- Before adding one, check that Next.js, React or the platform already does the job.
