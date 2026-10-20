# Running the scenarios in CI

The CI job installs Go, fetches the pinned test modules and runs the suite the same way `bdd run` does. Pin the actions
you use to a commit.

```yaml
- uses: actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e  # v7.0.0
  with:
    go-version: "1.26"
    cache-dependency-path: tests/go.sum
- run: go -C tests mod download
- run: go -C tests test -mod=readonly -count=1 -run '^TestFeatures$' . -args -bdd.tag=FEAT-007 -bdd.out "$PWD/bdd-report.xml"
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

`tests/go.sum` holds the hashes of every module, so a modified or substituted module fails the build. Use one `go test`
per feature, or one run with the tag expression of several features.

For the gates themselves (the approvals in the committed record, locks, a fresh green run, traceability, and the optional
stability, quality and mutation checks) use the complete workflow in `ci/github-actions.yml` next to this file;
`docs/ci.md` explains what each step checks.
