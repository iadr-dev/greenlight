# Running the scenarios in CI

CI runs the same command `bdd run` does, from `.bdd/config.toml`, so nothing is configured twice. The job needs your
runner's toolchain and the greenlight plugin's wrapper (Python 3.11 or newer, nothing to install). The complete workflow,
with every action pinned to a commit, is `ci/github-actions.yml` next to this file; copy it to
`.github/workflows/greenlight.yml` and add your runner's setup step (JDK, Node, Go or .NET) where it says so.

It checks, for every finished feature, the approvals in the committed record, the locks, a fresh green run, the
traceability, and the optional stability, quality and mutation checks; `docs/ci.md` explains each step and what the
approval check can and cannot tell.

`bdd run` keeps the JUnit file of each run under `.bdd/.runs/FEAT-n/`; the workflow uploads that folder as an artifact so
a failed job can be read afterwards. If your runner is not installed on the CI machine, `bdd run` stops with "not on PATH"
before any scenario runs.
