---
id: dotnet-test
kind: runner
apply_when: "a .NET project tested with xUnit, NUnit or MSTest through dotnet test (the generic-junit adapter), including Reqnroll or SpecFlow"
---
## Run

For Reqnroll features use the `dotnet-reqnroll` adapter instead of this recipe: it ships the steps, the drivers, the pinned
packages, a wrapper that builds the test filter and the run command. The rest of this card is for other .NET test projects.

Give the tests of a feature a category (xUnit: `[Trait("Category", "FEAT_007")]`; NUnit: `[Category("FEAT_007")]`;
MSTest: `[TestCategory("FEAT_007")]`) and add the JUnit logger to the test project (`JunitXml.TestLogger`, pinned):

```toml
[adapters.run]
by_tag = 'dotnet test --no-restore --filter "Category={marker}"'
report = '--logger "junit;LogFilePath={out}"'
```

The logger takes the path as an option, so no wrapper is needed. Add the test project file (`*.csproj`) and
`Directory.Build.props` to `support`. Restore packages yourself before the run (`--no-restore` keeps a recorded run from
fetching anything). Reqnroll and SpecFlow generate test classes from the feature files and carry the scenario tags as
categories, so `FEAT-007` becomes a category after the generator's rewriting of the name; check the generated name once.

## Report

One XML file. The case `name` is the method name (or the display name for xUnit with `DisplayName`), so name methods after
their scenarios.

## What red looks like

Assertion libraries throw `Xunit.Sdk.EqualException`, `NUnit.Framework.AssertionException` and the like; the type is in the
`<failure type=...>` and the message is `Assert.Equal() Failure`. The default patterns do not know these names: add
`Xunit\.Sdk|AssertionException|Assert\.` to `expected_fail`, or throw an exception whose message contains
`BDD_EXPECTED_MISSING`. A build error stops before any test runs and no report is
written; `bdd run` prints the build output, where `error CS...` marks a test defect.

## Known pitfalls

- `--filter` expressions are case-sensitive, and an unknown trait selects nothing: zero tests run and the exit code is 0 unless
  the project sets `--fail-on-no-tests`/`TreatNoTestsAsError`; then the scenarios are `not-run`.
- Running on several target frameworks writes the report once per framework; the logger's last write wins. Pass `-f net8.0` (or
  your framework) in the command.
- Test discovery by name (`FullyQualifiedName~`) matches substrings and can pick up other features' tests.
- Parallel test runs can reorder cases; the report is unaffected.
