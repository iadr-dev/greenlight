# Running the scenarios in CI

The CI job installs the test tooling from the lockfile (`npm ci`) and runs the suite the same way `bdd run` does. Pin the
actions you use to a commit (the version is in the comment).

```yaml
- uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1  # v7.1.0
  with:
    node-version: "22"
    cache: npm
    cache-dependency-path: tests/package-lock.json
- run: npm ci --ignore-scripts --prefix tests
- run: >
    node --import ./tests/node_modules/tsx/dist/loader.mjs tests/node_modules/@cucumber/cucumber/bin/cucumber.js
    --config tests/cucumber.mjs --tags @FEAT-007 --format junit:bdd-report.xml
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

Start the application in the job when the scenarios call a running service, or start it from `System` (a bound file) so
that the run starts it. Use one run per feature.

For the gates themselves (the approvals in the committed record, locks, a fresh green run, traceability, and the optional
stability, quality and mutation checks) use the complete workflow in `ci/github-actions.yml` next to this file;
`docs/ci.md` explains what each step checks.
