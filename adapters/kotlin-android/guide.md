# Adapter guide: kotlin-android

For Android apps and the Kotlin libraries inside them, tested with Cucumber-JVM on the JUnit Platform as **local JVM unit
tests**: no emulator, no device, the same speed and the same JUnit report as any Gradle `test` task. The same feature files
and steps can also run **on a device** through Cucumber-Android (opt-in, see *Running the scenarios on a device*). It is the first-class
form of the `generic-junit` contract for this stack. Tested with Gradle 9.8, Kotlin 2.4 and Cucumber-JVM 8.0 on
JDK 21 (CI) and 25 as a Kotlin/JVM module, and with the Android Gradle Plugin 9 in CI (see *What was run for real* below).
`bdd adapter apply kotlin-android` copies `templates/` into the module and registers the adapter in `.bdd/config.toml`.
Nothing is overwritten.

## What it covers, and what needs a device

| Covered (local JVM, and on a device when opted in) | Not covered by this adapter |
|---|---|
| use cases, repositories, view models and other logic; Kotlin libraries | screens: no step drives a Compose or View UI (Espresso), so the `ui` profile is not declared |
| Room or SQLite access, with the query counter attached | on the JVM only: code that calls `android.*` classes, because the unit-test `android.jar` throws "Method ... not mocked"; on a device those calls are real |

For code that calls the Android framework, either put the framework behind a small interface in your code and fake it in
the seams (recommended: the logic is then testable and the scenario reads the same), or run the scenarios on a device as
well (see *Running the scenarios on a device*), where the framework is the real one. Robolectric is **not** supported here: it needs its
own JUnit 4 runner, which Cucumber's JUnit Platform engine does not use. Setting `isReturnDefaultValues = true` makes
framework calls return zeros and nulls; that can turn a real defect into a pass, so do not use it to make a scenario
green. Features for a web UI use `ts-playwright-bdd`.

## What you get

| Path | What it is | Who edits it |
|---|---|---|
| `src/test/resources/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `src/test/kotlin/greenlight/steps/CoreSteps.kt` | every core instruction of the `base`, `lib` and `data` profiles bound to the drivers | nobody: add project steps in their own class |
| `src/test/kotlin/greenlight/steps/{Hooks,ParameterTypes}.kt` | per-scenario set-up; one step method takes a table or a doc string | nobody |
| `src/test/kotlin/greenlight/drivers/ProjectSeams.kt` | the seams into the code under test: seed, sign in, read records, jobs, events | step-engineer, from `system.md` |
| `src/test/kotlin/greenlight/drivers/Operations.kt` | logical name → the function to call, logical error → exception or text | step-engineer, from `system.md` |
| `src/test/kotlin/greenlight/drivers/` (the rest) | clock, stubs, comparison, the library driver, the query counter | nobody |
| `greenlight.gradle.kts`, `RunCucumberTest.kt`, `junit-platform.properties` | which features run and how Gradle hands the settings to the tests | nobody (bound) |
| `SampleDomain.kt`, `SampleSeams.kt` | code under test and in-memory seams for the sample feature | delete with the sample |

## Set up

1. In the module's `build.gradle.kts`, add the test dependencies and apply the bound script:

   ```kotlin
   apply(from = "greenlight.gradle.kts")

   dependencies {
       testImplementation(platform("io.cucumber:cucumber-bom:8.0.4"))
       testImplementation("io.cucumber:cucumber-java")
       testImplementation("io.cucumber:cucumber-picocontainer")
       testImplementation("io.cucumber:cucumber-junit-platform-engine")
       testImplementation("org.junit.platform:junit-platform-suite")
       testRuntimeOnly("org.junit.platform:junit-platform-launcher")
   }
   ```

   Install nothing else; the agents are not allowed to change the build.
2. Run `bdd init --smoke` (or `./gradlew testDebugUnitTest --tests greenlight.RunCucumberTest -Pcucumber.filter.tags=@FEAT-000`):
   the sample is green. In a plain Kotlin/JVM module the task is `test`, not `testDebugUnitTest`: change `by_tag` in
   `.bdd/config.toml`.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented raises `ExpectedMissing` (the message contains `BDD_EXPECTED_MISSING`): that is an
  *expected* failure. Leave the default in `ProjectSeams` until the code has the seam.
- A logical name with no entry in `Operations.kt` raises `NotMapped`: that is a defect of the *test*. Fix the map, do not
  touch the feature.
- An undefined or ambiguous step, a Kotlin compile error, a missing class and a "not mocked" framework call are defects
  too. Anything the patterns in `adapter.toml` do not recognise is `unknown` and blocks the gate.
- Operations are lambdas, so a function that does not exist yet is a **compile error** in `Operations.kt`, which is a
  test defect. Register the operation as `{ throw ExpectedMissing("...") }` until the function exists.

## Filling in the seams

Override the methods of `Seams` in `ProjectSeams`, one at a time, from the system map. Use the most realistic seam: the use
case or view model first, then the repository, then the raw database.

- **Clock.** `world.clock` is a `java.time.Clock`. Give the code under test a `Clock` (core library desugaring provides
  `java.time` on every API level) and construct it with `world.clock` in the seams; code that calls `Instant.now()` does
  not follow `Given the current time is ...`, and `system.md` should say so.
- **Dependencies.** Route outbound calls through a gateway interface whose test implementation calls
  `world.stubs.call(dependency, operation, request)`. A call the scenario did not stub fails the scenario.
- **Queries.** Attach `QueryCounter.shared` to the test database (the Room snippet is in `QueryCounter.kt`); then `... ran
  at most N queries` works with no seam of your own. Seed three or more records so a query per record shows.
- **Do not edit the core drivers** (`World`, `LibDriver`, `Compare`, `Stubs`, `QueryCounter`, `Json`, ...) or `CoreSteps`.
  Project differences go in `ProjectSeams`, `Operations` and your own step classes.

## Writing steps and drivers

- Features contain no class names, function names or SQL; everything concrete lives in `Operations.kt` and
  `ProjectSeams.kt`.
- A `Then` step must assert (`bdd scan` reports S2 otherwise); put the comparison in `Compare`.
- No `Thread.sleep` or `delay(...)`: wait for the condition (`bdd scan` reports E3).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4 for a `mockk<...>()` or
  `mock(...::class)` of anything else).
- A step method may take a `Payload` (a table or a doc string, whichever the step has) or a `DataTable`. Never write one
  method per kind: two methods with the same pattern are a duplicate-definition error.

## Running

```sh
./gradlew testDebugUnitTest --tests greenlight.RunCucumberTest -Pcucumber.filter.tags=@FEAT-007         # one feature
./gradlew testDebugUnitTest --tests greenlight.RunCucumberTest -Pcucumber.filter.name='^Order of 999$'   # one scenario
./gradlew testDebugUnitTest --tests greenlight.RunCucumberTest -Pcucumber.execution.order=random -Pcucumber.execution.order.random.seed=42   # random, repeatable
```

`bdd run FEAT-007` does all of this and records the result (Cucumber's JUnit report, one file); always use it for gates.
On Windows `gradlew` is a `.bat` file, so `bdd run` refuses an argument with characters that `cmd.exe` would read as syntax
(`" & | < > ^ % !`), for example a scenario name containing `&` in `--isolated` mode.

