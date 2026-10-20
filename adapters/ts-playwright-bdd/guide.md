# Adapter guide: ts-playwright-bdd

For web interfaces tested in a real browser with [Playwright](https://playwright.dev) and
[playwright-bdd](https://vitalets.github.io/playwright-bdd) (TypeScript). The profiles are `base` and `ui`: the
application is driven through its pages, and the system behind it is seeded and read through seams. `bdd adapter
apply ts-playwright-bdd` copies `templates/` into the project and registers the adapter in `.bdd/config.toml`.
Nothing is overwritten.

## What you get

| Path | What it is | Who edits it |
|---|---|---|
| `tests/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `tests/sample/` | the page the sample feature opens (delete it with the sample) | nobody |
| `tests/steps/core_steps.ts` | every core instruction of the `base` and `ui` profiles bound to the drivers | nobody: add project steps in their own module |
| `tests/steps/fixtures.ts`, `tests/steps/parameters.ts` | the per-scenario `world` fixture and the placeholders of the step patterns | nobody |
| `tests/drivers/system.ts` | the seams into the system behind the pages: base URL, seed, sign in, flags, events, jobs, records | step-engineer, from `system.md` |
| `tests/drivers/operations.ts` | logical name → page address, component locator, external dependency endpoint | step-engineer, from `system.md` |
| `tests/drivers/*.ts` (the rest) | the world, the clock, the stubs and the network block, the user actions and checks, comparison helpers | nobody |
| `tests/bdd.config.ts`, `tests/run.mjs`, `tests/junit-reporter.mjs`, `tests/tsconfig.json` | how scenarios are generated, selected, run and reported | nobody |
| `tests/package.json`, `tests/package-lock.json` | the pinned test tooling, kept apart from the application's own `package.json` | the person |

The `api`, `cli` and `lib` profiles are not part of this adapter. A service without a browser uses
`python-pytest-bdd`.

## Setting up

The test tooling lives in `tests/` and is installed on its own, from the lockfile, so it never touches the
application's dependencies:

```sh
npm ci --ignore-scripts --prefix tests
node tests/node_modules/@playwright/test/cli.js install chromium
```

`--ignore-scripts` keeps the packages' install scripts from running; the browser is downloaded by the second command,
not by a script. Agents may not install packages; the person does, and chooses when to change the pinned versions.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented throws `ExpectedMissing` (the message contains `BDD_EXPECTED_MISSING`): that is an
  *expected* failure. Leave the default in `system.ts` until the system has the seam. `System.baseUrl()` is one: until
  the application exists, opening one of its pages is an expected failure.
- A page that answers 404, 405 or 501 fails the step with `status 404`: also expected.
- A component that is not on the page yet fails with `expect(locator).toBeVisible()` (after the timeout in
  `bdd.config.ts`): also expected.
- A logical name with no entry in `operations.ts` throws `NotMapped`: that is a defect of the *test*. Fix the map,
  do not touch the feature.
- A locator that matches several elements (`strict mode violation`), a missing step definition, a type or syntax
  error, a missing module: defects too. Anything the patterns in `adapter.toml` do not recognise is `unknown` and
  blocks the gate.
- A page that calls an external service nobody stubbed (`UnstubbedCall`) or reaches a host outside the application
  (`OutboundNetworkBlocked`) is `unknown`: stub the dependency, or the call does not belong in the page.

## What is bound

The bind lock covers `tests/steps/`, `tests/drivers/` and the plumbing files: `tests/bdd.config.ts`, `tests/run.mjs`,
`tests/junit-reporter.mjs`, `tests/tsconfig.json`, `tests/package.json` and `tests/package-lock.json` (the adapter's
`support` paths), so nothing that decides which scenarios run, how they run or what is reported can be changed once the
red is proven. `bdd lock FEAT-n --scope bind --bound` locks exactly these.

`bdd run` starts `node tests/run.mjs`, which generates the test files from the features, runs Playwright with
`-c tests/bdd.config.ts`, and writes the JUnit report through the bound reporter. No shell is involved. Variables that
change what node loads or how Playwright behaves (`NODE_*`, `PW_*`, `PLAYWRIGHT_*`) are not passed on.

**Not covered.** The packages in `tests/node_modules` are not hashed as a whole. The tripwire watches npm's record of the
installed tree (`.package-lock.json`), the entry points the run starts and the manifests of the four test packages; agents
may neither write there nor install packages (the guard refuses it, for any `node_modules` folder, as a best-effort text
check), and the lockfile is bound. Install from the lockfile with `npm ci` and do not run `npm install` in `tests/` during
a feature. The node
program itself is whichever `node` is on `PATH`. Unlike the Python adapter, a gate does not compare the runtime that
produced a recorded run. Run the gates in CI as well (see `ci.md`).

## Do not edit the core drivers

`world.ts`, `ui.ts`, `compare.ts`, `clock.ts`, `stubs.ts`, `errors.ts` and `core_steps.ts` belong to the adapter. A
project differs in `system.ts`, `operations.ts` and its own step modules. When a step needs something the driver does
not give, add it as a seam in `System`, not as a change to a core driver.

## Filling in the seams

Use the most realistic seam: the application's own API or a test endpoint, then a domain service, then a repository,
then the raw database.

- **Base URL.** `System.baseUrl()` returns the address the pages are opened under, such as `http://localhost:3000`. To
  start the application for the run, describe it in `webServer` in `tests/bdd.config.ts` (it is bound, so decide it
  before the bind gate).
- **Pages and components.** `PAGES` maps a page name to a path (or a complete URL). `TARGETS` maps a component name to
  `{ role, name }`, `{ label }`, `{ text }` or `{ testId }`: prefer what a user perceives to markup.
- **Sign in.** `authenticate(actor, role)` returns what the browser needs: a Playwright `storageState` (cookies, local
  storage) and/or extra headers. Each actor gets a browser context of their own.
- **Records.** `seed(entity, rows)` creates rows (an unknown column must throw); `records(entity)` returns the stored
  rows without changing anything. `no X records changed` compares `records` before the first action with `records`
  after it, for every entity that a Given step seeded.
- **Isolation.** `reset()` runs after every scenario: roll back, truncate, or drop the in-memory data. Scenarios must
  pass alone and in any order (`bdd run --isolated`). Shuffling is not offered by this adapter: Playwright has no
  repeatable order option, so `bdd run --shuffle` says so instead of pretending.
- **Clock.** Once a scenario sets the time, every browser context of the scenario runs on a frozen clock that moves
  only when the scenario says time passes (`2 days passes`). It covers the browser: `Date`, timers and intervals. If
  the server needs the same time, implement `System.setTime(moment)`; say which in `system.md`.
- **Stubs.** Name an external HTTP dependency in `DEPENDENCIES` (method and URL of each operation). Requests of the
  page to the application itself, to `localhost` and to local schemes pass; requests to a stubbed operation are
  answered with what the scenario gave and recorded; every other request is refused and fails the scenario at its end.
- **Events and jobs.** `deliverEvent`, `runJob` and `published` talk to the application's own handlers and a
  broker double; the scenario never waits.
- **Application state.** `the application state is:` writes to the browser's local (or, with a `storage` column,
  session) storage before the page's own scripts run; `the application state includes:` reads it back.

## Writing steps and drivers

- Features contain no URLs, selectors or SQL; everything concrete lives in `operations.ts` and `system.ts`.
- A `Then` step must assert (`bdd scan` reports S2 otherwise); the web-first `expect(...)` assertions wait for the
  condition, so there is nothing to sleep for (`bdd scan` reports E3 for `waitForTimeout`, `setTimeout` and `sleep`).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4 for
  `stubs.respond("name", ...)` with a name that is not listed).
- Project-specific steps go in their own `.ts` module under `tests/steps/`, built with `createBdd(test)` from
  `./fixtures`, and call the same drivers. Step patterns are Cucumber expressions; the placeholders of the core
  instructions (`{actor}`, `{target}`, `{entity}` …) are defined in `parameters.ts`.

## Running

```sh
node tests/run.mjs --tag FEAT-007 --out report.xml                     # one feature
node tests/run.mjs --tag FEAT-007 --scenario "Order of 999" --out r.xml  # one scenario
npm run typecheck --prefix tests                                        # type-check the drivers and steps
```

`bdd run FEAT-007` does all of this and records the result; always use it for gates.

## Quality checks (opt-in)

greenlight forces no formatter, linter or type checker on a project. If yours uses `tsc` and `eslint`, say so in
`.bdd/config.toml` (your file; the agents cannot edit it) and `bdd check FEAT-n` runs them; once the tables exist, the
implement and verify gates need a current, passing result.

```toml
[adapters.quality.typecheck]
command = 'npx tsc --noEmit'

[adapters.quality.lint]
command = 'npx eslint .'
```

Agents cannot run `npx` or install packages: the orchestrator runs `bdd check`. Set the `@typescript-eslint/no-deprecated`
rule to `error` in the ESLint configuration so that use of a deprecated API fails the lint. The `language-typescript`
card (and `language-expo` or `language-nextjs`) lists the details.

## Known pitfalls

- A tag selects whole: `FEAT-7` does not run `FEAT-70`.
- Scenario Outlines produce one test per example row; `bdd` reads the outline's name and the case is named after the
  outline and the example. Keep `examplesTitleFormat` in `bdd.config.ts` as it is: the reporter relies on it.
- Step patterns that end in `with:` take a table or a doc string: declare the last parameter as `Data` (a table, a
  string, or nothing).
- `file:` pages can be opened without a base URL (the sample does), but a page served from the application should use
  `baseUrl()` so that the red phase fails for the right reason.
- The browsers are not part of the lockfile. `playwright install` downloads the build that matches the pinned version;
  in CI cache it per version.
