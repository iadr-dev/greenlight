# Running the scenarios in CI

The CI job installs the .NET SDK, restores the pinned packages from the lock file (a changed or substituted package fails
the restore) and runs the suite the same way `bdd run` does. Pin the actions you use to a commit.

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- uses: actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68  # v6.0.0
  with:
    dotnet-version: "10.0.x"
    cache: true
    cache-dependency-path: tests/packages.lock.json
- run: dotnet restore tests --locked-mode
- run: python -I tests/run_dotnet.py --tag FEAT-007 --out "$PWD/bdd-report.xml"
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

`tests/packages.lock.json` holds the hash of every package. Use one `run_dotnet.py` per feature.

For the gates themselves (the approvals in the committed record, locks, a fresh green run, traceability, and the optional
stability, quality and mutation checks) use the complete workflow in `ci/github-actions.yml` next to this file;
`docs/ci.md` explains what each step checks.
