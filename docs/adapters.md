# Adapters

An adapter connects greenlight's language-independent flow to one test stack: it supplies the step bindings, the
drivers that talk to your system, the command that runs the tests, and the rules that tell an expected failure from a
broken test.

## What exists

| Adapter | Status | For |
|---|---|---|
| `python-pytest-bdd` | available | Python services, libraries and command-line tools with `pytest` (8+) and `pytest-bdd` (8+); profiles `base`, `api`, `cli`, `lib` |
| `ts-playwright-bdd` | planned | web UIs (the `ui` profile) |
| `generic-junit` | available | any runner that writes a JUnit report (JUnit 5 with Gradle or Maven, jest, `go test`, `dotnet test`, behave, godog and others); you supply the run command and the step code, the adapter defines and checks the contract |

`bdd adapter list` shows what your installed greenlight offers, and `bdd init --detect` says which one fits the
repository and why. If nothing fits, greenlight says so; it does not pretend.

## The generic-junit adapter

It is never suggested by detection: choose it when no other adapter fits your stack. `bdd init --adapter generic-junit` copies a
small working sample (standard library only) so the setup can be proven, and you then replace the run command in
`.bdd/config.toml` with your runner's. The runner cards in `cards/runners/` (JUnit with Gradle, JUnit with Maven, pytest, jest,
go test, dotnet test) give the command, how to select a feature, where the report goes and what a red looks like. The contract is
short: one command runs one feature, it writes one JUnit file, each test name contains its scenario name, an unbuilt seam fails with
`BDD_EXPECTED_MISSING`, and build errors are loud. See `adapters/generic-junit/guide.md`.

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

See [ci.md](ci.md) for a complete job and `adapters/python-pytest-bdd/ci.md` for the plain test run. The gates themselves (locks, valid red, green) can be re-checked, with the plugin's `tools/bdd/bdd` wrapper (Python 3.11+, nothing to install):
with the plugin's `tools/bdd/bdd` wrapper (Python 3.11+, nothing to install):

```yaml
- run: tools/bdd/bdd lock FEAT-001 --check --require
- run: tools/bdd/bdd run FEAT-001
- run: tools/bdd/bdd classify FEAT-001 --expect green
```

## Writing an adapter

An adapter is a folder with `adapter.toml`, `guide.md` and `templates/`. `adapter.toml` declares its name, profiles,
detection rule, required packages, paths (features, steps, drivers, support files), the run command
(`[run]`: `by_tag`, optional `shuffle` and `isolated` words, `report`, `scrub_env`), the scan patterns used by
`bdd scan`, and the classification patterns (`test_defect`, `expected_fail`). Copy `adapters/python-pytest-bdd` as a
starting point, bind every instruction of the profiles you declare (a test checks this for the bundled adapter), and
describe the red phase in the guide. Placeholders in run commands are filled one word at a time and never go through
a shell.
