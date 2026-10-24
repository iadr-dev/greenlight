# Running the scenarios in CI

The CI job installs the Flutter SDK, fetches the pinned packages from the lock file (`--enforce-lockfile`) and runs the suite the
same way `bdd run` does. Pin the actions you use to a commit (the version is in the comment).

```yaml
- uses: subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2  # v2.23.0
  with:
    channel: stable
    cache: true
- run: flutter pub get --enforce-lockfile
  working-directory: tests
- run: python -I tests/run_flutter.py --tag FEAT-007 --out bdd-report.xml
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
  if: always()
  with:
    name: bdd-report
    path: bdd-report.xml
```

Use one run per feature. A widget test needs no emulator, so the job runs on any runner with the SDK.

For the gates themselves (the approvals in the committed record, locks, a fresh green run, traceability, and the optional
stability, quality and mutation checks) use the complete workflow in `ci/github-actions.yml` next to this file;
`docs/ci.md` explains what each step checks.
