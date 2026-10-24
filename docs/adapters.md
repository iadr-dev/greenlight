# Adapters

An adapter connects greenlight's language-independent flow to one test stack: it supplies the step bindings, the
drivers that talk to your system, the command that runs the tests, and the rules that tell an expected failure from a
broken test.

## What exists

| Adapter | Status | For |
|---|---|---|
| `python-pytest-bdd` | available | Python services, libraries and command-line tools with `pytest` (8+) and `pytest-bdd` (8+); profiles `base`, `api`, `cli`, `lib`, `data` |
| `go-godog` | available | Go services, libraries and command-line tools with godog (Cucumber for Go); profiles `base`, `api`, `cli`, `lib`, `data` |
| `dotnet-reqnroll` | available | .NET services, libraries and command-line tools with Reqnroll and xUnit; profiles `base`, `api`, `cli`, `lib`, `data` |
| `ts-cucumber-js` | available | Node and TypeScript services, libraries and command-line tools (and the logic of Expo and React Native apps) with cucumber-js and `tsx`; profiles `base`, `api`, `cli`, `lib`, `data` |
| `dart-flutter-test` | available | Flutter apps and Dart libraries as widget tests with `flutter test` and the official Dart Gherkin parser; profiles `base`, `ui`, `lib` |
| `ts-playwright-bdd` | available | web UIs in a real browser with Playwright and playwright-bdd (TypeScript); profiles `base`, `ui` |
| `java-cucumber-spring` | available | Spring Boot services tested with Cucumber-JVM through `MockMvc`; profiles `base`, `api`, `data` |
| `kotlin-android` | available | Android apps and Kotlin libraries tested with Cucumber-JVM as local JVM unit tests, and (opt-in) the same scenarios on a device through Cucumber-Android, including screens through UI Automator; profiles `base`, `lib`, `data`, `ui` |
| `generic-junit` | available | any runner that writes a JUnit report (JUnit 5 with Gradle or Maven, jest, `go test`, `dotnet test`, behave, godog and others); you supply the run command and the step code, the adapter defines and checks the contract |

`bdd adapter list` shows what your installed greenlight offers, and `bdd init --detect` says which one fits the
repository and why. If nothing fits, greenlight says so; it does not pretend.

## The Go and .NET adapters

Both are the language-specific form of the generic-junit contract: the steps for every core instruction, the drivers (a world
per scenario, the seams `ExpectedMissing`, a clock, stubs, comparison helpers, a query counter) and a run command that
produces the JUnit report are shipped and pinned, so a missing seam is an *expected* failure and a broken test a *defect*
from the first run.

- `go-godog` puts the test code in its own Go module in `tests/` (`go.mod` and `go.sum` pinned, read-only with `-mod=readonly`),
  runs `go -C tests test` and lets godog's junit formatter write the report. See `adapters/go-godog/guide.md`.
- `dotnet-reqnroll` puts the test code in its own project in `tests/` (packages pinned in `packages.lock.json`, restored with
  `RestoreLockedMode`), runs `dotnet test` through a small bound wrapper and lets `JunitXml.TestLogger` write the report. See
  `adapters/dotnet-reqnroll/guide.md`.

- `ts-cucumber-js` puts the test code in its own package in `tests/` (`package.json` and `package-lock.json` pinned, installed
  with `npm ci`), loads the TypeScript steps through `tsx` and lets cucumber-js's JUnit formatter write the report. It has no
  `ui` profile: a web UI is `ts-playwright-bdd`'s job, and the two can share a repository. See `adapters/ts-cucumber-js/guide.md`.

- `dart-flutter-test` puts the test code in its own Dart package in `tests/` (packages pinned in `pubspec.yaml` and hashed in `pubspec.lock`,
  fetched with `flutter pub get --enforce-lockfile`), reads the feature files at run time with `cucumber_gherkin` and runs each scenario as a
  widget test, driving real widgets through a `WidgetTester` with no emulator. `tests/run_flutter.py` turns Flutter's JSON events into the one JUnit
  report. Screens that need a device (platform plugins, swipes, scrolling) are outside it. See `adapters/dart-flutter-test/guide.md`.

