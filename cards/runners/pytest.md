---
id: pytest
kind: runner
apply_when: "a Python project tested with plain pytest functions rather than pytest-bdd (the generic-junit adapter); with pytest-bdd prefer the python-pytest-bdd adapter"
---
## Run

Mark the tests of a feature with a marker named like the tag (`FEAT_007`) and register it in `pytest.ini`:

```ini
[pytest]
markers =
    FEAT_007: order discounts
```

```toml
[adapters.run]
by_tag = '{project_python} -X utf8 -I -m pytest -c pytest.ini -q -p no:cacheprovider -m {marker}'
report = '--junitxml={out}'
scrub_env = ["PYTEST_"]
```

pytest takes the report path as an option, so no wrapper is needed. Put `pytest.ini` and `conftest.py` in `support`, so
the files that decide which tests run are bound. Shuffling needs a plugin: with `pytest-randomly` installed,
`shuffle = '--randomly-seed={seed}'`.

## Report

`--junitxml` writes one file. The `name` is the test function, so `test_two_numbers_are_added` maps to "Two numbers are
added". Keep `junit_family = xunit2` (the default in current pytest).

## What red looks like

An unbuilt seam: `raise AssertionError("BDD_EXPECTED_MISSING: ...")` or `pytest.fail("BDD_EXPECTED_MISSING ...")`. The case is a
`<failure message="AssertionError: ...">`. An import error in a test module is a collection error: an `<error>` whose text
contains `ImportError` (a test defect).

## Known pitfalls

- An unregistered marker is only a warning, and `-m` then selects nothing; register every marker or use `--strict-markers`.
- Parametrised tests produce one case per parameter set (`test_x[1]`); the name still contains the scenario name.
- `PYTEST_ADDOPTS` can change which tests run; `scrub_env` keeps it out of the run.
- A conftest in a parent folder can change behaviour; confine pytest with `-c` and `--confcutdir` as the Python adapter does.
