# Adapters

An adapter connects greenlight's language-independent flow to one test stack: it supplies the step bindings, the
drivers that talk to your system, the command that runs the tests, and the rules that tell an expected failure from a
broken test.

## What exists

| Adapter | Status | For |
|---|---|---|
| `python-pytest-bdd` | available | Python services, libraries and command-line tools with `pytest` (8+) and `pytest-bdd` (8+); profiles `base`, `api`, `cli`, `lib`, `data` |
| `ts-playwright-bdd` | available | web UIs in a real browser with Playwright and playwright-bdd (TypeScript); profiles `base`, `ui` |
| `generic-junit` | available | any runner that writes a JUnit report (JUnit 5 with Gradle or Maven, jest, `go test`, `dotnet test`, behave, godog and others); you supply the run command and the step code, the adapter defines and checks the contract |

`bdd adapter list` shows what your installed greenlight offers, and `bdd init --detect` says which one fits the
repository and why. If nothing fits, greenlight says so; it does not pretend.

## The generic-junit adapter

It is never suggested by detection: choose it when no other adapter fits your stack. `bdd init --adapter generic-junit` copies a
small working sample (standard library only) so the setup can be proven, and you then replace the run command in
`.bdd/config.toml` with your runner's. The runner cards in `cards/runners/` (JUnit with Gradle, JUnit with Maven, pytest, jest,
go test, dotnet test, cucumber-js, behave, godog, Cucumber-JVM, Reqnroll) give the command, how to select a feature, where the report goes and what a red looks like. The contract is
short: one command runs one feature, it writes one JUnit file, each test name contains its scenario name, an unbuilt seam fails with
`BDD_EXPECTED_MISSING`, and build errors are loud. See `adapters/generic-junit/guide.md`.

The reports of five runners (cucumber-js and behave from real runs, godog, Cucumber-JVM and Reqnroll from their documented
format) are kept as fixtures in `tools/bdd/tests/fixtures/junit`, and a test checks that each classifies the same way: a missing
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
command    = '{project_python} -m your_mutation_wrapper {files} --report {out}'
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
fails the check whatever the report says (a wrapper turns a tool that exits non-zero on survivors into exit 0 plus
counts). A missing or malformed report is an error, and so is a report with no mutants, because that proves nothing.
If production files changed but none ends in `extensions`, the check fails too: it covered nothing. Only a feature
that changed no production file at all passes with "nothing to mutate". The result is recorded in
`.bdd/.runs/FEAT-n/mutation.json` (command, exit status, hash of the report, the changed and the mutated files), which
only the command writes. `bdd mutate FEAT-n --check` shows the record
and says whether it is current.

With the table present, the verify gate refuses until the recorded result is current (same production source and tests)
and passes the threshold. Without it nothing changes. See the `mutation-check` card for how to read survivors.

## Writing an adapter

An adapter is a folder with `adapter.toml`, `guide.md` and `templates/`. `adapter.toml` declares its name, profiles,
detection rule, required packages, paths (features, steps, drivers, support files), the run command
(`[run]`: `by_tag`, optional `shuffle` and `isolated` words, `report`, `scrub_env`), the scan patterns used by
`bdd scan`, and the classification patterns (`test_defect`, `expected_fail`). Copy `adapters/python-pytest-bdd` as a
starting point, bind every instruction of the profiles you declare (a test checks this for the bundled adapter), and
describe the red phase in the guide. Placeholders in run commands are filled one word at a time and never go through
a shell.
