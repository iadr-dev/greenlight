# Running the scenarios in CI

The CI job needs the project's own dependencies plus `pytest` and `pytest-bdd`. It runs the suite the same
way `bdd run` does, and keeps the JUnit report:

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: python -m pip install -r requirements.txt pytest pytest-bdd
- run: python -m pytest -q -p no:cacheprovider --junitxml=bdd-report.xml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

For the gates themselves (locks, approvals, valid red, green) run `bdd lock FEAT-n --check --require` and
`bdd run FEAT-n` followed by `bdd classify FEAT-n --expect green` with the greenlight plugin's
`tools/bdd/bdd` wrapper; it needs Python 3.11 or newer and nothing to install.
