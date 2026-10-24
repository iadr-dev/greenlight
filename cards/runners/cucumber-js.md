---
id: cucumber-js
kind: runner
apply_when: "a JavaScript or TypeScript project whose scenarios run with cucumber-js (the generic-junit adapter)"
---
For a TypeScript project, the `ts-cucumber-js` adapter ships this recipe ready made (steps, drivers, `tsx` loader, pinned tooling and
the run command); use it instead unless you already have cucumber-js steps of your own.

## Run

cucumber-js reads the `.feature` files itself and writes JUnit with its built-in formatter, so no wrapper is needed:

```toml
[adapters.run]
by_tag = 'node node_modules/@cucumber/cucumber/bin/cucumber.js --tags @{tag}'
report = '--format junit:{out}'
```

Add the cucumber configuration file (`cucumber.js` or `cucumber.json`), `package.json` and the lockfile to `support`. For
TypeScript steps add the loader your project uses (`--require-module ts-node/register`, or a compiled `dist/`) in the
configuration file, not on the command line, so the file is bound. Shuffle: `shuffle = '--order random:{seed}'`. One scenario:
`isolated = '--name "^{scenario:js}$"'`. `--name` takes a JavaScript regular expression: `{scenario:js}` escapes the
metacharacters and writes a character beyond ASCII as `\uXXXX`, which JavaScript reads, while `{scenario:regex}` writes
`\x{HEX}`, which it does not (an accented title would select nothing). Both flags were checked on cucumber-js 11.2.0.
Behind the wrapper `tests/run_junit.py` each word is given as `--add=WORD`.

## Report

One `<testsuite>` with one `<testcase>` per scenario: `classname` is the feature name and `name` is the scenario name, which is
exactly what greenlight maps on. Verified against `@cucumber/cucumber` 11.2.0 (the files are in `tools/bdd/tests/fixtures/junit/cucumber-js`).

## What red looks like

- A step that throws (`throw new Error("BDD_EXPECTED_MISSING: add")`) is a `<failure type="Error" message="BDD_EXPECTED_MISSING: add">`:
  an expected failure. A failing `node:assert` is a `<failure type="AssertionError" ...>`: also expected.
- A step nobody defined is an **empty** `<failure/>`; the words `undefined` appear only in `<system-out>`. `bdd classify` reads the
  output when a failure has no text, and the default patterns call it a test defect.
- A syntax error or a missing module in a steps file stops cucumber-js before any report is written (exit code non-zero, no file):
  `bdd run` shows the output and the scenarios are `not-run`.

## Known pitfalls

- `--tags @FEAT-007` selects the feature only if the tag is on the `Feature:` line (greenlight puts it there).
- Pending steps (`return "pending"`) are reported as skipped, which blocks the red as "did not run".
- Parallel workers (`--parallel`) merge into one report, but their output order varies; do not combine with `--order random` for a repeatable seed.
- The formatter path is relative to the project directory; `{out}` is absolute, which is fine.
