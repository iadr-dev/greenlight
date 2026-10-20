# Running the gates in CI

Hooks protect a session; CI protects the repository. A job can re-check everything that does not depend on a session: the
approvals in the committed record, the locks, a fresh run that is green, the traceability, and the optional stability,
quality and mutation checks. It needs Python 3.11+ and a checkout of the greenlight plugin (pin a release tag; nothing is
installed).

## Ready-made workflows

Each adapter ships a complete GitHub Actions workflow. Copy it to `.github/workflows/greenlight.yml`:

| Adapter | Workflow |
|---|---|
| `python-pytest-bdd` | `adapters/python-pytest-bdd/ci/github-actions.yml` (uv installs the project and pytest into a `.venv`) |
| `ts-playwright-bdd` | `adapters/ts-playwright-bdd/ci/github-actions.yml` (`npm ci` from the lockfile and the matching browser) |
| `generic-junit` | `adapters/generic-junit/ci/github-actions.yml` (you add your runner's toolchain) |

Every action in them is pinned to a commit, with its version in a comment, and the job asks for read access only. Update
the pins on purpose. `GREENLIGHT_REF` names the greenlight release the job runs; change it when you upgrade.

## What the job does

For every finished feature (`bdd status --done` lists them) it runs:

| Command | Fails when |
|---|---|
| `bdd approve FEAT-n --check` | an approval a later phase rests on is missing, was rejected or revoked, has an origin the project does not accept, or the approved files changed after it |
| `bdd lock FEAT-n --check --require` | a locked spec, step, driver or plumbing file changed, or a scope was never locked |
| `bdd run FEAT-n`, `bdd classify FEAT-n --expect green` | a fresh run is not green |
| `bdd trace FEAT-n` | a rule has no example, or an example no test |
| `bdd stability FEAT-n` | (only with `[stability]`) a scenario changes outcome between runs |
| `bdd check FEAT-n` | (only with `[adapters.quality.*]`) a quality check fails |
| `bdd mutate FEAT-n` | (only with `[adapters.mutation]`) the mutation score is below the threshold |

`bdd lint` checks the feature files against the vocabulary first. Features still in progress are left out on purpose:
their locks and approvals are not complete yet. The job also keeps `.bdd/.runs/` (the JUnit files of every run) as an
artifact, so a failure can be read afterwards.

## What the approval check can and cannot tell

`bdd approve FEAT-n --check` reads only what is committed: `state.json` and the approved files.

It can tell that:

- the files approved (the rules, the feature files) are byte for byte what the approval recorded;
- the origin recorded when the approval was verified is one the project accepts: `human` (typed by the person, checked
  against the session transcript at the time), or `headless` if `[approvals] allow_headless` is set, and `auto` or
  `self-reported` only where the autonomy level and the enforcement setting allow them;
- no approval was revoked by a change, and none is missing for a phase that rests on it.

It cannot tell that:

- the session transcript really contained the prompt: the transcript stays on the machine where the person typed, so an
  approval that was never verified there shows up as "waiting for its origin to be verified" and fails;
- `state.json` was not edited by hand: the record is not signed. Anyone who can push can rewrite it, so protect the branch
  (required reviews, no direct pushes to the main branch) and treat a pull request that touches `.bdd/features/*/state.json`
  as the thing to review.

The hashes, the locks and a fresh green run are what CI adds; the transcript check is what the machine of the person adds.
Neither replaces review of the rules and examples.

## Notes

- `--require` makes a missing lock an error, so a feature whose approval or bind lock was deleted fails the job.
- `fetch-depth: 0` is there for the mutation check, which compares with the commit at which the red was proven.
- A project that does not use uv can install with its own tool; the commands above do not depend on it.
- For the plain test run without the gates, see the adapter's own `ci.md`.