## Running the scenarios on a device

The same feature files, steps and drivers run as instrumented tests through
[Cucumber-Android](https://github.com/cucumber/cucumber-android) on a phone or an emulator: the Android framework is the
real one, and the result is a second set of cases in the same recorded run. It is opt-in and needs a device every time
`bdd run` runs, so turn it on only when the scenarios need the framework. Tested on 2026-10-21 with a Samsung SM-G996N on
Android 15 (API 35), Cucumber-Android 7.19.0 (on Cucumber-JVM 7.34.9), the Android Gradle Plugin 9.4.1 with Kotlin 2.4.21,
`compileSdk` 37 and Gradle 9.8.2.

1. In the module's `build.gradle.kts` (the project's file, so you edit it):

   ```kotlin
   plugins {
       id("com.android.library") version "9.4.1"                       // or com.android.application
       id("org.jetbrains.kotlin.android") version "2.4.21" apply false   // Cucumber-Android is built with Kotlin 2.4
   }

   apply(from = "greenlight.gradle.kts")
   apply(from = "greenlight-device.gradle.kts")

   android {
       compileSdk = 37                     // Cucumber-Android 7.19 compiles against 37
       defaultConfig {
           minSdk = 26                     // and runs on API 26 and newer
           testInstrumentationRunner = "io.cucumber.android.runner.CucumberAndroidJUnitRunner"
           testInstrumentationRunnerArguments["optionsAnnotationPackage"] = "greenlight"
       }
       sourceSets {
           getByName("androidTest") {
               kotlin.srcDir("src/test/kotlin")      // the same steps and drivers
               kotlin.srcDir("src/device/kotlin")    // RunCucumberOnDevice, which starts them
               assets.srcDir("src/test/resources")   // the same feature files
           }
       }
   }

   dependencies {
       androidTestImplementation("io.cucumber:cucumber-android:7.19.0")
       androidTestImplementation("io.cucumber:cucumber-picocontainer:7.34.9")
   }
   ```

   Install the SDK platform 37 if it is missing (`android sdk install platforms/android-37.0`).
2. Add this second adapter block to `.bdd/config.toml`, after the `kotlin-android` one. It names no feature, step or driver
   folder of its own: it runs the same ones.

   <!-- device adapter block: tools/bdd/tests/test_adapter_jvm.py reads the toml block below -->
   ```toml
   [[adapters]]
   name = "kotlin-android-device"

   [adapters.run]
   by_tag = "./gradlew -q connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.tags=@{tag}"
   report = "-Pgreenlight.report={out}"
   isolated = "-Pandroid.testInstrumentationRunnerArguments.name='\\\\A{scenario:device}\\\\z'"
   timeout = 1800

   [adapters.classify]
   test_defect = ["NotMapped", "UndefinedStepException|Undefined step|DuplicateStepDefinitionException|AmbiguousStepDefinitionsException", "ClassNotFoundException|NoClassDefFoundError|NoSuchMethodError|ExceptionInInitializerError", "CucumberException", "e: file:.*\\.kt|Unresolved reference|Compilation error|Execution failed for task .*compile", "(?i)no tests (were )?(found|executed)"]
   expected_fail = ["BDD_EXPECTED_MISSING", "AssertionError|AssertionFailedError"]
   ```
