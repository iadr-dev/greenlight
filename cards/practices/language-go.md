---
id: language-go
kind: practice
apply_when: writing or judging production code in a Go project
output: code that follows the Go version in go.mod, is gofmt clean, passes vet and staticcheck, and uses no deprecated API
phase: implement
pairs_with: [mutation-check]
---
## Intent

The `go` directive in `go.mod` (and `toolchain`, if present) is the standard. Write for that version with its current
standard library; raising the Go version or a module version is a decision of the person.

## How to apply

1. Read `.bdd/standards.md`, `go.mod` and the lint configuration (`.golangci.yml`).
2. Commands:
   - format: `gofmt -l .` prints the files that are not formatted; a non-empty output is a failure (wrap it in a script the project owns, since `gofmt` exits 0)
   - vet: `go vet ./...`
   - static analysis including deprecated use (check SA1019): `staticcheck ./...`, or `golangci-lint run`
   - build and tests: `go build ./...`, `go test -race ./...`
   - modules: `go mod tidy` must leave `go.mod` and `go.sum` unchanged
3. To have greenlight run them, add tables to `.bdd/config.toml`:

   ```toml
   [adapters.quality.vet]
   command = 'go vet ./...'

   [adapters.quality.staticcheck]
   command = 'staticcheck ./...'
   ```

4. Read the current documentation of every package you call (`go doc`, pkg.go.dev, or a documentation tool such as
   context7). `Deprecated:` comments in doc text are the signal.

## Known pitfalls

- Ignoring errors (`_ = f()`), and wrapping them without `%w`, which loses the cause.
- `io/ioutil`, `interface{}` where `any` is in use, and other pre-1.16 and pre-1.18 idioms.
- Goroutines without a way to stop, and loops that capture a loop variable in versions before 1.22.
- `//nolint` without a reason, and `init()` functions with side effects.
- Adding a module to `go.mod` to avoid a few lines of code; dependencies are the person's decision.
- A formatter check wired as `gofmt -l` alone: it exits 0 even when files need formatting.
