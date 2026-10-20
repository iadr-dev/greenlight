---
id: behave
kind: runner
apply_when: "a Python project whose scenarios run with behave (the generic-junit adapter)"
---
## Run

behave writes one JUnit file per feature file into a directory, so use the wrapper, which deletes old files and merges
the new ones:

```toml
[adapters.run]
by_tag = '{python} -I tests/run_junit.py --reports "reports/behave/*.xml" --command "{project_python} -m behave --tags=@{tag} --junit --junit-directory reports/behave"'
report = '--out {out}'
```

Add `tests/run_junit.py`, `behave.ini` (or `setup.cfg`/`pyproject.toml` section) and `features/environment.py` to `support`.
If your features live in `tests/features`, say so in `behave.ini` (`paths = tests/features`).

## Report

`TESTS-<feature file>.xml`: `classname` is `<file>.<feature name>`, `name` is the scenario name. Verified against the current
`behave` release (the files are in `tools/bdd/tests/fixtures/junit/behave`).

## What red looks like

- A step that raises `AssertionError("BDD_EXPECTED_MISSING: add")` is a `<failure type="AssertionError" message="BDD_EXPECTED_MISSING: add">`
  with the failing step in the body: an expected failure. A plain `assert` failing is the same.
- A step nobody defined is `<error type="NoneType" message="None">` with `... undefined in 0.000s` in the body. The default
  patterns call it a test defect. Any other exception in a step (`ImportError`, `NameError`) is a defect too.

## Known pitfalls

- `--tags=@FEAT-007` needs the tag on the `Feature:` line to select every scenario of the feature.
- A scenario that is skipped (`@skip`, or after a failed step in a `Background`) is `skipped` and blocks the red as "did not run".
- behave exits with 1 when a scenario fails; that is normal and the wrapper keeps the status. An exit with no report files
  (a syntax error in `environment.py`) is reported by the wrapper as "wrote no file".
- behave has no seeded shuffle; leave `shuffle` out and `bdd run --shuffle` will say so.
