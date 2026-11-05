# Running the scenarios in CI

The CI job installs the test tooling from the lockfile (`pnpm install --frozen-lockfile`), downloads the browser that matches the pinned
Playwright version, and runs the suite the same way `bdd run` does. Pin the actions you use to a commit (the version is in
the comment).

```yaml
- uses: pnpm/action-setup@73e46992e05b19abd31f2f3c20e0e7370d762115  # v6.1.1
  with:
    package_json_file: tests/package.json
- uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1  # v7.1.0
  with:
    node-version: "26"
    cache: pnpm
    cache-dependency-path: tests/pnpm-lock.yaml
- run: pnpm install --frozen-lockfile --ignore-scripts --ignore-workspace --dir tests
- run: node tests/node_modules/@playwright/test/cli.js install --with-deps chromium
- run: node tests/run.mjs --tag FEAT-007 --out bdd-report.xml
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

Start the application in the job, or describe it in `webServer` in `tests/bdd.config.ts` (a bound file) so that the
run starts it. Use one `node tests/run.mjs --tag FEAT-n` per feature.

For the gates themselves (the approvals in the committed record, locks, a fresh green run, traceability, and the optional
stability, quality and mutation checks) use the complete workflow in `ci/github-actions.yml` next to this file;
`docs/ci.md` explains what each step checks.
