# Adapter guide: python-pytest-bdd

For Python services, libraries and command-line tools tested with `pytest` and `pytest-bdd` (8 or newer).
`bdd adapter apply python-pytest-bdd` copies `templates/` into the project and registers the adapter in
`.bdd/config.toml`. Nothing is overwritten.

## What you get

| Path | What it is | Who edits it |
|---|---|---|
| `tests/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `tests/steps/core_steps.py` | every core instruction of the `base`, `api`, `cli`, `lib` and `data` profiles bound to the drivers | nobody: add project steps in their own module |
| `tests/drivers/system.py` | the seams into the system under test: seed, sign in, read records, HTTP client, jobs, events | step-engineer, from `system.md` |
| `tests/drivers/operations.py` | logical name → API route, command, library function, file, error | step-engineer, from `system.md` |
| `tests/drivers/*.py` (the rest) | clock, stubs, network block, files, comparison helpers, the drivers for API, CLI and library calls | nobody |
| `tests/conftest.py`, `tests/test_features.py` | a fresh world per scenario, no real network, `--bdd-shuffle-seed`, `--bdd-scenario` | nobody |

The `ui` profile is not part of this adapter. Features for a web UI use `ts-playwright-bdd`.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented raises `ExpectedMissing` (the message contains `BDD_EXPECTED_MISSING`):
  that is an *expected* failure. Leave the default in `system.py` until the system has the seam.
- An API operation answered with 404, 405 or 501 fails the step with `status 404`: also expected.
- A logical name with no entry in `operations.py` raises `NotMapped`: that is a defect of the *test*. Fix the
  map, do not touch the feature.
- Import errors, undefined steps, fixture errors and syntax errors are defects too. Anything the patterns in
  `adapter.toml` do not recognise is `unknown` and blocks the gate.

## What is bound

The bind lock covers `tests/steps/`, `tests/drivers/` and the plumbing files: `tests/pytest.ini`,
`tests/conftest.py`, `tests/test_features.py`, `tests/__init__.py` and any `tests/*/conftest.py` (the adapter's
`support` paths and patterns), so nothing that decides how the scenarios run can be changed once the red is proven.
`bdd lock FEAT-n --scope bind --bound` locks exactly these. pytest is started with `-c tests/pytest.ini`,
`--confcutdir tests` and no `PYTEST_*` environment variables, so a `pytest.ini`, `pyproject.toml`, `tox.ini` or
`conftest.py` elsewhere in the project, or a variable set for one command, cannot change which scenarios run.

## Which Python runs the tests

The project's own environment, so the tests see the project's packages: `python = "..."` in `.bdd/config.toml`
(write it with `bdd init --python PATH`), else a `.venv` or `venv` folder in the project, else the interpreter that
runs `bdd`. Environment variables such as `VIRTUAL_ENV` are not consulted: a process can set them for one command, and
this interpreter produces the evidence that gates accept. Each recorded run names its interpreter (path and hash), a
gate refuses a run made with another one, the tripwire watches an in-project environment (the interpreter,
`pyvenv.cfg`, `.pth` files, `sitecustomize.py` and the pytest packages) and agents may neither write into it nor
install packages.

## Do not edit the core drivers

`api.py`, `cli.py`, `lib.py`, `compare.py`, `world.py`, `clock.py`, `stubs.py`, `files.py`, `sockets.py` and
`core_steps.py` belong to the adapter. A project differs in `system.py`, `operations.py` and its own step modules.
When a request needs something the driver does not give, add it as a seam: `System.complete(operation, fields)`
fills in a field the scenario left out (for example the id of the order created earlier), and `System.http()` can
return a wrapper that reshapes a request body.

## Filling in the seams

Use the most realistic seam: the API, then a domain service, then a repository, then the raw database.

- **HTTP client.** `System.http()` returns anything with `request(method, url, json=None, params=None,
  headers=None)` and a response with `status_code` and `json()`/`text`: Starlette/FastAPI `TestClient`, a
  Flask app's test client wrapped to that shape, `httpx.Client(app=...)`. Async apps: run them through the
  framework's synchronous test client, or `anyio`'s portal, inside this one method; keep steps synchronous.
- **Records.** `seed(entity, rows)` creates rows (an unknown column must raise); `records(entity)` returns the
  stored rows without changing anything. `no X records changed` compares `records` before the first action
  with `records` after it, for every entity that a Given step seeded.
- **Isolation.** `reset()` runs after every scenario: roll back the transaction, truncate the tables, or drop
  the in-memory database. Scenarios must pass alone and in any order (`bdd run --isolated`, `--shuffle`).
- **Clock.** Application code should read `world.clock.now()` (a seam). Without a seam, install `time-machine`
  and the clock freezes `datetime.now()` and `time.time()` as well. Say which in `system.md`.
- **Stubs.** Route outbound calls through `world.stubs.call(dependency, operation, request)` (a thin gateway
  object), or aim `respx`/`responses` at `world.stubs.respond`. A call nobody stubbed raises `UnstubbedCall`.
  Real network connections are blocked (loopback stays open) and raise `OutboundNetworkBlocked`.
- **Events and jobs.** `deliver_event`, `run_job` and `published` talk to the application's own handlers and
  an in-memory broker double; the scenario never waits.

## Writing steps and drivers

- Features contain no paths, binaries, selectors or SQL; everything concrete lives in `operations.py` and
  `system.py`.
- A `then` step must assert (`bdd scan` reports S2 otherwise); put the comparison in `compare.py`.
- No `sleep`: wait for the condition (`bdd scan` reports E3).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4).
- Project-specific steps go in their own module under `tests/steps/` and import it from `tests/conftest.py`;
  they must call the same drivers.

## Running

```sh
python -m pytest -q -m FEAT-007                       # one feature (tags are markers)
python -m pytest -q --bdd-scenario "Order of 999"      # one scenario
python -m pytest -q --bdd-shuffle-seed 42              # random order, repeatable
```

`bdd run FEAT-007` does all of this and records the result; always use it for gates.

## Quality checks (opt-in)

greenlight forces no formatter, linter or type checker on a project. If yours uses `ruff` and `mypy`, say so in
`.bdd/config.toml` (your file; the agents cannot edit it) and `bdd check FEAT-n` runs them with the project's own
interpreter; once the tables exist, the implement and verify gates need a current, passing result.

```toml
[adapters.quality.format]
command = '{project_python} -m ruff format --check {root}'

