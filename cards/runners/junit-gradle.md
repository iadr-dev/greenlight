---
id: junit-gradle
kind: runner
apply_when: "a Java or Kotlin project built with Gradle and tested with JUnit 5 (the generic-junit adapter)"
---
## Run

Mark the tests of a feature with a JUnit tag whose name is the marker, and let the build script take the tag as a property:

```kotlin
// build.gradle.kts
tasks.test {
    useJUnitPlatform {
        providers.gradleProperty("includeTag").orNull?.let { includeTags(it) }
    }
}
```

```java
@Tag("FEAT_007")
class OrderDiscountsTest {
    @Test void twoNumbersAreAdded() { ... }
}
```

In `.bdd/config.toml` (Windows: `gradlew.bat`, or `gradle` if installed):

```toml
[adapters.run]
by_tag = '{python} -I tests/run_junit.py --reports "build/test-results/test/*.xml" --command "./gradlew cleanTest test -PincludeTag={marker}"'
report = '--out {out}'
```

Add `tests/run_junit.py` and the build files that decide what runs (`build.gradle.kts`, `settings.gradle.kts`) to `support`.
Leave `shuffle` out unless your build reads a property such as `-Pseed=N` and orders tests with it; then
`shuffle = '--add=-Pseed={seed}'` passes it on.

## Report

Gradle writes one XML file per test class to `build/test-results/test/`; the wrapper merges them. The `name` of a case is the
test method (with `()`), so name methods after their scenario (`twoNumbersAreAdded` is "Two numbers are added"). Look at one
file once to confirm what your version writes.

## What red looks like

An unbuilt seam: the test throws or calls `fail("BDD_EXPECTED_MISSING: order service")`. The case is a `<failure>` with type
`org.opentest4j.AssertionFailedError` (or your own exception) and the message in `message`. A compile error stops Gradle before
any test runs: no report is written, and `bdd run` shows Gradle's output ("error: cannot find symbol" is a test defect).

## Known pitfalls

- `cleanTest` is needed: without it Gradle reports the test task as up to date and runs nothing, so no new report appears.
- A tag that matches no test makes Gradle run zero tests and exit 0: every scenario is `not-run`.
- The Gradle daemon and build cache can serve a stale result; `cleanTest` or `--rerun` forces a real run.
- Parameterised tests produce several cases per scenario; the worst result of them counts.
- On Windows `./gradlew` does not run; use `gradlew.bat` (the command is not run through a shell, so `./` has no meaning).
