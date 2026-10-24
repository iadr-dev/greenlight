# Adapter guide: dart-flutter-test

For Flutter apps and the Dart libraries inside them, tested as **widget tests** with `flutter test`: the scenarios run in the
Flutter test environment, drive real widgets through a `WidgetTester` (tap, enter text, read what is on the screen) and need
no emulator and no device. The profiles are `base`, `ui` and `lib`. It is the Dart-specific form of the `generic-junit`
contract: `flutter test` reports as JSON events, one bound script turns them into the JUnit report, every core instruction is
bound, and the drivers give a missing seam the right failure. `bdd adapter apply dart-flutter-test` copies `templates/` into
the project and registers the adapter in `.bdd/config.toml`. Nothing is overwritten.

## What it covers, and what it does not

| Covered | Not covered by this adapter |
|---|---|
| screens and their widgets: opening a page, tapping, entering text, what a component shows, whether it is enabled, checked or on the screen | anything that needs a real device or platform plugin: camera, push notifications, platform views, the real keyboard, gestures other than a tap |
| use cases, repositories, view models and Dart libraries, called by name | `integration_test` on a device or emulator (a second adapter block could run it; this one does not) |
| the clock, stubbed dependencies, feature flags, events and jobs through seams of your own | swipes, scrolling and going back: the `ui` instruction `{actor} {action} {target}` has the actions clicks, fills, selects, uploads, types and toggles, and no more |

A widget test runs on the Dart VM with Flutter's test binding, so what it proves is what the widgets do, not how the app looks
or behaves on a phone. `uploads` is an expected failure by design (a widget test has no file picker): give the app a seam
and map it in `System`. A scenario has one screen, so every actor shares it.

## What you get

The test code is a Dart package of its own in `tests/`, so it never changes your application's `pubspec.yaml`. It needs the
Flutter SDK (3.35 or newer; tested with 3.47.8 and Dart 3.13.7).

| Path | What it is | Who edits it |
|---|---|---|
| `tests/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `tests/sample/` | the code the sample feature tests (delete it with the sample) | nobody |
| `tests/steps/core_steps.dart` | every core instruction of the declared profiles bound to the drivers | nobody: add project steps in `project_steps.dart` |
| `tests/steps/definition.dart` | how a step is written and matched | nobody |
| `tests/drivers/system.dart` | the seams into the system under test: seed, sign in, flags, events, jobs, records, application state | step-engineer, from `system.md` |
| `tests/drivers/operations.dart` | logical name → page, component, library function, error | step-engineer, from `system.md` |
| `tests/drivers/*.dart` (the rest) | the world of a scenario, the clock, the stubs, the screen and library drivers, comparison helpers | nobody |
| `tests/bdd_test.dart` | the one test that reads the features with the official Gherkin parser and runs each scenario | nobody |
| `tests/run_flutter.py` | runs `flutter test` and writes the JUnit report | nobody |
| `tests/pubspec.yaml`, `tests/pubspec.lock`, `tests/analysis_options.yaml` | the pinned test tooling and the analysis rules | the person |

## Setting up

```sh
cd tests && flutter pub get --enforce-lockfile      # fetches the pinned packages; pubspec.lock holds their hashes
```

To test your own application, add it to `tests/pubspec.yaml` as a path dependency (`my_app: {path: ../}`) and import it from
`operations.dart` and `system.dart`. Agents may not install packages; the person does, and chooses when to change the
pinned versions. The run uses `--no-pub`, so a changed `pubspec.yaml` that was not followed by `pub get` is an error and not a
silent update.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented throws `ExpectedMissing` (the message contains `BDD_EXPECTED_MISSING`): that is an
  *expected* failure. Leave the default in `system.dart` until the system has the seam. A component that is not on the
  screen yet is `ExpectedMissing` too, so a screen that does not exist is a valid red.
- An assertion that does not hold (`TestFailure`, `Expected: ... Actual: ...`) is expected.
- A logical name with no entry in `operations.dart` is `NotMapped`: that is a defect of the *test*. Fix the map, do not touch
  the feature.
- A step nobody wrote (`Undefined step`), a step two definitions match (`Ambiguous step`), an unstubbed call
  (`UnstubbedCall`) and a `NoSuchMethodError` are defects. Anything the patterns in `adapter.toml` do not recognise is
  `unknown` and blocks the gate.
- A Dart compile error, a missing package or a feature that does not parse stops `flutter test` before any test starts:
  `bdd run` shows the output and the scenarios are `not-run`. Code that does not exist yet is a compile error in a `lib`
  entry of `operations.dart`, which is a test defect: register it as `(_) => throw ExpectedMissing('...')` until it exists.

## What is bound

The bind lock covers `tests/steps/`, `tests/drivers/` and the plumbing files: `tests/bdd_test.dart`, `tests/run_flutter.py`,
`tests/pubspec.yaml`, `tests/pubspec.lock` and `tests/analysis_options.yaml`. A change to any of them makes a recorded run
stale.

The run is `python -I tests/run_flutter.py --tag FEAT-n --out REPORT`, started without a shell. The script runs
`flutter test --no-pub --reporter json bdd_test.dart` in `tests/`. The tag, the shuffle seed and the scenario to run travel in
`BDD_TAG`, `BDD_SEED` and `BDD_SCENARIO`, so a scenario title in any script is never squeezed through a command line. `DART_*`
and the `FLUTTER_TEST*` and `FLUTTER_ENGINE` variables are not passed on.

## Writing steps and drivers

- Features contain no widget keys, class names or import paths; everything concrete lives in `operations.dart` and `system.dart`.
- A step is a regular expression for its whole text plus a function of the world, the words it matched and the data under it
  (`argument?.table`, `argument?.docString`, or `payload(argument)`). Exactly one definition may match a step: two matching is
  an `Ambiguous step` defect, so a project phrase must not be matched by a core expression.
- A `then` step must assert (`bdd scan` reports S2 otherwise): call a driver's `assert…` function or `expect`.
- No `Future.delayed` or `sleep`: the screen driver pumps the frames it needs (`pumpAndSettle`) (`bdd scan` reports E3).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4).
- Components are found by `Finder`s in `targets`: prefer a `Key` the app puts on the widget (`find.byKey`), then a type with text
  (`find.widgetWithText`). A finder that matches several widgets uses the first.
- Give the application a clock seam that reads `world.clock.now()` (or hand it the time in `System.setTime`); the process clock is
  not frozen.
- The network is blocked by Flutter's test binding (an HTTP request answers 400), so a dependency must be stubbed or faked.

## Quality checks

Opt-in; add the tables you want to `.bdd/config.toml` (greenlight chooses none of them). Run them from the package you test,
and keep deprecation an error so that the code stays on current APIs (`tests/analysis_options.yaml` does for the tests):

```toml
[adapters.quality.analyze]
command = 'flutter analyze tests'

[adapters.quality.format]
command = 'dart format --output=none --set-exit-if-changed tests'
```

## Known pitfalls

- A scenario outline repeats its name once per example row: give each row a distinct title with `<param>` placeholders in the
  scenario name so each maps to its own example id.
- Two scenarios whose names are a substring of each other (`Add` and `Add twice`) after dropping punctuation: name them apart
  (see the generic-junit contract).
- A widget that animates forever (a progress indicator) makes `pumpAndSettle` time out: give the screen a state without it in
  the page builder, or find the component and pump a fixed frame in a step of your own.
- The first run downloads Flutter's test tooling and compiles the tests, which can take minutes; later runs are fast.