[adapters.quality.lint]
command = '{project_python} -m ruff check {root}'

[adapters.quality.typecheck]
command = '{project_python} -m mypy {root}'
```

Nothing here is a runtime dependency of greenlight or of the adapter; install the tools in the project's environment. To
make deprecations fail, add `filterwarnings = ["error::DeprecationWarning"]` to the bound `tests/pytest.ini`. The
`language-python` card lists the details.

For a service with an interface or a database, the same tables can hold the contract and migration checks the
project already uses. These are examples; install and choose your own, and wrap anything that needs a glob or a pipe in
a script (commands run without a shell):

```toml
[adapters.quality.api-lint]
command = 'spectral lint openapi.yaml'

[adapters.quality.api-breaking]
command = 'oasdiff breaking openapi.base.yaml openapi.yaml --fail-on ERR'

[adapters.quality.migrations-drift]
command = '{project_python} -m alembic check'
```

The cards `api-design`, `database-schema`, `database-migrations`, `database-performance` and `database-engines` say what
each check is for.

## Counting queries (the `data` profile)

The `data` profile adds one instruction, `{operation} ran at most {count:int} queries`, so that an N+1 problem is a
scenario that fails before the code exists. It needs one seam: `System.queries_executed()` returns how many database
statements have run since the scenario began. Create a `QueryCounter` from `tests/drivers/queries.py` when your
`System` is built, attach it to the application's data access, and return its `count`:

```python
class MySystem(System):
    def __init__(self):
        self.counter = QueryCounter()
        self.counter.hook_sqlalchemy(engine)        # or: with connection.execute_wrapper(self.counter.django_wrapper)

    def queries_executed(self) -> int:
        return self.counter.count
```

`World.act()` notes the count before each action; the step compares the difference with the limit. Without the seam the
step fails as an expected failure and every other scenario is unaffected. SQLAlchemy and Django are imported only when
their hook is used; nothing is added to the requirements. Savepoints and transaction control are not counted, and an
action that runs in another process (the command line) cannot be counted this way. Seed at least three records in a
scenario about a collection, or the problem cannot show.

## Known pitfalls

- pytest-bdd turns every tag into a marker; unknown markers only warn (the run command silences it). Do not
  enable `--strict-markers` without registering the trace tags.
- Step patterns that end in `with:` take a table or a doc string: declare `docstring=None, datatable=None` in
  the step function (pytest-bdd leaves them out when the step has none).
- Scenario Outlines produce one test per example row; the scenario name in the report is the outline's name.
- On Windows run from the project root so that `tests` imports resolve (`python -m pytest`, not `pytest`).

## Mutation check (opt-in)

Nothing here is installed or enabled by default. A project that wants to know whether its tests would notice a change
in the code adds an `[adapters.mutation]` table to `.bdd/config.toml` and installs a mutation tool itself (for example
`mutmut`; it is a development tool, never a requirement of greenlight):

```toml
[adapters.mutation]
command    = '{project_python} -m your_mutation_wrapper {files} --report {out}'
threshold  = 80
extensions = [".py"]
```

`bdd mutate FEAT-n` runs the command, without a shell, on the production files that changed since the red was proven
(only those ending in `extensions`), and records the result. The tool must leave a JSON report at `{out}` with whole
numbers `killed` and `survived` (optionally `timeout`, `suspicious`, `skipped`). Most tools do not write exactly this
format: put a few lines of your own (standard library only) around the tool that run it on `{files}` and translate its
results into the two counts, and exit 0 when it has finished. The format and the placeholders are described in `docs/adapters.md`. Once the table
exists, the verify gate requires a result that is current and at or above the threshold.
