# Troubleshooting

Start with `bdd doctor` (`/greenlight:init` runs it). `bdd` is not on your `PATH`, so from a terminal run
`sh "<plugin folder>/tools/bdd/bdd" doctor`, with the plugin folder from the [README](../README.md#running-bdd-yourself).
Every `WARN` or `FAIL` line comes with a `fix:`.

## The machine

| Symptom | Cause and fix |
|---|---|
| `bdd` exits with code 127 or says Python is missing | Install Python 3.11 or newer. On Windows, `python.exe` is often the Microsoft Store stub: turn off its alias in Settings > Apps > App execution aliases. |
| Hooks do nothing on Windows | Hooks need Git for Windows (Git Bash). Install it; until then greenlight is in soft mode. |
| `hook latency` warns | The budget is 300 ms on Windows, 200 ms elsewhere. Antivirus scanning of the Python install or a slow disk is the usual cause; exclude the plugin folder and Python. |
| `enforcement: no hook has run in this project yet`, `integrity: no baseline yet` | Normal before the first session, and shown only once `.bdd/` exists (doctor run before `bdd init` checks only the machine). The first edit or shell command of a Claude Code session with the plugin makes the first go away, and the next prompt takes the baseline that makes the second go away. If the first stays after a session, the plugin's hooks are not running (see the Windows row above). |
| `deny rules` warns | Type the line it shows (`! sh ".../tools/bdd/bdd" doctor --add-deny-rules`) in Claude Code. It adds the missing rules to `.claude/settings.json` and keeps everything else; only you can run it, because the guard refuses it from a tool call. The rules make the protection hold even for shell spellings the guard cannot read. |
| The guard refuses a settings change | Claude may change the harmless parts of `.claude/settings.json` and `settings.local.json` (`env` entries, `permissions.allow` and `ask`, `model`). Hooks, plugins, the status line, helper commands, `permissions.defaultMode`, every deny rule and environment variables that steer the tools (`PATH`, `CLAUDE_*`, ...) are yours to change; edit the file yourself. A shell command that writes a settings file is always refused. |
| `codex hooks` warns | It appears only where the `codex` program is installed. Run `bdd install-hooks codex` to see the entries and `--apply` to write them, or ignore it if you do not use Codex in this project. Work done in Codex is soft either way. `bdd install-hooks codex --uninstall` removes them. |
| `models` fails | A name in `[models]` of `.bdd/config.toml` is not an agent, or its model is not one the Agent call accepts (`fable`, `haiku`, `opus`, `sonnet`). Fix the line or delete it; an agent without a line runs on the model of its agent file, and `bdd status` shows what each runs on. |

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
| `NOT recorded: send one approval per message` | The message held an approval command together with other text, or two commands, so nothing was recorded. Send the command alone, one gate per message. |
| Approval shows `pending` | Claude Code has not yet written your prompt to the transcript. It settles after the next turn; check with `bdd approve FEAT-n --verify`. |
| Approval `invalid` or `unverifiable` | Type the command again yourself; it only counts when it comes from your keyboard. If you had approved the same, unchanged file before and that approval was verified, it still stands and `bdd approve FEAT-n --check` says so; once the file changed, only a new approval counts. |
| You want to see what you are approving | `bdd approve FEAT-n rules --summary` (or `examples`) prints the rules or scenarios in plain words, and after a change only what changed since your last approval. It only reads. `bdd report FEAT-n` shows the same in its "Approval summary" section. |
| `... changed since it was locked` | A locked file differs from its lock. Restore it (for example `git checkout`), or if the change is intended, use `/greenlight:change`. |
| `... neither a feature's bind lock nor the plumbing lock covers it` | A step or driver file was created after every feature was bound. The next feature's bind lock takes it (`bdd lock FEAT-n --scope bind --bound`); otherwise remove it. |
| `... is shared test plumbing and changed since the project locked it` | A shared support or driver file changed. Restore it, or, if the change is intended, make it a plumbing change: `bdd lock --plumbing --reason "..."`, then rerun every bound feature once. |
| `... its bind lock was written before the shared plumbing lock existed` | Run `bdd migrate`: it moves the shared files of the old locks into `.bdd/plumbing.lock.json` (backup in `.bdd-backup-plumbing`). |
| `integrity violation #n is open` | The tripwire saw a protected file change during a tool call (settings, hooks, Claude Code's plugin records, plugin files, `.bdd/config.toml`, the test environment) and the implement and verify gates refuse. The message and `bdd status` list what changed. If you did not make the change, undo it (for example with `git checkout`) and the violation closes. If you made it or want it, type the one line the message gives, for example `/greenlight:approve integrity #3,#4 I reinstalled the test tools` (with one violation open the ids may be left out); it closes exactly those violations, if their files are still as listed, once Claude Code's transcript shows you typed it, at the next tool call or `bdd status`, and the reason is kept and shown in `bdd report`. A file that changed again after it was listed is listed anew. A locked spec or step is not acknowledged this way: use `/greenlight:change`. Never edit the files under `.bdd/.integrity` by hand. |
| The recorded tokens or time of a phase are wrong (for example an agent's cost was recorded twice) | `bdd cost FEAT-n --amend PHASE --tokens N --seconds S --reason "..."` replaces the figure. The old one stays on record with the reason, `bdd report` and `bdd pr` list every correction, and `bdd status` counts them. |
| `plugin updated from X to Y; baseline refreshed` | Information only. greenlight was updated, and its own files were taken as the new baseline instead of being reported one by one. |
| The guard blocks something you want | Locked and managed files are protected on purpose. Use `/greenlight:change`, or edit the file yourself outside the session. |
| `this project is at schema N but this greenlight writes schema M` | See [upgrading](upgrading.md). |

## Diagrams and features

| Symptom | Cause and fix |
|---|---|
| `bdd lint` L015 to L025 | Style warnings, not errors: see [the vocabulary](vocabulary.md#style-warnings). Fix the scenario, or list a code you disagree with under `[lint] ignore` in `.bdd/config.toml`. |
| `bdd lint` L026 | Two exact record tables of one entity have different columns, so one of them can never pass. Use one column set (an empty cell for an absent value), `records include:` for a part, or a second entity. If the driver of that entity reads only the columns a table lists, list it under `[lint] projected_records` in `.bdd/config.toml`: see [record tables](vocabulary.md#record-tables). |
| `bdd lint` L002 | The step is not in the [vocabulary](vocabulary.md); the message suggests the closest phrase. Add a project step only if the behaviour is real. |
| `bdd design` D5, D6 | Diagrams must be plain text; list only interfaces that exist in `system.md`. |
| `uses the boundary-value card for a date but records no leap day` (also text: empty value, maximum length; a paged list: page size 1) | The test-design gate and `bdd trace` (gap `T009`) found a rule with the `boundary-value` technique and no example of that edge. Add the example to the rule's section of `test-design.md`, or one line `- No leap day boundary: <why this rule has none>` (also `empty`, `maximum length`, `page size 1`). |
| `is tagged @existing but failed in the red run` | `bdd classify` (and the bind gate) found a scenario tagged `@existing` that failed before implementation, so it does not work yet. Remove the tag. |
| `reviews/T-n.m-code-reviewer.md is older than the code it covers` | A production file of the task changed after the reviewer finished (the message names up to three). Run the reviewer again on the task; the new report is sealed with the new files. |
| `reviews/T-n.m-code-reviewer.md has no record of the code it was written against` | The reviewer's SubagentStop did not seal the report (the report is from before this check, or the hook did not run), or the report was written without an agent id. Run the reviewer again on the task. In the verify phase go back to implement with `/greenlight:change` first. Coverage, mutation and test-cache files a tool generates in the project count as code when git does not ignore them: add them to `.gitignore`. |
| `bdd trace` shows a gap | A rule without examples or an example without a test; the code names which. |

If something looks wrong that this page does not cover, run `bdd status --json` and `bdd state show FEAT-n --json`
and include them in an issue at https://github.com/iadr-dev/greenlight/issues.
