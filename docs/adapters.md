# Adapters

An adapter connects greenlight's language-independent flow to one test stack: it supplies the step bindings, the
drivers that talk to your system, the command that runs the tests, and the rules that tell an expected failure from a
broken test.

## What exists

| Adapter | Status | For |
|---|---|---|
| `python-pytest-bdd` | available | Python services, libraries and command-line tools with `pytest` (8+) and `pytest-bdd` (8+); profiles `base`, `api`, `cli`, `lib` |
| `ts-playwright-bdd` | planned | web UIs (the `ui` profile) |
| `generic-junit` | planned | any runner that writes a JUnit report |

`bdd adapter list` shows what your installed greenlight offers, and `bdd init --detect` says which one fits the
repository and why. If nothing fits, greenlight says so; it does not pretend.

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

See `adapters/python-pytest-bdd/ci.md`. For the gates themselves (locks, approvals, valid red, green) a CI job can run,
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
