# Adapter guide: ts-cucumber-js

For Node and TypeScript services, libraries and command-line tools tested with [cucumber-js](https://github.com/cucumber/cucumber-js)
(the official Cucumber implementation for JavaScript). The profiles are `base`, `api`, `cli`, `lib` and `data`. It is the
TypeScript-specific form of the `generic-junit` contract: cucumber-js writes the JUnit report itself, every core
instruction is bound, and the drivers give a missing seam the right failure. It also fits the logic of Expo and React
Native apps (the code that does not need a screen). A web UI is the job of `ts-playwright-bdd`; both can live in one
repository (`bdd adapter apply … --into DIR`). `bdd adapter apply ts-cucumber-js` copies `templates/` into the project and
registers the adapter in `.bdd/config.toml`. Nothing is overwritten.

## What you get

The test code is a separate package in `tests/`, so it never changes your application's `package.json`. It needs Node 22 or
newer.

| Path | What it is | Who edits it |
|---|---|---|
| `tests/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `tests/sample/` | the code the sample feature tests (delete it with the sample) | nobody |
| `tests/steps/core_steps.ts` | every core instruction of the declared profiles bound to the drivers | nobody: add project steps in their own file |
| `tests/steps/support.ts` | the world of a scenario and the hooks that block the network | nobody |
| `tests/drivers/system.ts` | the seams into the system under test: HTTP client, seed, sign in, flags, events, jobs, records, query counter | step-engineer, from `system.md` |
| `tests/drivers/operations.ts` | logical name → API route, command line, library function, file, error | step-engineer, from `system.md` |
| `tests/drivers/*.ts` (the rest) | the world of a scenario, the clock, the stubs, the network block, comparison helpers | nobody |
| `tests/cucumber.mjs` | the cucumber-js settings: where features and steps are | nobody |
| `tests/package.json`, `tests/package-lock.json`, `tests/tsconfig.json` | the pinned test tooling | the person |

## Setting up

```sh
npm ci --ignore-scripts --prefix tests      # installs the pinned tooling from the lockfile
npm run typecheck --prefix tests            # optional: tsc over the steps and drivers
```

To test your own code, import it from `operations.ts` and `system.ts` with a relative path (`../../src/orders`), or add
your package to `tests/package.json` the usual way. Agents may not install packages; the person does, and chooses when to
change the pinned versions. The run starts the files from `tests/node_modules` and fails if one is missing.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented throws `ExpectedMissing` (the message contains `BDD_EXPECTED_MISSING`): that is an
  *expected* failure. Leave the default in `system.ts` until the system has the seam. `System.http()` is one: until the
  application has an HTTP client, calling an API operation is an expected failure.
- An API operation answered with 404, 405 or 501 fails the step with `status 404`: also expected. An assertion that does
  not hold (`AssertionError`) is expected too.
- A logical name with no entry in `operations.ts` throws `NotMapped`: that is a defect of the *test*. Fix the map, do not
  touch the feature.
- A step nobody wrote (cucumber-js reports it as undefined), two steps that both match, a missing module, a syntax error,
  an unstubbed call (`UnstubbedCall`) and a connection to the internet (`OutboundNetworkBlocked`) are defects. Anything the
  patterns in `adapter.toml` do not recognise is `unknown` and blocks the gate.
- A syntax error or a missing module in a steps file stops cucumber-js before any report is written: `bdd run` shows the
  output and the scenarios are `not-run`.

## What is bound

The bind lock covers `tests/steps/`, `tests/drivers/` and the plumbing files: `tests/cucumber.mjs`, `tests/package.json`,
`tests/package-lock.json` and `tests/tsconfig.json`. A change to any of them makes a recorded run stale.

The run is `node --import ./tests/node_modules/tsx/dist/loader.mjs tests/node_modules/@cucumber/cucumber/bin/cucumber.js
--config tests/cucumber.mjs --tags @FEAT-n --format junit:REPORT`, started without a shell. `NODE_*` (for example
`NODE_OPTIONS`), `TSX_*` and `CUCUMBER_*` are not passed on, because they change what node loads or how cucumber-js runs.
`--order random:N` shuffles the scenarios (repeatably) and `--name "^…$"` runs one scenario, which is what
`bdd run --shuffle` and `--isolated` use.

## Writing steps and drivers

- Features contain no URLs, paths, binaries or SQL; everything concrete lives in `operations.ts` and `system.ts`.
- A step function is a regular `function` (not an arrow, because cucumber-js sets `this` to the world) that takes the
  words its expression matched, then the doc string or the data table. The world is `this` (`GreenlightWorld`).
- Step expressions are regular expressions and **every** matching expression is an error (`Multiple step definitions
  match`, a test defect): a project phrase must not be matched by a core expression. The core steps are written so that
  they do not overlap; keep a project step at least as specific.
- A `then` step must assert (`bdd scan` reports S2 otherwise): call a driver's `assert…` function or `node:assert`.
- No `setTimeout` or `sleep`: wait for the condition (`bdd scan` reports E3).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4).
- Project-specific steps go in their own `.ts` file under `tests/steps/` and must use the same drivers.
- Give the application a clock seam that reads `world.clock.now()` (or hand it the time in `System.setTime`); the process
  clock is not frozen.
- Count queries with `QueryCounter` from `drivers/queries.ts`: call `record(sql)` from the data layer's query hook and
  return `count` from `System.queriesExecuted`.
- The network is blocked through `net.Socket.prototype.connect` (loopback is allowed), which covers `fetch`, `http` and
  `https`. The guard fails closed: a connection whose target it cannot read is refused, and `localhost` must resolve to
  this machine. A client that opens sockets in native code is not covered: stub the dependency, and run the tests without
  network access in CI.
- For a test of an HTTP service, either start it in `System` (listening on a free port) and return
  `httpClient('http://127.0.0.1:PORT')` from `System.http`, or wrap the framework's in-process test client (`supertest`,
  Fastify `inject`) as an `HttpClient`.

## Quality checks

Opt-in; add the tables you want to `.bdd/config.toml` (greenlight chooses none of them). Run them from the package you
test, and treat deprecation as an error so that the code stays on current APIs:

```toml
[adapters.quality.types]
command = 'node tests/node_modules/typescript/bin/tsc -p tests/tsconfig.json'

[adapters.quality.lint]
command = 'npx eslint tests'               # with the project's own ESLint configuration
```

## Known pitfalls

- cucumber-js writes the scenario's report name as `Rule name - Scenario name`; `bdd classify` finds the scenario inside it,
  so a rule name is harmless, but two scenarios whose names are a substring of each other (`Add` and `Add twice`) after
  dropping punctuation should be named apart (see the generic-junit contract).
- A scenario outline repeats its name once per example row: give each row a distinct title with `<param>` placeholders in
  the scenario name so each maps to its own example id.
- Pending steps (`return 'pending'`) are reported as skipped, which blocks the red as "did not run".
- Parallel workers (`--parallel`) are not used: the run is one process, so the order is repeatable with a seed.
- Reading the real clock, the real network or the real environment in the application: the scenario then depends on the
  machine. Inject the clock and the dependencies.
- A scenario title in another script or with accents works: `bdd classify` compares letters and digits of any script, and
  `--name` receives the title with every character outside ASCII written as `\uXXXX`.
