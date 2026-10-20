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
| `bdd lint` L002 | The step is not in the [vocabulary](vocabulary.md); the message suggests the closest phrase. Add a project step only if the behaviour is real. |
| `bdd design` D5, D6 | Diagrams must be plain text; list only interfaces that exist in `system.md`. |
| `bdd trace` shows a gap | A rule without examples or an example without a test; the code names which. |

If something looks wrong that this page does not cover, run `bdd status --json` and `bdd state show FEAT-n --json`
and include them in an issue at https://github.com/iadr-dev/greenlight/issues.
