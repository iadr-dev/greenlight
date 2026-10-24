# Running the scenarios in CI

CI runs the same command `bdd run` does, from `.bdd/config.toml`, so nothing is configured twice. The job needs a JDK,
Maven (preinstalled on GitHub's hosted runners) and the greenlight plugin's wrapper (Python 3.11 or newer, nothing to
install):

```yaml
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: "21"
    cache: maven
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: git clone --depth 1 --branch v1.1.0 https://github.com/iadr-dev/greenlight "$RUNNER_TEMP/greenlight"
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

Pin the actions by commit SHA in your own pipeline. `bdd run` keeps the Cucumber JUnit file of each run under
`.bdd/.runs/FEAT-n/`; the artifact makes it available when a job fails. The first Maven run downloads the dependencies,
so cache `~/.m2` (the `cache: maven` line does).
