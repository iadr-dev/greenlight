# Running the scenarios in CI

CI runs the same command `bdd run` does, from `.bdd/config.toml`, so nothing is configured twice. The job needs your
runner's toolchain and the greenlight plugin's wrapper (Python 3.11 or newer, nothing to install):

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: git clone --depth 1 --branch v0.1.0 https://github.com/iadr-dev/greenlight "$RUNNER_TEMP/greenlight"
# ... set up your runner's toolchain here (JDK, Node, Go, .NET) ...
- name: Check every finished feature
  run: |
    bdd="$RUNNER_TEMP/greenlight/tools/bdd/bdd"
    for dir in .bdd/features/FEAT-*; do
      [ -d "$dir" ] || continue
      id=$(basename "$dir" | grep -o '^FEAT-[0-9]*')
      "$bdd" lock "$id" --check --require
      "$bdd" run "$id"
      "$bdd" classify "$id" --expect green
    done
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: bdd-runs
    path: .bdd/.runs/
```

`bdd run` keeps the JUnit file of each run under `.bdd/.runs/FEAT-n/`; the artifact above makes it available when a job
fails. If your runner is not installed on the CI machine, `bdd run` stops with "not on PATH" before any scenario runs.
