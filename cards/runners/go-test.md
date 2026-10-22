---
id: go-test
kind: runner
apply_when: "a Go project tested with go test (the generic-junit adapter), including godog features"
---
## Run

Go has no tags in test names, so put the marker and the scenario name in the name of the test function:

```go
func TestFEAT_007_TwoNumbersAreAdded(t *testing.T) { ... }
```

`go test` itself writes no JUnit; use `gotestsum` (install it with the project's tools, pinned):

```toml
[adapters.run]
by_tag = '{python} -I tests/run_junit.py --reports "reports/go.xml" --command "gotestsum --junitfile reports/go.xml -- ./... -run {marker}"'
report = '--out {out}'
shuffle = '--add=-shuffle={seed}'
isolated = '--add=-run=(?i)^Test{marker}_{scenario:alnum}$'
```

Add `tests/run_junit.py` and `go.mod` to `support`. `-shuffle` needs Go 1.17 or newer. `isolated` relies on the test function being named for the scenario without spaces or
punctuation (`TestFEAT_007_TwoNumbersAreAdded`): `go test` takes the last `-run`, which narrows the feature's pattern to that one
test. Both lines were run for real with `gotestsum` v1.13.0 on Go 1.27 (v1.12.1 does not build on Go 1.25 or newer). For godog features use the `go-godog`
adapter instead of this recipe: it ships the steps, the drivers, godog's own JUnit report and the run command, with the tag
passed as a test flag (`Tags: "@FEAT-007"` in the test options).

## Report

gotestsum writes one JUnit file with the package as `classname` and the test function as `name`. Subtests are separate cases
named `TestX/sub_name`.

## What red looks like

Go has no assertion exception, so a failing `t.Errorf` shows as a `<failure message="Failed">` with the printed lines in the body
(`file_test.go:12: got 4, want 5`). The default patterns do not know `got/want`: either use an assertion library (testify prints
`Error Trace:` and `expected:`) and add `Error Trace|expected:` to `expected_fail`, or fail unbuilt seams with
`t.Fatal("BDD_EXPECTED_MISSING: ...")`. A compile error fails the package: the body holds the compiler output (`undefined: Foo`),
which the default test-defect pattern matches.

## Known pitfalls

- `-run` is a regular expression: `FEAT_1` also selects `FEAT_10`; end the marker with `_` in the function name.
- Cached results (`(cached)`) are not re-run; gotestsum passes `-count=1` only if you give it: add `-count=1` after `--`.
- A package with no tests is reported as `no test files`, not as a failure; those scenarios are `not-run`.
- Parallel subtests interleave output; the failure text per case stays correct in the JUnit file.
