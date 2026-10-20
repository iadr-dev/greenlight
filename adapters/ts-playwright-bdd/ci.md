# Running the scenarios in CI

The CI job installs the test tooling from the lockfile (`npm ci`), downloads the browser that matches the pinned
Playwright version, and runs the suite the same way `bdd run` does. Pin the actions you use to a commit.

```yaml
- uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1  # v7.1.0
  with:
    node-version: "22"
    cache: npm
    cache-dependency-path: tests/package-lock.json
- run: npm ci --ignore-scripts --prefix tests
- run: node tests/node_modules/@playwright/test/cli.js install --with-deps chromium
- run: node tests/run.mjs --tag FEAT-007 --out bdd-report.xml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

Start the application in the job, or describe it in `webServer` in `tests/bdd.config.ts` (a bound file) so that the
run starts it. Use one `node tests/run.mjs --tag FEAT-n` per feature.

For the gates themselves (locks, approvals, valid red, green) run `bdd lock FEAT-n --check --require` and
`bdd run FEAT-n` followed by `bdd classify FEAT-n --expect green` with the greenlight plugin's `tools/bdd/bdd` wrapper;
it needs Python 3.11 or newer and nothing to install. See `docs/ci.md` for a complete job.
