---
id: flutter-test
kind: runner
apply_when: "a Flutter or Dart project whose scenarios run as widget tests with flutter test (the dart-flutter-test adapter)"
---
## Run

Use the `dart-flutter-test` adapter: it ships the Gherkin runner (`tests/bdd_test.dart`, built on the official `cucumber_gherkin`
parser), every core step, and `tests/run_flutter.py`, which runs `flutter test --no-pub --reporter json` and writes the one
JUnit file `bdd run` reads. Nothing else is needed:

```toml
[adapters.run]
by_tag = '{python} -I tests/run_flutter.py --tag {tag}'
report = '--out {out}'
shuffle = '--seed {seed}'
isolated = '--scenario "{scenario}"'
```

For a project that already writes its own Dart tests, `flutter test --reporter json` is the stream to convert; the
`bdd_widget_test` package generates one test file per feature, but it ignores doc strings, which the core steps use, so the adapter
reads the features itself.

## Report

One `<testcase>` per scenario with `classname` `bdd` and the scenario name as `name`. A widget test whose body throws fails with
"Test failed. See exception logs above."; the script reads the real exception class and message from the report Flutter printed,
so `ExpectedMissing`, `TestFailure` and `StepError` reach the classifier.

## What red looks like

- A seam or a component that does not exist yet is `ExpectedMissing` (`BDD_EXPECTED_MISSING`): an expected failure.
- A failing `expect` is a `TestFailure` with `Expected: ... Actual: ...`: also expected.
- An unmapped name (`NotMapped`), an undefined or ambiguous step and an unstubbed call are test defects.
- A Dart compile error, a missing package or a feature that does not parse stops `flutter test` before any test starts: no report
  is written, the scenarios are `not-run`, and the compiler output is shown.

## Known pitfalls

- Running `flutter test` by hand instead of `bdd run`: only a recorded run can back a gate.
- A changed `pubspec.yaml` without `flutter pub get --enforce-lockfile`: the run uses `--no-pub` and stops, by design.
- A widget that animates forever makes `pumpAndSettle` time out; give the screen a state without the animation.
- `flutter` must be on `PATH` for the process that runs `bdd` (on Windows it is `flutter.bat`).
