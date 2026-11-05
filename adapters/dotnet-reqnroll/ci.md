# Running the scenarios in CI

The CI job installs the .NET SDK, restores the pinned packages from the lock file (a changed or substituted package fails
the restore) and runs the suite the same way `bdd run` does. Pin the actions you use to a commit.

```yaml
- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0  # v7.1.0
  with:
    python-version: "3.14"
- uses: actions/setup-dotnet@0f4a354dd5547a28c70b7853dbd95d5b67886e73  # v6.1.0
  with:
    dotnet-version: "10.0.x"
    cache: true
    cache-dependency-path: tests/packages.lock.json
- run: dotnet restore tests --locked-mode
- run: python -I tests/run_dotnet.py --tag FEAT-007 --out "$PWD/bdd-report.xml"
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

`tests/packages.lock.json` holds the hash of every package. Use one `run_dotnet.py` per feature.

For the gates themselves (the approvals in the committed record, locks, a fresh green run, traceability, and the optional
stability, quality and mutation checks) use the complete workflow in `ci/github-actions.yml` next to this file;
`docs/ci.md` explains what each step checks.
