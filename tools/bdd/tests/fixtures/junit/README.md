# JUnit report fixtures

One folder per runner, four states of the same two-scenario feature (`Two numbers are added`, `A negative number is
refused`): `red.xml` (the system part is missing: `BDD_EXPECTED_MISSING`), `assert.xml` (a plain assertion fails),
`defect.xml` (no step is defined) and `green.xml`. `tests/test_junit_fixtures.py` classifies every one of them with the
`generic-junit` defaults.

| Runner | Where the files came from |
|---|---|
| `cucumber-js` | **A real run**: `@cucumber/cucumber` 11.2.0 on Node 26, `--format junit:FILE`, 2026-10-20 (the temporary project path and the host name were replaced by placeholders). |
| `behave` | **A real run**: the current `behave` release from PyPI on Python 3.14, `--junit --junit-directory DIR`, 2026-10-20. |
| `godog` | **A real run**: godog v0.16.0 (`junit` formatter) with Go 1.27.3 on Windows, 2026-10-21; a two-scenario module with steps that fail on purpose, one run per state. The test process exit status was ignored, as `bdd run` does with the report. |
| `cucumber-jvm` | **A real run**: Cucumber-JVM 8.0.4 with `cucumber-junit-platform-engine` on Maven 3.9.16 and JDK 25, `-Dcucumber.plugin=junit:FILE`, 2026-10-21. |
| `reqnroll` | **Written from the documented report format** of the JUnit logger for `dotnet test` (JunitXml.TestLogger) with xUnit. Not produced by a run. |

What the real runs showed, which the hand-written file does not need to repeat: cucumber-js and Cucumber-JVM write an **empty**
`<failure/>` for an undefined step and say `undefined` only in `system-out`, godog writes `<error type="undefined">` (and lists every undefined step of a scenario as its own element, and a `status="passed"` scenario can still carry a failure from a later step), and behave writes `<error type="NoneType"
message="None">` with `undefined` in the body. `bdd classify` reads `system-out` when a failure has no text of its own,
and the `generic-junit` defect patterns know both spellings.
