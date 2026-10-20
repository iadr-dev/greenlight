---
id: junit-maven
kind: runner
apply_when: "a Java or Kotlin project built with Maven and tested with JUnit 5 through Surefire (the generic-junit adapter)"
---
## Run

Tag the tests of a feature with the marker and select them with Surefire's `groups` property:

```java
@Tag("FEAT_007")
class OrderDiscountsTest { ... }
```

```toml
[adapters.run]
by_tag = '{python} -I tests/run_junit.py --reports "target/surefire-reports/TEST-*.xml" --command "mvn -q test -Dgroups={marker}"'
report = '--out {out}'
```

Windows: `mvn.cmd` (or `mvnw.cmd`). Add `tests/run_junit.py` and `pom.xml` to `support`.

## Report

Surefire writes `target/surefire-reports/TEST-<class>.xml` per class; the wrapper merges them. Case names are the method
names (or the display name when a `@DisplayName` is set and `surefire` is configured to report it): name the method after the
scenario, and open one file once to see what your version writes.

## What red looks like

Failed assertions and thrown exceptions are `<failure>` or `<error>` elements with the exception type and message. A unit that
does not compile makes Maven stop with `COMPILATION ERROR` before tests run: no report, and `bdd run` prints the output.

## Known pitfalls

- `-Dgroups` filters JUnit 5 tags only with a recent Surefire (2.22 or newer); with JUnit 4 use categories instead.
- A tag that matches nothing: Surefire runs no tests; the scenarios are `not-run`.
- `-q` hides the test summary; that is fine, the XML is what counts.
- Integration tests run by Failsafe write to `target/failsafe-reports`; list that folder in `--reports` too if you use it.