3. Connect one device with USB debugging on (`adb devices` shows it as `device`), or start an emulator. With several,
   choose one with `ANDROID_SERIAL`: the bound script refuses to pick a report when there is more than one.

`bdd run FEAT-007` then runs both adapters and records the JVM cases and the device cases side by side; a scenario counts
with its worse result. `bdd run FEAT-007 --adapter kotlin-android` runs the JVM side alone, `--adapter kotlin-android-device`
the device side alone, and `--isolated` runs each scenario in its own instrumentation run on the device too.

How it works, and what to know:

- `greenlight-device.gradle.kts` (bound) removes the results of an earlier instrumented run before the tests start and
  copies the new report to the file `bdd run` reads. Cucumber's own JUnit plugin does not work on Android, so the report is
  the one the Android Gradle Plugin writes; it names each case after its scenario. The script also leaves the JVM suite,
  `RunCucumberTest.kt`, out of the instrumented build. `src/device/kotlin/greenlight/RunCucumberOnDevice.kt` (bound) holds
  the `@CucumberOptions` that Cucumber-Android looks for; that folder is not a source set until step 1 adds it, so a
  project that does not opt in never compiles it.
- `--shuffle` is refused for the device adapter: Cucumber-Android has no setting for the order. Shuffle the JVM side with
  `--adapter kotlin-android`.
- Instrumentation arguments reach the device through its shell unquoted, so the single-scenario filter is written for that
  shell (`{scenario:device}`: every character other than a letter or digit escaped twice, and characters outside ASCII as
  `\x{HEX}`). Titles with accents and in Chinese ran, also one at a time.
- A scenario title must not contain parentheses or a comma on the device: the Android test report splits a case name at
  the first parenthesis (the case would not map to its scenario, so the gates block), and Cucumber-Android reserves the
  comma for sharding.
- The Android Gradle Plugin installs the test app, runs it and uninstalls it again; nothing else on the device changes.
- An emulator works the same way. Google's `android` command-line tool sets one up without Android Studio; these commands
  were run on Windows with `android` 1.0.16 and the emulator 37.2:

  ```sh
  android sdk install emulator system-images/android-36/google_apis/x86_64
  android emulator create medium_phone              # also fetches the system image its profile needs
  android emulator start medium_phone               # returns when the emulator has booted (about 5 minutes the first time)
  adb devices                                       # the emulator shows as "device"
  ```

  `android emulator start` is the emulator's parent: wrapping it in `timeout` or closing its shell stops the emulator.

## Quality checks (optional)

Name your own tools in `[adapters.quality.NAME]` tables; none is forced:

```toml
[adapters.quality.lint]                  # detekt or Android lint, from your build
command = './gradlew -q detekt lintDebug'

[adapters.quality.format]                # needs the ktlint or spotless Gradle plugin
command = './gradlew -q ktlintCheck'

[adapters.quality.warnings]              # compile warnings, deprecations included, are errors: set allWarningsAsErrors in the build
command = './gradlew -q compileDebugKotlin'
```

`.bdd/standards.md` holds the Kotlin, Gradle and `compileSdk` versions, the style and the deprecation policy these checks
enforce; the `kotlin` practice card lists the usual commands.

## What this adapter does not do

- It does not drive screens: no step taps, types or reads a Compose or View UI, so the `ui` profile is not declared. On a
  device the scenarios exercise the same logic with the real framework underneath.
- The module's `build.gradle.kts` is the project's, so it is not bound by default. A build setting that skips the tests
  makes the scenarios `not-run`, which blocks the gates rather than faking a pass. Add it to `support` in
  `.bdd/config.toml` once the dependencies are final, and review changes to it.
- Production code runs inside the test JVM and could in principle detect the run; the auditor reads the diff and the
  optional mutation check (`bdd mutate`, with PIT and its Gradle plugin as the project's wrapper command) adds a second line.

## Known pitfalls

- A scenario title in another script or with accents works, also when one scenario runs alone: the name filter is sent to
  Gradle as plain ASCII (every character outside ASCII as `\x{HEX}`), because Windows converts a command line that reaches
  a `.bat` launcher to the active code page and a letter that page lacks arrives as `?`.
- `./gradlew -q` hides Gradle's own progress; a failing scenario still shows its message. Drop `-q` when debugging.
- The first Gradle run downloads the Android SDK components and dependencies; cache `~/.gradle` in CI.
- State that lives in objects the code under test keeps (singletons, in-memory stores) must be reset in
  `ProjectSeams.reset()`.
