# Troubleshooting

Start with `bdd doctor` (the plugin's wrapper is `${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd`; `/greenlight:init` runs it).
Every `WARN` or `FAIL` line comes with a `fix:`.

## The machine

| Symptom | Cause and fix |
|---|---|
| `bdd` exits with code 127 or says Python is missing | Install Python 3.11 or newer. On Windows, `python.exe` is often the Microsoft Store stub: turn off its alias in Settings > Apps > App execution aliases. |
| Hooks do nothing on Windows | Hooks need Git for Windows (Git Bash). Install it; until then greenlight is in soft mode. |
| `hook latency` warns | The budget is 300 ms on Windows, 200 ms elsewhere. Antivirus scanning of the Python install or a slow disk is the usual cause; exclude the plugin folder and Python. |
| `deny rules` warns | Only you can add the shown JSON snippet to `.claude/settings.json`; it makes the protection hold even for shell spellings the guard cannot read. |

## Running tests

| Symptom | Cause and fix |
|---|---|
| `has not been run yet` | Run `bdd run FEAT-n` before the bind or verify gate. |
| `the recorded run is out of date` | A feature file, step, driver or plumbing file changed since the run. Run it again. |
| `used another interpreter` | The project's interpreter changed (new `.venv`, new `python =`). Run `bdd run` again from the project. |
| `pytest` or `pytest_bdd` not found | Install them in the project's environment (`uv pip install pytest pytest-bdd`, or pip), or point greenlight at the right interpreter: `bdd init --python PATH` or `python = "PATH"` in `.bdd/config.toml`. The agents cannot install packages. |
| Tests need `PYTHONPATH` | It is not passed on. Set `pythonpath` in `tests/pytest.ini` (a bound file). |
| `not a valid red` | Read the listed problems: a *test defect* (import error, unmapped name, undefined step) needs the steps fixed; an *unknown* failure needs a classification pattern or a fix; a scenario that passes needs `@existing` if the behaviour truly exists. |
| `not a valid red` after `/greenlight:change`, with scenarios that "passed before implementation" | The feature was reopened after its code was written, so the code makes the tests pass. Run `bdd run FEAT-n --against-red`: it proves the red against the production source of the first red, in a temporary worktree. Do not stash or revert the code, and do not tag those scenarios `@existing`. |
| `--against-red`: "no recorded red", "not committed", or "digest differs" | The feature never passed the bind gate with `--record-red`; or its red was recorded, before snapshots were kept, with production changes that were not committed; or the source at that commit is not the one the red was proven on. None can be reproduced: say so in the report and ask the person how to proceed. |
| `--against-red`: "cannot link the installed folder node_modules" | The folder could not be linked into the temporary worktree, so nothing was run. On Windows greenlight makes a junction, which needs no privilege but a local NTFS drive for both the project and the temporary folder (`TEMP`): move the project off a network share, or point `TEMP` at a local drive, or turn on Developer Mode so symbolic links work; then run the command again. On macOS and Linux, make the temporary folder (`TMPDIR`) writable. |
| `--against-red`: the application's own build fails in the worktree with "Could not find the Next.js package" | Turbopack (Next.js 16) does not read `next` through a link to a folder outside its project root. greenlight copies a `node_modules` that holds `next` instead of linking it (the result message says "(copied)"), so this appears only when `next` is installed somewhere greenlight does not look (deeper than 4 folders below the project root) or when an older greenlight linked it. Install `next` in a folder greenlight finds, or build with `next build --webpack`, which works through a link (Next.js documents that flag; it is your test configuration, so you decide it). |
| `--against-red`: "the test report holds no test cases", and the message lists the folders linked or says the project has none | The runner found no tests in the worktree. If the project has no `node_modules`, `.venv` or `venv`, install the dependencies first (with your own tool) and run again. If it has them, the tests really found nothing: check the feature tag and the run command. |
| `--against-red` tests fail with missing packages | The project's environment holds an editable install that points at the project's own source, so the worktree loads today's code. Install the project without editable mode. |
| `--against-red`: "the temporary worktree ... was left in place because these links ... could not be removed" | A program still holds the link open. Close it, remove each named link itself (`rmdir` on Windows, `rm` without `-r` elsewhere; never delete the contents), then delete the worktree folder and run `git worktree prune`. |
| A scenario in `unknown` | Its failure text matches no pattern. Run `bdd classify FEAT-n` to see the text. |

## Gates, locks and approvals

| Symptom | Cause and fix |
|---|---|
| `NOT recorded` after `/greenlight:approve` | The line says why; typically the feature is not at that gate yet, or the typed text does not match (`FEAT-n` and `rules` or `examples` exactly). Type it again yourself. |
| Approval shows `pending` | Claude Code has not yet written your prompt to the transcript. It settles after the next turn; check with `bdd approve FEAT-n --verify`. |
| Approval `invalid` or `unverifiable` | Type the command again yourself; it only counts when it comes from your keyboard. |
| `... changed since it was locked` | A locked file differs from its lock. Restore it (for example `git checkout`), or if the change is intended, use `/greenlight:change`. |
| `... is a step, driver or plumbing file that was never locked` | A file that matches the bound paths was created after the bind lock. Re-lock with `bdd lock FEAT-n --scope bind --bound` through the bind phase, or remove the file. |
| `integrity violation #n is open` | The tripwire saw a protected file change (settings, hooks, plugin files, `.bdd/config.toml`, the test environment). It closes when the file is back as it was; your own edits between prompts are accepted at your next prompt. `bdd status` lists them. |
| The guard blocks something you want | Locked and managed files are protected on purpose. Use `/greenlight:change`, or edit the file yourself outside the session. |
| `this project is at schema N but this greenlight writes schema M` | See [upgrading](upgrading.md). |

## Diagrams and features

| Symptom | Cause and fix |
|---|---|
| `bdd lint` L015 to L025 | Style warnings, not errors: see [the vocabulary](vocabulary.md#style-warnings). Fix the scenario, or list a code you disagree with under `[lint] ignore` in `.bdd/config.toml`. |
| `bdd lint` L002 | The step is not in the [vocabulary](vocabulary.md); the message suggests the closest phrase. Add a project step only if the behaviour is real. |
| `bdd design` D5, D6 | Diagrams must be plain text; list only interfaces that exist in `system.md`. |
| `bdd trace` shows a gap | A rule without examples or an example without a test; the code names which. |

If something looks wrong that this page does not cover, run `bdd status --json` and `bdd state show FEAT-n --json`
and include them in an issue at https://github.com/iadr-dev/greenlight/issues.