Detection suggests them from `go.mod`, from `*.csproj`/`*.sln` for `dart-flutter-test`, from a `pubspec.yaml` that names Flutter, and, for `ts-cucumber-js`, from a `package.json` that names a Node
framework (`express`, `fastify`, `koa`, `@nestjs`, `hono`), a command-line library (`commander`, `yargs`) or `@cucumber/cucumber`. In CI, each adapter has a job that scaffolds it into a
temporary project and runs the sample feature, every core step and a red phase for real, on Linux, Windows and macOS.

A scenario title in another script or with accents (Chinese, an accented Latin letter, or both mixed with ASCII) maps to its
scenario on every adapter: `bdd classify` compares the letters and digits of any script, again without accents, and falls
back to the example id when a test name carries it. Reqnroll, for example, writes `Café: two numbers` as `CafeTwoNumbers`.
The contract tests run such titles in the usual order, shuffled and one scenario per process.

## The JVM adapters

`java-cucumber-spring` and `kotlin-android` are the first-class form of the `generic-junit` contract for the JVM: the same steps, drivers and red-phase rules as the Python adapter, a ready run command (Maven, or Gradle with a bound script that hands Cucumber its settings to the test JVM), and classification of Cucumber, Spring and Kotlin build failures. `bdd init --detect` suggests them from `pom.xml` (Spring Boot) or the Gradle files (the Android Gradle Plugin). They were run for real with Spring Boot 4.1 on Maven 3.9, Kotlin 2.4 on Gradle 9.8 and Cucumber-JVM 8.0, and the CI jobs run the same contract tests on Linux, Windows and macOS: a fresh scaffold goes green, red looks like red, and a scenario whose name is full of regular-expression characters, or written in Chinese or with accents, runs alone. The name filter reaches Maven and Gradle as plain ASCII (characters outside ASCII as `\x{HEX}`), because Windows converts a command line that reaches a `.cmd` or `.bat` launcher to the active code page. Two limits are worth knowing before you choose:

- **Android.** The scenarios are local JVM unit tests, and can also run on a phone or an emulator through Cucumber-Android: a second adapter block, `kotlin-android-device`, runs the same feature files and steps as instrumented tests, and `bdd run` records both sets of cases (tested on a Samsung phone on Android 15). On the JVM, code that calls the Android framework needs a seam (an interface your code owns); Robolectric does not work with Cucumber's JUnit Platform engine. On a device the `ui` profile drives Compose and View screens through UI Automator (scenarios tagged `@ui`; swipes and scrolling are not covered). The guide says exactly what is covered.
- **Network.** The JVM has no process-wide hook for raw sockets, so the Spring adapter's network guard covers the JDK HTTP client and `HttpURLConnection` only; run the tests without network access in CI for the rest.

## The generic-junit adapter

It is never suggested by detection: choose it when no other adapter fits your stack. `bdd init --adapter generic-junit` copies a
small working sample (standard library only) so the setup can be proven, and you then replace the run command in
`.bdd/config.toml` with your runner's. The runner cards in `cards/runners/` (JUnit with Gradle, JUnit with Maven, pytest, jest,
go test, dotnet test, cucumber-js, behave, godog, Cucumber-JVM, Reqnroll) give the command, how to select a feature, where the report goes and what a red looks like. The contract is
short: one command runs one feature, it writes one JUnit file, each test name contains its scenario name, an unbuilt seam fails with
`BDD_EXPECTED_MISSING`, and build errors are loud. See `adapters/generic-junit/guide.md`.

