---
id: reqnroll
kind: runner
apply_when: "a .NET project whose scenarios run with Reqnroll (the SpecFlow successor) on xUnit, NUnit or MSTest (the generic-junit adapter)"
---
## Run

Reqnroll generates one test per scenario and turns feature tags into test categories, so `dotnet test` filters by category and a
logger writes the JUnit file. Use a pinned JUnit logger package (`JunitXml.TestLogger`, referenced in the test project):

```toml
[adapters.run]
by_tag = 'dotnet test --no-restore --filter "Category={tag}"'
report = '--logger "junit;LogFilePath={out}"'
```

Add the test project file (`*.csproj`), `packages.lock.json`, `reqnroll.json` and `Hooks.cs` to `support`. With several target
frameworks the logger writes a file per framework: use `tests/run_junit.py --reports "TestResults/*.xml"` instead. See also the dotnet-test card.

## Report

One `<testcase>` per scenario; `name` is the generated test method (`TwoNumbersAreAdded` for the scenario `Two numbers are added`),
which contains the scenario name once punctuation is dropped, so the mapping works. This card and the fixtures in
`tools/bdd/tests/fixtures/junit/reqnroll` were written from the documented format and **not produced by a run**.

## What red looks like

- A step that throws `new NotImplementedException("BDD_EXPECTED_MISSING: add")` is a `<failure type="System.NotImplementedException">`:
  an expected failure. xUnit assertions (`Xunit.Sdk.EqualException`, `Assert.Equal() Failure`) and NUnit's `AssertionException` are expected too.
- A step with no definition is reported as pending ("No matching step definition found for one or more steps"): the default patterns call it
  a test defect. Check what your Reqnroll version does by default: in `reqnroll.json` set `"runtime": { "missingOrPendingStepsOutcome": "Error" }`,
  because an outcome of `Ignore` or `Inconclusive` appears as skipped and only blocks the red as "did not run".
- A compile error stops `dotnet test` before any report (`error CS0103`): scenarios `not-run`, and the output matches the defect pattern.

## Known pitfalls

- The category is the tag without `@`: `Category=FEAT-007`. A hyphen is fine; spaces are not.
- Scenario Outlines generate one test per example row with the row values in the name; the scenario name is still contained in it.
- `--no-restore` needs a restore step before the first run; do it in the same bound command file or by hand, not in the run line.
