---
id: jest
kind: runner
apply_when: "a JavaScript or TypeScript project tested with jest (the generic-junit adapter); for browsers see the UI adapters"
---
## Run

Put the marker in the name of the `describe` block, and the scenario name in each `it`:

```ts
describe("FEAT_007 Order discounts", () => {
  it("Two numbers are added", () => { ... });
});
```

Install `jest-junit` and set its output in `package.json` (so the location is a bound file, not an environment variable):

```json
"jest-junit": { "outputDirectory": "reports", "outputName": "junit.xml" }
```

```toml
[adapters.run]
by_tag = '{python} -I tests/run_junit.py --reports "reports/junit.xml" --command "npx jest --ci --reporters=default --reporters=jest-junit -t {marker}"'
report = '--out {out}'
shuffle = '--add=--randomize --add=--seed={seed}'
```

Add `tests/run_junit.py`, `package.json` and the jest configuration file to `support`. `--randomize` and `--seed` need jest 29.2
or newer; leave `shuffle` out for older versions. The command is not run through a shell: on Windows write `npx.cmd`.

## Report

jest-junit writes one file. A case `name` is by default `<describe> <test title>`, which contains both the marker and the scenario
name. If you changed `titleTemplate`, keep the test title in it.

## What red looks like

A failed `expect` is a `<failure>` whose text reads `Error: expect(received).toBe(expected)` followed by `Expected: 5` and
`Received: 4` on separate lines. The default patterns look for `expected ... to`/`but` on one line, so add `expect\(received\)`
to `expected_fail`. Throw `new Error("BDD_EXPECTED_MISSING: ...")` for an unbuilt seam.
A syntax or import error fails the whole test file: the suite is reported with `SyntaxError` or `Cannot find module`
(add `Cannot find module` to `test_defect`).

## Known pitfalls

- `-t` is a regular expression on the full test name; a marker that is a prefix of another (`FEAT_1` and `FEAT_10`) selects both.
- With `-t`, tests that do not match are skipped, not absent: the report may hold skipped cases of other features; they map to no
  scenario here and are ignored.
- jest exits 1 and writes nothing when the configuration is invalid; `bdd run` then says no report was written.
- Watch mode and caching are not wanted in a recorded run: keep `--ci` and avoid `--watch`.
