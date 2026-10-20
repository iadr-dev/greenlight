# Adapter guide: dotnet-reqnroll

For .NET services, libraries and command-line tools tested with [Reqnroll](https://reqnroll.net) (the SpecFlow successor)
and xUnit. The profiles are `base`, `api`, `cli`, `lib` and `data`. It is the .NET-specific form of the `generic-junit`
contract: the JUnit report is written by a test logger, every core instruction is bound, and the drivers give a missing
seam the right failure. `bdd adapter apply dotnet-reqnroll` copies `templates/` into the project and registers the
adapter in `.bdd/config.toml`. Nothing is overwritten.

## What you get

The test code is its own project in `tests/`, so it never changes your solution's projects. It needs the .NET 10 SDK (or
the version `net10.0` is changed to in `tests/GreenlightTests.csproj`).

| Path | What it is | Who edits it |
|---|---|---|
| `tests/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `tests/sample/` | the code the sample feature tests (delete it with the sample) | nobody |
| `tests/steps/CoreSteps.cs` | every core instruction of the declared profiles bound to the drivers | nobody: add project steps in `ProjectSteps.cs` |
| `tests/drivers/SystemUnderTest.cs`, `Wiring.cs` | the seams into the system under test: HTTP client, seed, sign in, flags, events, jobs, records, query counter | step-engineer, from `system.md` |
| `tests/drivers/Operations.cs` | logical name → API route, command line, library function, file, error | step-engineer, from `system.md` |
| `tests/drivers/*.cs` (the rest) | the world of a scenario, the clock, the stubs, the network block, comparison helpers, the seeded orderer | nobody |
| `tests/GreenlightTests.csproj`, `tests/packages.lock.json`, `tests/nuget.config`, `tests/.editorconfig`, `tests/run_dotnet.py` | the pinned test tooling and how scenarios are selected and reported | the person |

## Setting up

```sh
dotnet restore tests --locked-mode      # restores exactly what packages.lock.json says, with hashes
```

To test your own projects, add a project reference to `tests/GreenlightTests.csproj` and a using to `Operations.cs` and
`Wiring.cs`:

```xml
<ProjectReference Include="..\src\YourApp\YourApp.csproj" />
```

For an ASP.NET application, `Microsoft.AspNetCore.Mvc.Testing` gives `WebApplicationFactory<Program>`, whose
`CreateClient()` is the `SystemUnderTest.Http()` seam (requests are served in memory, no port is opened). Adding a package
changes `packages.lock.json`; the person does that, with `dotnet restore tests --force-evaluate`, and reviews the diff.
Agents may not install packages.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented throws `ExpectedMissingException` (the message contains `BDD_EXPECTED_MISSING`): that is
  an *expected* failure. Leave the default in `SystemUnderTest.cs` until the system has the seam. `Http()` is one: until
  the application has something to call, an API operation is an expected failure.
- An API operation answered with 404, 405 or 501 fails the step with `status 404`: also expected. An assertion that does
  not hold (`AssertionError`) is expected too.
- A logical name with no entry in `Operations.cs` throws `NotMapped`: that is a defect of the *test*. Fix the map, do not
  touch the feature.
- A step nobody wrote (Reqnroll: `No matching step definition`), a step whose signature does not fit the step (`Parameter
  count mismatch`), two expressions that both match (`Ambiguous step definitions`), an unstubbed call (`UnstubbedCall`) and
  a connection to the internet (`OutboundNetworkBlocked`) are defects. Anything the patterns in `adapter.toml` do not
  recognise is `unknown` and blocks the gate.
- A compile error stops `dotnet test` before any report is written: `bdd run` shows the compiler output and the scenarios
  are `not-run`.

## What is bound

The bind lock covers `tests/steps/`, `tests/drivers/` and the plumbing files: the project file, the lock file,
`nuget.config`, `.editorconfig` and `run_dotnet.py`. A change to any of them makes a recorded run stale.

The run is `python -I tests/run_dotnet.py --tag FEAT-n --out REPORT`, started without a shell. The wrapper (standard
library only) runs `dotnet test tests/GreenlightTests.csproj -p:RestoreLockedMode=true` with the filter
`Category=FEAT-n` (Reqnroll turns every tag into an xUnit trait named `Category`) and the `junit` logger from
`JunitXml.TestLogger`. For `--isolated` the filter also names the scenario (`DisplayName=…`, with the filter language's
operators escaped, so a name is only ever a value). `--seed N` sets `GREENLIGHT_BDD_SEED`, which an orderer in
`SeededOrder.cs` turns into a repeatable shuffle. `DOTNET_STARTUP_HOOKS`, `DOTNET_ADDITIONAL_DEPS`, `DOTNET_SHARED_STORE`,
`DOTNET_ROLL_FORWARD`, `DOTNET_gc*`, `COMPlus_*`, `MSBUILD*`, `VSTEST_*` and `XUNIT_*` are not passed on, because they
change what .NET loads or how the test host behaves; `DOTNET_ROOT`, `PATH` and `NUGET_*` are.

## Writing steps and drivers

- Features contain no paths, binaries, selectors or SQL; everything concrete lives in `Operations.cs` and
  `SystemUnderTest.cs`.
- Reqnroll picks a binding by its expression **and** its signature, so a step that accepts a data table or a doc string has
  one method per shape (none, `DataTable`, `string`). Expressions must not overlap: a step that matches two of them is an
  ambiguous-binding failure. Copy the pattern in `CoreSteps.cs`.
- A `then` step must assert (`bdd scan` reports S2 otherwise): call a `…Assert…` method.
- No `Thread.Sleep` or `Task.Delay`: wait for the condition (`bdd scan` reports E3).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4).
- Project-specific steps go in `ProjectSteps.cs` (or classes next to it) and use the same drivers.
- Give the application a clock seam, for example `TimeProvider`: `world.Clock` is one. Nothing freezes the process clock.
- Count queries with `QueryCounter`: call `Record` from the data access (an EF Core `DbCommandInterceptor`, a wrapper
  around the connection, the repository) and return `Count` from `QueriesExecuted`.
- The network is not blocked globally (.NET has no switch for that). Give the application's `HttpClient` a
  `SocketsHttpHandler { ConnectCallback = BlockedNetwork.ConnectAsync }` in the test host, or stub the dependency.

## Quality checks

Opt-in; add the tables you want to `.bdd/config.toml` (greenlight chooses none of them). The test project already turns the
use of an obsolete API into a build error (`CS0612`, `CS0618`, `CS0672`); the same is worth doing for your own projects:

```toml
[adapters.quality.format]
command = 'dotnet format tests --verify-no-changes --no-restore'

[adapters.quality.build]                   # analyzers and nullable warnings are errors; deprecation is already one
command = 'dotnet build tests --no-restore -warnaserror'
```

Add `<AnalysisMode>All</AnalysisMode>` and `<EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>` to the projects you want
checked more strictly, and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` where the code base is clean enough for it.

## Known pitfalls

- A scenario name whose letters are not ASCII: Reqnroll builds the test method name from the title and the JUnit report
  uses it, so the name the report carries may not contain the scenario name. Keep scenario titles in ASCII, or check the
  report once (the generic-junit contract explains the mapping).
- Two scenarios whose names are a substring of each other after dropping punctuation: name them apart.
- A solution that targets another framework than `net10.0`: change `TargetFramework` in the test project to one the
  installed SDK can run, and restore again (the lock file is per framework).
- Reading the real clock, the real network or the real environment in the application: the scenario then depends on the
  machine. Inject the clock and the dependencies.
