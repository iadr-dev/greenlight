# Engineering standards

Status: APPROVED

Approved by the person running the evaluation, for the evaluation runs of this reference app. It is copied into the
project's `.bdd/standards.md` by the evaluation harness, acting as that person.

Each rule is marked [tool] (enforced by a linter, type checker, test or CI step) or [review] (enforced by the auditor
reading the change). A [tool] rule whose tool is not named in an `[adapters.quality.NAME]` table is checked by the
auditor until it is.

## Language and toolchain

- Language and version: Go, at the language level `go.mod` declares (`go 1.22`), built with the Go toolchain installed on the machine.
- Build and package tool: go modules; standard library only (there is no `go.sum`).
- Frameworks: none.
- Project type: existing. The tool is one package, `main`, in `main.go`; its conventions are kept unless this file says otherwise.

## Style

- Formatter: gofmt; code is formatted, never hand-aligned. [tool]
- Naming: names say what a thing is or does, in the domain's own words (row, column, group, total). Short names only where Go convention uses them (`err`, `i`, `w`). [review]
- Casing follows Go: `camelCase` unexported, `PascalCase` exported, no underscores. [tool]
- Comments explain why, never what (doc comments excepted). No commented-out code, no TODO without an issue reference. [review]
- Every function has a doc comment that starts with its name, as `run` and `count` do. [review]

## Clean code

- One function does one thing, at one level of abstraction. Target: under 30 lines and cyclomatic complexity under 10. [review]
- At most 4 parameters; beyond that, pass a struct. No boolean flag parameters that switch behaviour. [review]
- Nesting is at most 3 levels deep; return early on errors. [review]
- No magic numbers or strings: exit statuses use the existing `exitOK`, `exitInvalid` and `exitUsage` constants. [review]
- No dead code: unused functions, parameters, imports and variables are deleted (the compiler refuses most of them). [tool]
- A command reads its input, computes with pure functions and writes its output; the computation does not print. [review]

## No duplicated code (DRY)

- A rule, parse step or message exists in exactly one place; a new command reuses the existing CSV reading and usage handling. [review]
- Do not merge code that merely looks alike; two blocks that change for different reasons stay separate.
- Duplication detector: none is run in this project; duplication is checked by review. [review]
- Test code is held to the same rule: shared setup goes into helpers or table-driven tests.

## Architecture

- Layers: none beyond the package: `run` dispatches the subcommand, each subcommand is one function taking its arguments and the output writers, so tests drive it without a process. [review]
- No global state; `os.Stdout`, `os.Stderr` and the arguments are passed in, as `run` does. [review]

## Folder and file structure

- The existing layout is kept: `main.go` and `main_test.go` in the module root, and `tests/` for the greenlight scenarios. A second file in package `main` is fine once `main.go` holds more than one concern. [review]
- Test data lives with the tests (Go convention: next to the test, or under `testdata/`) and is never read by production code. [review]

## Error handling and logging

- Errors are never ignored: every returned `error` is checked. [tool]
- Invalid input exits with `exitInvalid` (1) and a message on stderr that names the file, the line or the value; a usage mistake exits with `exitUsage` (2) and the usage line; nothing goes to stdout on an error. [review]
- Errors are wrapped with context (`fmt.Errorf("...: %w", err)`), not swallowed or replaced by a generic text. [review]

## Quality rules

- Linter: `go vet ./...`, run by `bdd check` once it is in `[adapters.quality]`; until then the auditor checks the diff against it. [tool]
- Suppressions need an inline reason and are named in the report. [review]
- Every behaviour change has a scenario; a bug fix has a regression scenario or unit test that fails without the fix. [review]
- Test layers: the unit tests in `main_test.go` and the greenlight scenarios in `tests/`, which drive the built command; both are deterministic and independent of order. [review]
- Coverage: not measured; every rule must have its scenarios (`bdd trace`). [review]
- Numbers that are summed are exact (`math/big` or integers), never floating point. [review]

## Performance

- The input is read once, as a stream; a whole file is not held in memory twice. [review]
- No optimisation without a measurement that justified it. [review]

## Deprecation policy

- Code uses the current, non-deprecated API of the standard library.
- Go has no compiler switch that refuses a deprecated API, and staticcheck is not run in this project, so the auditor checks the diff against the package documentation (deprecated identifiers are marked `Deprecated:` there). [review]

## API

- The command line is the interface: `csvtool count FILE`, and any new subcommand with its options. Changing the output format or the exit status of an existing subcommand is breaking and is named in the report.

## Dependencies

- Standard library only. A new module dependency is a decision the person makes; it is named in the report, never added silently.
