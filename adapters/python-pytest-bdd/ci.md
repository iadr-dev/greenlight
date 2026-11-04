# Running the scenarios in CI

The CI job needs the project's own dependencies plus `pytest` and `pytest-bdd`. It runs the suite the same
way `bdd run` does, and keeps the JUnit report. Actions are pinned to a commit (the version is in the comment):

```yaml
- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0  # v7.1.0
  with:
    python-version: "3.12"
- uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2  # v10.3.3
- run: |
    uv venv .venv
    uv pip install --python .venv/bin/python -r requirements.txt pytest pytest-bdd
- run: .venv/bin/python -m pytest -q -p no:cacheprovider --junitxml=bdd-report.xml
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

For the gates themselves (the approvals in the committed record, locks, a fresh green run, traceability, and the optional
stability, quality and mutation checks) use the complete workflow in `ci/github-actions.yml` next to this file; `docs/ci.md`
explains what each step checks.
