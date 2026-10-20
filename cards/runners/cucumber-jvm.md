---
id: cucumber-jvm
kind: runner
apply_when: "a Java or Kotlin project whose scenarios run with Cucumber-JVM under JUnit Platform, Maven or Gradle (the generic-junit adapter)"
---
## Run

Cucumber-JVM selects scenarios with the `cucumber.filter.tags` property and writes JUnit with its `junit` plugin. With Maven:

```toml
[adapters.run]
by_tag = '{python} -I tests/run_junit.py --reports "target/cucumber-report.xml" --command "mvn -B -q test -Dcucumber.filter.tags=@{tag} -Dcucumber.plugin=junit:target/cucumber-report.xml"'
report = '--out {out}'
```

With Gradle, pass the properties through the test task (`systemProperty` in `build.gradle`) or an environment-free
`cucumber.properties` file in the test resources. Add `pom.xml` (or `build.gradle` and its lockfile) and
`src/test/resources/cucumber.properties` to `support`. See also the junit-maven and junit-gradle cards.

## Report

`<testsuite name="io.cucumber.core.plugin.JUnitFormatter">` with one `<testcase classname="<feature>" name="<scenario>">` per
scenario. The scenario name is the test name. This card and the fixtures in `tools/bdd/tests/fixtures/junit/cucumber-jvm` were
written from the documented format and **not produced by a run**: run once with a failing and an undefined step and compare.

## What red looks like

- A step that throws `new UnsupportedOperationException("BDD_EXPECTED_MISSING: add")` is a `<failure type="java.lang.UnsupportedOperationException">`
  with the message: an expected failure. A failed JUnit assertion is `org.opentest4j.AssertionFailedError: expected: <5> but was: <0>`: also expected.
- In strict mode (the default since Cucumber 7) an undefined step fails with `The step "..." is undefined`; the default patterns
  call it a test defect. If the plugin writes `<skipped message="...undefined">` instead, the run is not strict: turn strict on.
- A compile error makes Maven fail before any test runs: no report, scenarios `not-run`.

## Known pitfalls

- A tag expression with `and`/`or` needs quoting in a shell; the run line is not a shell, so write it as one word.
- Surefire forks the test JVM: `-D` properties on the Maven command line reach it as user properties; `systemPropertyVariables` in the pom are bound with the pom.
- The report path is relative to the module directory in a multi-module build.