The reports of five runners (cucumber-js, behave, godog, Cucumber-JVM and Reqnroll, all from real runs, with the versions in the fixtures' README)
are kept as fixtures in `tools/bdd/tests/fixtures/junit`, and a test checks that each classifies the same way: a missing
seam or a failed assertion is an expected failure, an undefined step is a test defect, and a pass is a pass. The adapter is also
exercised on two reference apps (`evals/apps/csv-tool`, Go, and `evals/apps/money-lib`, TypeScript) with their own runners in CI.

## Using one

`/greenlight:init` does this for you. By hand:

```sh
bdd init --adapter python-pytest-bdd --autonomy standard
# or, in a project that already has .bdd/:
bdd adapter apply python-pytest-bdd
```

Files are copied into the project and never overwritten; the adapter's tables are added to `.bdd/config.toml`. The
adapter's own guide (`adapters/<name>/guide.md`) explains each file, the red phase, and known pitfalls.

## Which Python runs the tests (python-pytest-bdd)

The tests run in your project's environment, not in the one that runs `bdd`. The interpreter is, in order:
`python = "PATH"` in `.bdd/config.toml` (set with `bdd init --python PATH`), a `.venv` or `venv` in the project, or
else the interpreter running `bdd`. Environment variables such as `VIRTUAL_ENV` are deliberately not consulted: a
command can set them for itself, and the evidence must not depend on that. The runner starts Python in isolated mode,
reads settings only from `tests/pytest.ini`, and does not pass on `PYTHON*`, `PYTEST_*`, `LD_*` or `DYLD_*`
variables. If your project needs `PYTHONPATH`, set `pythonpath` in `tests/pytest.ini` instead.

Install `pytest` and `pytest-bdd` yourself, with your own tool (`uv`, `pip`, `poetry`); the agents are not allowed to
install packages.

## Running in CI

Each adapter ships a complete, pinned GitHub Actions workflow in `adapters/<name>/ci/github-actions.yml`; see
[ci.md](ci.md) for what it checks (approvals from the committed record, locks, a fresh green run, traceability, and the
optional stability, quality and mutation checks) and what it cannot. `adapters/<name>/ci.md` has the plain test run.

## One feature in several repositories

Each repository uses the adapter that fits its own stack (a Python API with `python-pytest-bdd`, a web app with
`ts-playwright-bdd`); the home lists the others:

```toml
[workspace]
web = "../shop-web"
api = "../shop-api"
```

Run commands in a member with `bdd --in web run FEAT-007`, or in all of them with `--workspace`. Details and limits:
[concepts](concepts.md).

## Quality checks (optional)

The project's own formatter, linter, type checker and deprecation check are named in `.bdd/config.toml`; greenlight does
not choose them. One table per check, in the order they should run:

```toml
[adapters.quality.format]
command = '{project_python} -m ruff format --check {root}'

[adapters.quality.lint]
command = '{project_python} -m ruff check {root}'
timeout = 300
```

`command` is split into words before `{root}`, `{python}` and `{project_python}` are filled in, and is started without a
shell in the project, with the same environment rules as `bdd run`. The exit status is the verdict (0 passes); a tool that
is not installed, or that runs too long, is a failed check with the reason. `bdd check FEAT-n` runs them and records the
result in `.bdd/.runs/FEAT-n/quality.json`, together with the source, tests, interpreter and `.bdd/standards.md` it
depends on. Once a table exists, the implement and verify gates need a current, passing result (a feature of kind `adopt`
is not held to it); without it nothing changes. The guides of the Python and the Playwright adapters show suggested
tables, and the language cards under `cards/practices` list the commands for Kotlin, Swift, Go, Rust, TypeScript, Expo
and Next.js.

## API contract and database checks (optional)

The same quality tables hold the checks a service with an interface or a database already uses. greenlight chooses none of them; the practice cards `api-design`, `database-schema`, `database-migrations`, `database-performance` and `database-engines` say what each is for, and the API and data sections of `.bdd/standards.md` hold the project's rules.

```toml
[adapters.quality.api-lint]
command = 'spectral lint openapi.yaml'

[adapters.quality.api-breaking]
command = 'oasdiff breaking openapi.base.yaml openapi.yaml --fail-on ERR'

[adapters.quality.migrations-drift]
command = '{project_python} -m alembic check'
```

Commands run without a shell, so a glob or a pipe goes in a small script the project owns. Queries are counted by the `data` profile: `{operation} ran at most {count:int} queries` fails a scenario when an action runs a query per record (see the adapter guide for the one seam it needs). Plans and counts show "no N+1 here" and "this query can use an index"; they say nothing about speed at production volume.

## Mutation check (optional)

An adapter, or the project, can add an `[adapters.mutation]` table. It is off unless the table exists.

```toml
[adapters.mutation]
command    = '{project_python} -I tests/tools/mutate_python.py --report {out} -- {files}'
threshold  = 80        # percent of killed / (killed + survived); above 0, at most 100
timeout    = 1800      # seconds
extensions = [".py"]   # only changed files with these suffixes are mutated (blank: all)
```

`bdd mutate FEAT-n` splits `command` into words (no shell), fills `{root}`, `{python}`, `{project_python}` and `{out}`,
and replaces a word that is exactly `{files}` with one word per production file added or modified since the red was
proven (committed or not; tests and `.bdd/` are never included). The tool writes a JSON object to `{out}`:

```json
{"killed": 18, "survived": 2, "timeout": 1, "suspicious": 0, "skipped": 0}
```

`{out}` is a file in a fresh private folder outside the project, removed afterwards, so nothing in the project can have
written the report beforehand. `killed` and `survived` are required whole numbers and decide the score; the others
are shown, not counted. The tool must exit 0 once it has finished and state survivors in the report; a non-zero exit
fails the check whatever the report says (a tool that exits non-zero on survivors needs a wrapper that turns that into
exit 0 plus counts; the adapters ship them: `tests/tools/mutate_python.py` for mutmut in `python-pytest-bdd`,
`tests/tools/mutate-ts.mjs` for Stryker in `ts-playwright-bdd`, each described in the adapter's guide; mutmut does not run natively on Windows, so on Windows the Python check runs from WSL in the same checkout, with a Linux `venv` beside the Windows `.venv`, as the guide shows). A missing or malformed report is an error, and so is a report with no mutants, because that proves nothing.
If production files changed but none ends in `extensions`, the check fails too: it covered nothing. Only a feature
that changed no production file at all passes with "nothing to mutate". The result is recorded in
`.bdd/.runs/FEAT-n/mutation.json` (command, exit status, hash of the report, the changed and the mutated files), which
only the command writes. `bdd mutate FEAT-n --check` shows the record
and says whether it is current.

With the table present, the verify gate refuses until the recorded result is current (same production source and tests)
and passes the threshold. Without it nothing changes. See the `mutation-check` card for how to read survivors.

## Several adapters in one repository

A repository with a backend and a web front end has two adapters. Give each its own folder with `--into`:

```sh
bdd adapter apply python-pytest-bdd --into api
bdd adapter apply ts-playwright-bdd --into web
```

The adapter's files are copied under that folder, and its table in `.bdd/config.toml` gets `root = "web"`: its paths
(features, steps, drivers, support files) are relative to that folder, and its run command runs in it. In a run command
`{base}` is that folder (`{root}` is still the project). Nothing changes for a project with one adapter at its top level.

- `bdd run FEAT-n` runs the feature with **every** adapter that has scenarios of it and records one run with all their
  cases; `--adapter NAME` runs just one. An adapter with no scenario of the feature is skipped, and `--isolated` gives each
  adapter only the scenarios in its own feature folder.
- `bdd classify`, `bdd trace`, `bdd scan` and the gates treat the scenarios of both folders as one feature: a rule can
  have an API example and a UI example, the red proof covers both, and so does the green.
- Tag the feature files of both folders with the same `@FEAT-n`, and keep rule and example numbers unique across them.
- The scenario names must be unique across the adapters of one feature, because a test result is matched to its scenario
  by name.

## Writing an adapter

An adapter is a folder with `adapter.toml`, `guide.md` and `templates/`. `adapter.toml` declares its name, profiles,
detection rule, required packages, paths (features, steps, drivers, support files), the run command
(`[run]`: `by_tag`, optional `shuffle` and `isolated` words, `report`, `scrub_env`), the scan patterns used by
`bdd scan`, and the classification patterns (`test_defect`, `expected_fail`). Copy `adapters/python-pytest-bdd` as a
starting point, bind every instruction of the profiles you declare (a test checks this for the bundled adapter), and
describe the red phase in the guide. Placeholders in run commands are filled one word at a time and never go through
a shell, and a value that looks like a placeholder is not filled in again. A runner whose test names are written without spaces or punctuation (Go test functions) uses `{scenario:alnum}`, the letters and digits of the name; a JavaScript runner uses `{scenario:js}` (non-ASCII as `\uXXXX`); a runner that takes a name filter as a regular expression uses `{scenario:regex}`, the scenario name with every regular-expression metacharacter escaped (`isolated = "-Dcucumber.filter.name='\\A{scenario:regex}\\z'"`, where the doubled backslashes are TOML's); never wrap `{scenario}` in `\Q...\E` yourself, because a name containing `\E` would end the quotation.
