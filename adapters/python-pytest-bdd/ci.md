# Running the scenarios in CI

The CI job needs the project's own dependencies plus `pytest` and `pytest-bdd`. It runs the suite the same
way `bdd run` does, and keeps the JUnit report. Actions are pinned to a commit (the version is in the comment):

```yaml
- uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
  with:
    python-version: "3.12"
- uses: astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884  # v10.3.0
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
