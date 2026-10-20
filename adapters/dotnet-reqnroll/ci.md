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

For the gates themselves (locks, approvals, valid red, green) run `bdd lock FEAT-n --check --require` and
`bdd run FEAT-n` followed by `bdd classify FEAT-n --expect green` with the greenlight plugin's `tools/bdd/bdd` wrapper;
it needs Python 3.11 or newer and nothing to install. See `docs/ci.md` for a complete job.
