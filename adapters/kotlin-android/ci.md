# Running the scenarios in CI

CI runs the same command `bdd run` does, from `.bdd/config.toml`, so nothing is configured twice. The scenarios are local JVM
unit tests, so the job needs no emulator: a JDK, the Android SDK (preinstalled on GitHub's Ubuntu runners) and the greenlight
plugin's wrapper (Python 3.11 or newer, nothing to install):

```yaml
- uses: actions/setup-java@b843ebf9b913146b38da2eaa7aeddf76074ae1ad  # v6.1.0
  with:
    distribution: temurin
    java-version: "21"
- uses: gradle/actions/setup-gradle@8da46b539cd8fe6ab27ca75128919a18d757604c  # v6.4.1
- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0  # v7.1.0
  with:
    python-version: "3.12"
- run: git clone --depth 1 --branch v1.2.0 https://github.com/iadr-dev/greenlight "$RUNNER_TEMP/greenlight"
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
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
  if: always()
  with:
    name: bdd-runs
    path: .bdd/.runs/
```

Pin the actions by commit SHA in your own pipeline. `bdd run` keeps the Cucumber JUnit file of each run under
`.bdd/.runs/FEAT-n/`; the artifact makes it available when a job fails. Tests that need a device or emulator are outside
this adapter and belong in a separate job of your own.
