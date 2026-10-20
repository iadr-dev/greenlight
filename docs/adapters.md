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

See [ci.md](ci.md) for a complete job and `adapters/python-pytest-bdd/ci.md` for the plain test run. The gates themselves (locks, valid red, green) can be re-checked, with the plugin's `tools/bdd/bdd` wrapper (Python 3.11+, nothing to install):
with the plugin's `tools/bdd/bdd` wrapper (Python 3.11+, nothing to install):

```yaml
- run: tools/bdd/bdd lock FEAT-001 --check --require
- run: tools/bdd/bdd run FEAT-001
- run: tools/bdd/bdd classify FEAT-001 --expect green
```

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
