# Running the gates in CI

Hooks protect a session; CI protects the repository. A job can re-check everything that does not depend on a session:
locks intact, the feature green, the traceability complete. It needs Python 3.11+ and a checkout of the greenlight
plugin (pin a release tag; nothing is installed).

```yaml
name: greenlight
on: [push, pull_request]
jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Get greenlight
        run: git clone --depth 1 --branch v0.1.0 https://github.com/iadr-dev/greenlight "$RUNNER_TEMP/greenlight"
      - name: Install the project and its test requirements
        run: python -m pip install -r requirements.txt pytest pytest-bdd
      - name: Check every feature
        run: |
          bdd="$RUNNER_TEMP/greenlight/tools/bdd/bdd"
          "$bdd" lint tests/features
          for dir in .bdd/features/FEAT-*; do
            id=$(basename "$dir" | grep -o '^FEAT-[0-9]*')
            "$bdd" lock "$id" --check --require
            "$bdd" run "$id"
            "$bdd" classify "$id" --expect green
            "$bdd" trace "$id"
          done
```

Notes:

- `--require` makes a missing lock an error, so a feature whose approval or bind lock was deleted fails the job.
- Features that are not finished yet (no lock) should not be in the loop; filter by `bdd status --json` if you keep
  work in progress on the same branch.
- Approvals themselves cannot be re-verified in CI (they come from a session transcript); the locks are what CI sees.
- Use `uv pip install` instead of `pip` if your project uses uv. See also `adapters/python-pytest-bdd/ci.md`.
