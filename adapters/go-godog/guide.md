# Adapter guide: go-godog

For Go services, libraries and command-line tools tested with [godog](https://github.com/cucumber/godog) (the Cucumber
implementation for Go). The profiles are `base`, `api`, `cli`, `lib` and `data`. It is the Go-specific form of the
`generic-junit` contract: godog writes the JUnit report itself, every core instruction is bound, and the drivers give a
missing seam the right failure. `bdd adapter apply go-godog` copies `templates/` into the project and registers the
adapter in `.bdd/config.toml`. Nothing is overwritten.

## What you get

The test code is a separate Go module in `tests/`, so it never changes your application's `go.mod`. It needs Go 1.24 or
newer.

| Path | What it is | Who edits it |
|---|---|---|
| `tests/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `tests/sample/` | the code the sample feature tests (delete it with the sample) | nobody |
| `tests/steps/core_steps.go` | every core instruction of the declared profiles bound to the drivers | nobody: add project steps in their own file |
| `tests/drivers/system.go` | the seams into the system under test: HTTP handler, seed, sign in, flags, events, jobs, records, query counter | step-engineer, from `system.md` |
| `tests/drivers/operations.go` | logical name → API route, command line, library function, file, error | step-engineer, from `system.md` |
| `tests/drivers/*.go` (the rest) | the world of a scenario, the clock, the stubs, the network block, comparison helpers | nobody |
| `tests/bdd_test.go` | the one test that runs the features and writes the JUnit report | nobody |
| `tests/go.mod`, `tests/go.sum` | the pinned test tooling (godog and its dependencies) | the person |

## Setting up

```sh
cd tests && go mod download      # fetch the pinned modules; go.sum already holds their hashes
```

To test your own packages, add them to the test module the usual way and import them from `operations.go` and
`system.go`:

```sh
cd tests
go mod edit -require example.com/yourapp@v0.0.0 -replace example.com/yourapp=../
```

Agents may not install packages; the person does, and chooses when to change the pinned versions. The run uses
`-mod=readonly`, so a missing or changed requirement is an error and not a silent update.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented returns `ExpectedMissing` (the message contains `BDD_EXPECTED_MISSING`): that is an
  *expected* failure. Leave the default in `system.go` until the system has the seam. `System.Handler()` is one: until the
  application has an HTTP handler, calling an API operation is an expected failure.
- An API operation answered with 404, 405 or 501 fails the step with `status 404`: also expected. An assertion that does
  not hold (`AssertionError`) is expected too.
- A logical name with no entry in `operations.go` returns `NotMapped`: that is a defect of the *test*. Fix the map, do
  not touch the feature.
- A step nobody wrote (godog reports it as `undefined`), a step whose arguments do not fit its function, a panic, an
  unstubbed call (`UnstubbedCall`) and a connection to the internet (`OutboundNetworkBlocked`) are defects. Anything the
  patterns in `adapter.toml` do not recognise is `unknown` and blocks the gate.
- A compile error stops `go test` before any report is written: `bdd run` shows the compiler output and the scenarios are
  `not-run`.

## What is bound

The bind lock covers `tests/steps/`, `tests/drivers/` and the plumbing files: `tests/bdd_test.go`, `tests/go.mod` and
`tests/go.sum`. A change to any of them makes a recorded run stale.

The run is `go -C tests test -mod=readonly -count=1 -run ^TestFeatures$ . -args -bdd.tag=FEAT-n -bdd.out REPORT`, started
without a shell. `GOFLAGS`, `GOENV`, `GOWORK`, `GOEXPERIMENT`, `GODEBUG`, `GOOS`, `GOARCH` and `CGO_*` are not passed on,
because they change what Go builds or runs; `GOPATH`, `GOMODCACHE` and `GOPROXY` are. `-bdd.seed N` shuffles the scenarios
(repeatably) and `-bdd.scenario "name"` runs one scenario, which is what `bdd run --shuffle` and `--isolated` use.

## Writing steps and drivers

- Features contain no paths, binaries, selectors or SQL; everything concrete lives in `operations.go` and `system.go`.
- A step function takes the words its expression matched and a `context.Context`; the data table or doc string is read
  with `drivers.Payload(ctx)`, `drivers.Table(ctx)` or `drivers.Text(ctx)`. The world of the scenario is
  `drivers.Of(ctx)`.
- Step expressions are Go regular expressions and the **first** expression that matches wins: put a more specific one
  before a general one.
- A `then` step must assert (`bdd scan` reports S2 otherwise): call a `drivers.Assert…` function.
- No `time.Sleep`: wait for the condition (`bdd scan` reports E3).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4).
- Project-specific steps go in `RegisterProject` (`tests/steps/project_steps.go`) or in files it calls, and they must use
  the same drivers. Put their expressions where they cannot be shadowed by a core one (the core steps are registered
  first, so a project phrase needs an expression the core ones do not match).
- Give the application a clock seam that reads `world.Clock.Now`; Go has no safe way to freeze the process clock.
- Count queries with `drivers.QueryCounter`: call `Record` from the data access (a `database/sql` driver wrapper, a GORM
  callback, the repository) and return `Count` from `System.QueriesExecuted`.
- The network is blocked for `http.DefaultTransport`; a client with its own transport or dialer must use
  `drivers.DialBlocked` or be stubbed.

## Quality checks

Opt-in; add the tables you want to `.bdd/config.toml` (greenlight chooses none of them). Run them from the module you
test, and treat deprecation as an error so that the code stays on current APIs:

```toml
[adapters.quality.format]
command = 'gofmt -l tests'                 # lists unformatted files; pair with a script that fails when the list is not empty

[adapters.quality.vet]
command = 'go -C tests vet ./...'

[adapters.quality.staticcheck]             # includes SA1019, the use of a deprecated API
command = 'staticcheck -checks all,-ST1000 ./tests/...'
```

`gofmt -l` always exits 0, so a project script (`test -z "$(gofmt -l tests)"`) is the usual wrapper: commands run
without a shell, so keep it in a file the project owns. `staticcheck` is installed by the person (`go install
honnef.co/go/tools/cmd/staticcheck@<version>`).

## Known pitfalls

- A scenario title in another script or with accents works: godog writes it into the report as it is typed, and
  `bdd classify` compares letters and digits of any script (checked with godog 0.16 and a Traditional Chinese, an accented
  and a mixed title, shuffled and one scenario per process). Give a title at least one word; one made only of symbols
  has nothing to compare.
- Two scenarios whose names are a substring of each other (`Add` and `Add twice`) after dropping punctuation: name them
  apart (see the generic-junit contract).
- A scenario outline repeats its name once per example row: godog numbers them `#1`, `#2`; give each row a distinct
  title with `<param>` placeholders in the scenario name so each maps to its own example id.
- Putting the module's `go` directive higher than the Go you run: `go -C tests test` may try to download a toolchain;
  keep `tests/go.mod` at the version the project already supports.
- Reading the real clock, the real network or the real environment in the application: the scenario then depends on the
  machine. Inject the clock and the dependencies.
