---
id: godog
kind: runner
apply_when: "a Go project whose scenarios run with godog, the Cucumber implementation for Go (the generic-junit adapter)"
---
## Run

godog has its own command and writes JUnit with `--format junit:FILE`. Pin its version, so the run is repeatable:

```toml
[adapters.run]
by_tag = 'go run github.com/cucumber/godog/cmd/godog@v0.15.0 run --tags @{tag} tests/features'
report = '--format junit:{out}'
```

The step code lives in a test package that registers a `godog.TestSuite`; if you prefer `go test`, set the formatter in the
test options (`Format: "junit:report.xml"`) in a bound file and wrap it with `tests/run_junit.py` as the go-test card shows.
Add `go.mod` and `go.sum` to `support`.

## Report

`<testsuites><testsuite><testcase name="<scenario>" status="passed|failed|undefined">`. The scenario name is the test name, so the
mapping is direct. The fixtures in `tools/bdd/tests/fixtures/junit/godog` are a real run (godog v0.16.0 with the `junit`
formatter, Go 1.27.3, 2026-10-21). A scenario whose first step fails has the later steps listed as `<error type="skipped">`,
and a `status="passed"` scenario can still carry a `<failure>` from a later step: classification uses the failure elements.

## What red looks like

- A step that returns an error: `<failure message="Step I add 2 and 3: BDD_EXPECTED_MISSING: add" type="failed">`. Return
  `fmt.Errorf("BDD_EXPECTED_MISSING: add")` for a part of the system that does not exist yet.
- An assertion that returns `fmt.Errorf("expected %d, got %d", want, got)` matches the default "expected ... got" pattern.
- An undefined step is `<error message="Step I add 2 and 3" type="undefined">`, one element per undefined step (the message does not
  say "undefined"; the `type` does): the default patterns call it a test defect.
- A compile error in the step package stops `go run`/`go test` before any report: the scenarios are `not-run`.

## Known pitfalls

- `--tags @FEAT-007` needs the tag on the `Feature:` line.
- The `junit` formatter writes the file at the end of the run; a panic in a step can leave no file. `bdd run` then shows the output.
- godog's `--strict` makes undefined and pending steps fail the run; keep it on, so a missing step is loud.
- Random order: `--random=SEED` exists in godog; use `shuffle = '--random={seed}'`.
