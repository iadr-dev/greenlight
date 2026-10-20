# JUnit report fixtures

One folder per runner, four states of the same two-scenario feature (`Two numbers are added`, `A negative number is
refused`): `red.xml` (the system part is missing: `BDD_EXPECTED_MISSING`), `assert.xml` (a plain assertion fails),
`defect.xml` (no step is defined) and `green.xml`. `tests/test_junit_fixtures.py` classifies every one of them with the
`generic-junit` defaults.

| Runner | Where the files came from |
|---|---|
| `cucumber-js` | **A real run**: `@cucumber/cucumber` 11.2.0 on Node 26, `--format junit:FILE`, 2026-10-20 (the temporary project path and the host name were replaced by placeholders). |
| `behave` | **A real run**: the current `behave` release from PyPI on Python 3.14, `--junit --junit-directory DIR`, 2026-10-20. |
| `godog` | **Written from the documented report format** (the `junit` formatter of godog). Not produced by a run: check the shape against your godog version. |
| `cucumber-jvm` | **Written from the documented report format** (the `junit` plugin of Cucumber-JVM, strict mode). Not produced by a run. |
| `reqnroll` | **Written from the documented report format** of the JUnit logger for `dotnet test` (JunitXml.TestLogger) with xUnit. Not produced by a run. |

What the real runs showed, which the hand-written files do not need to repeat: cucumber-js writes an **empty**
`<failure/>` for an undefined step and says `undefined` only in `system-out`, and behave writes `<error type="NoneType"
message="None">` with `undefined` in the body. `bdd classify` reads `system-out` when a failure has no text of its own,
and the `generic-junit` defect patterns know both spellings.
