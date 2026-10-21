# Adapter guide: generic-junit

For any test runner that can write a JUnit XML report: JUnit 5 with Gradle or Maven, jest, `go test`, `dotnet test`,
behave, godog, cucumber-jvm, RSpec and the like. greenlight does not know your language, so **you** supply the run
command and the step code; this adapter defines the contract between the two and checks it.

`bdd adapter apply generic-junit` copies a small, working sample (standard library only) and registers the adapter in
`.bdd/config.toml`. Nothing is overwritten. Then you replace the run command with your runner's.

## What you get

| Path | What it is | Who edits it |
|---|---|---|
| `tests/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `tests/steps/` | the step code or test code of your runner (the sample is plain `unittest`) | step-engineer |
| `tests/drivers/` | drivers and helpers your steps share (empty at first) | step-engineer |
| `tests/run_tests.py` | the sample runner: runs the sample's unittest cases and writes JUnit | replaced by your command |
| `tests/run_junit.py` | a wrapper for runners that write several report files or choose their own location (below) | nobody |

`tests/run_tests.py` and `tests/run_junit.py` are bound files like the steps: they are locked with the steps, and a
change makes a recorded run stale.

## The contract

greenlight needs five things from your runner. If they hold, `bdd run`, `bdd classify` and every gate work.

1. **One command runs one feature.** The `by_tag` command in `[adapters.run]` of `.bdd/config.toml` is split into words
   (no shell) and the placeholders are filled: `{tag}` is `FEAT-007`, `{marker}` is the same as a word, `FEAT_007`;
   `{out}` is the report file to write; `{seed}` and `{scenario}` fill the optional `shuffle` and `isolated` words (`{scenario}`
   is the name as it is; `{scenario:regex}` and `{scenario:js}` write it as a pattern for a Java/Go or a JavaScript engine,
   and `{scenario:alnum}` keeps only its letters and digits, for test names written without spaces).
   `{python}` is the interpreter running `bdd`; `{project_python}` is the project's own (see the Python adapter's guide).
   The command must run only the tests of that feature: carry the marker in a tag, a category, a trait or the test name.
2. **One JUnit file.** The command writes JUnit XML to `{out}`. If your runner writes one file per class or to a fixed
   folder (Gradle, Maven, jest-junit), wrap it with `tests/run_junit.py`, which deletes the old files, runs the command,
   and merges every `testcase` into `{out}`.
3. **A test name contains its scenario name.** This is the whole mapping from the report to the feature files:
   greenlight lower-cases the `name` of each `testcase` and drops every character that is not a letter or a digit (of any
   script: Chinese, Cyrillic and accented letters stay), and does the same to each scenario name, a second time with the
   accents removed (`Café` and `Cafe` meet); the longest scenario name contained in a test name wins. When no scenario name
   is found, a test name that carries exactly one example id of the feature (`EX-007.1.2`, also written `EX_007_1_2`) maps
   to that scenario, which covers a runner that rewrites a title beyond recognition. The scenario
   `Two numbers are added` is found in `test_two_numbers_are_added`, `TwoNumbersAreAdded`, `two numbers are added` and
   `Feature › Two numbers are added`. The `classname` is only shown. A test that matches no scenario of the feature is
   counted and ignored; a scenario with no test is `not-run` and blocks both the red and the green. Two scenarios of one
   feature must therefore not be a substring of each other's names after this clean-up (`Add` and `Add twice`): the longer
   one still wins, but name them apart.
4. **A missing seam fails with `BDD_EXPECTED_MISSING`.** Anything the system under test does not have yet must fail the
   step with a message containing that word (raise your own `ExpectedMissing`, call `fail("BDD_EXPECTED_MISSING: ...")`).
   That is how an expected failure is told from a broken test in any language. An ordinary assertion failure also counts
   as expected (see the patterns below).
5. **Compile and load errors are loud.** A build failure, an import error or an undefined step must make the command exit
   non-zero and print the reason. When the runner still writes a report, the error should be a `failure` or `error` case
   whose text names the problem, so the classifier can call it a *test defect*. When it cannot be tied to a scenario (the
   whole build failed), the scenarios are `not-run`, which blocks the gate, and `bdd run` shows the runner's output when
   no report was written. Never let a broken build look like zero tests.

## Classification

`[adapters.classify]` holds regular expressions applied to the failure text (type, message and body, in that order).
Defects are checked first, then expected failures; anything else is `unknown`, which blocks the red gate, because
guessing would let a broken test pass. The defaults cover common messages from several languages. **Run your runner once
with a broken step, once with a failing assertion, and look at the XML**: add the phrases your runner uses to the lists.

## The red phase

Same as everywhere: before any production code, every scenario must run and fail for the intended reason, and a
scenario that passes must be tagged `@existing`. Write each step so that a missing part of the system makes it fail with
`BDD_EXPECTED_MISSING` or with an assertion, never with a compile or import error.

## Filling in the run command

Edit `.bdd/config.toml` (the person edits this file; agents cannot) and replace the `by_tag` line. The runner cards in
`cards/runners/` give a tested starting point for each common runner: the command, how to filter by feature, where the
report goes, and what a red looks like there.

- A runner that takes the report path as an option (pytest `--junitxml={out}`) needs no wrapper.
- The wrapper starts the program it finds on `PATH` (never a file in the project folder), by its full name, so `npm`, `mvn` and
  `gradle` start on Windows too; a `.bat` or `.cmd` program is refused when an argument holds a character that cmd.exe reads as syntax.
- A runner that writes elsewhere uses the wrapper:
  `by_tag = '{python} -I tests/run_junit.py --reports "build/test-results/test/*.xml" --command "gradle test --tests *{marker}*"'`
  with `report = '--out {out}'`.
- Shuffle and `isolated` (one process per scenario) are optional. The sample runner's lines (`--seed {seed}`, `--only
  "{scenario}"`) fit no other runner: replace them or delete them, or the first shuffled run fails. The wrapper takes
  words for your command only as `--add=WORD` (it says so, and runs nothing, when it is given anything else):
  - Go: `shuffle = '--add=-shuffle={seed}'`, and `isolated = '--add=-run=(?i)^Test{marker}_{scenario:alnum}$'` (`go test` takes
    the last `-run`, so it narrows the feature's pattern to the one test function named for the scenario).
  - cucumber-js, run directly: `shuffle = '--order random:{seed}'`, `isolated = '--name "^{scenario:js}$"'`.
  - Node's own test runner before version 24: no random order, and a second name pattern widens the first instead of
    narrowing it, so delete both lines.
  Without the words `bdd run --shuffle` (or `--isolated`) says "has no shuffle words" and stops; with words the runner
  refuses, the run fails and shows the runner's own message. A run that finds no test case is never a success.
- If you replace `tests/run_tests.py`, update `support` in the same file so the bound plumbing still lists every file
  that decides how scenarios run (your runner's config files, the wrapper).
- Commands run with the project's directory as the working directory and with `PYTHON*`, `LD_*`, `DYLD_*`, `BASH_ENV`,
  `ENV` and `NODE_OPTIONS` removed from the environment. Pass options on the command line or in a bound config file.

## `bdd scan`

`[adapters.scan]` tells `bdd scan` how to read your step code: `step_start` finds the start of a step (the default matches
`Given(`, `When(`, `@then` and the like), `assert_patterns` says what counts as asserting, `sleep_patterns` finds fixed
waits, `stub_patterns` finds stubs (group 1 must be the stubbed name; the default is none). Adjust them for your language
or `bdd scan` will report nothing useful.

## Known pitfalls

- A command that exits 0 without writing a report. `bdd run` stops with "no test report was written".
- A filter that matches nothing (zero tests, exit 0, or a report with no `testcase`): the scenarios are `not-run`.
- Test names that are generated from data (`test_case_1`) or truncated: the scenario name is not in them, so nothing
  maps. Use the scenario name as the display name.
- A report left over from an earlier run, taken for this one. Delete it first (the wrapper does).
- Putting the marker only in a file name or a package: filters usually look at tags, categories or test names.
- Counting on `{python}` for the project's dependencies: it is the interpreter running `bdd`. Use `{project_python}`
  for a project environment, or your runner's own launcher.
