# greenlight pipeline plan

Eleven PRs make greenlight faster and more correct on a real product, and make its README match the code.
They are for every person who runs `/greenlight:feature`, programmer or not, as the Fieldly run did over two days and three features.
The rule the program enforces is that a choice greenlight can check is made and checked before code is written, and that a protection never blocks legitimate work.
The PRs in order are P1 tripwire, P2 guard, P3 shared test plumbing, P4 earlier checks, P5 approvals, P6 agents and costs, P7 README and docs, P8 init records the project, P9 design stage, P10 technical design and design review, P11 implement against the design.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `skills/poteto-mode/playbooks/autopilot-stack.md` from the installed plugin, because P9 to P11 build on each other and P1 to P8 share `guard.py`, `tripwire.py` and the playbooks. The operator merges every PR. Every PR stops at merge-ready.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on the operator's explicit go.
- [ ] On the operator's go, write this exact text into `notes.md` in the program's store under `~/.claude/orchestrate/greenlight-pipeline/`, and restate it in your todolist. "Plan ~/.claude/orchestrate/greenlight-pipeline/docs/plan.md. PRs P1 to P11 in order, each stacked on the one before. A PR is verified only when its unit, live and perf boxes are checked. The operator merges every PR. Done when all eleven are merged, the Fieldly refusal corpus replays with no false positive, and the README audit has no wrong or outdated row."
- [ ] Read these from the installed plugin at program start. Re-read them at every tick.
  - [ ] `skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `skills/swarm/SKILL.md`
  - [ ] `skills/run/SKILL.md`, the driver for the `bdd` command line, the hooks and the evaluation harness
  - [ ] `skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `skills/technical-writing/SKILL.md` and `skills/unslop/SKILL.md` for every README, card, agent and playbook change
- [ ] Arm the hourly audit tick as a real `/loop` in dynamic mode, which schedules its own wake-up rather than blocking on a sleep. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from the installed plugin and the objective in the program store's `notes.md`. Audit the operation against both and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then post a short status message to the operator in chat only when the audit found a tracked change that no earlier status message reported, such as a PR opened, a code-ready head, a round launched or closed, a verdict, a merge, a stuck agent and the action taken, a blocker added or cleared, or a decision only the operator can make. Name every such change and nothing else. Do not repeat a table, the merged list, or an unchanged blocker. If the audit found none, end the turn with no reply text. Either way, log this tick's row in your decision trail. The row names the items reported, or none."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the execution playbook stacks.
  - [ ] P1 is first. It branches from `main`.
  - [ ] Each of P2 to P11 is based on the branch of the PR before it.
- [ ] Hold the file boundaries. P1 touches `tripwire.py`, `initcmd.py`, the approve hook and their tests. P2 touches `guard.py`, `codexguard.py`, `doctor.py`, `claudepaths.py` and their tests. P7 touches only `README.md`, `docs/` and `CHANGELOG.md`. Every PR also writes its spec in `specs/`, its decision in `docs/dev/decisions.md` and its `CHANGELOG.md` entry.
- [ ] Hold the review gate. P5 and P9 change what the person sees and does, so the operator reviews them with screenshots and a video before merge. P1, P2, P10 and P11 change protections or what agents are told, so the operator reads their diffs in chat before merge.

### PR mechanics, for every PR

- [ ] Resolve the forge once. Default to `gh`; if `command -v origin` succeeds and Origin can resolve the repository, use `origin pr` for every PR operation. Record any fallback to `gh`. Never require `gt`.
- [ ] Open the PR ready, never draft, per **Opening a PR**. Use the run's built-in PR tool when it has one, else `origin pr create --status open --base <base-branch>` or `gh pr create --base <base-branch>` according to the resolved forge. A stack child targets its parent branch.
- [ ] Run the repo's lint and typecheck once before the PR-facing push. For this repo that is `python -m unittest discover -s tests -t .` in `tools/bdd`, `claude plugin validate . --strict` and `claude plugin validate skills --strict`. Push with hooks on.
- [ ] Run `/deslop` before each commit and `/no-comments` before review.
- [ ] Triage every review-bot and security-reviewer comment per `../references/bugbot-triage.md`.
- [ ] Before the code-ready report and babysit, and again after merge prep, record the base and head SHAs prepared by the topology owner under the execution playbook.

### Verdict and merge, for every PR

- [ ] A full swarm runs once, at the code-ready head. Another full swarm runs only for new behavior, a redesign, or a large new diff. A rebase, a merge-conflict resolution, or a minor fix gets a single verifier at the new head, and a wording-only change gets none. Run each full swarm per `skills/swarm/SKILL.md`. One gates lane. The ten live lanes from the PR's **Verify, live** block. The perf lane from its **Verify, perf** block. Two or more audit lanes, each with its own focus, that read the diff and the receipts and distrust the PR body. The root audits the receipts in the merge-ready report before the verdict.
- [ ] Judge every finding by the execution playbook's blocking rule. The verdict is clean when none blocks. A failure on trunk behavior in a lane marked `Regression lane against trunk.` is recorded against trunk and does not block the PR. A new head gets a fresh verdict, except for results that stay valid under the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges each PR bottom-up with delete branch. A PR whose patch-id is unchanged after a rebase keeps its verdict, per `playbooks/shipping.md`.

### Boot recipe, for every live lane

Each live lane runs in its own worktree at the PR head. Drive through the skill path or exact commands recorded in this boot recipe.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] Create a scratch project under the system temp folder with `git init`, then `sh <worktree>/tools/bdd/bdd init --adapter <adapter>` and `sh <worktree>/tools/bdd/bdd init --smoke`. Ready when `bdd status` prints the project.
- [ ] For hook lanes, start `claude -p` in the scratch project with `--plugin-dir <worktree>` and `--setting-sources project`, as `evals/platform-probe/guard_e2e.py` does. Deliver input only through `bdd` commands, those sessions and file writes. Read-only diagnostics are `bdd status`, `bdd doctor`, `bdd trace` and `bdd lint`.
- [ ] Save every terminal capture to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.txt` and every page screenshot to `<slug>.png`, and return the paths with the report.

## Stop the integrity check from blocking ordinary changes (P1)

**Depends on.** None.

**Files.**

- [ ] Edit `tools/bdd/bddlib/tripwire.py`, `tools/bdd/bddlib/initcmd.py`, `tools/bdd/bddlib/approvehook.py`, `tools/bdd/bddlib/approvalcommand.py`, `skills/approve/SKILL.md`.
- [ ] Create `specs/features/integrity-acknowledge.feature` (FEAT-109), red before the code.
- [ ] Edit `tools/bdd/tests/test_tripwire.py`, `docs/troubleshooting.md`, `docs/upgrading.md`, `docs/dev/decisions.md` (D63), `CHANGELOG.md`.

**Build.**

- [ ] The baseline keys plugin files by their path relative to the plugin root, and records the plugin version. A changed version re-baselines the plugin files and records one "plugin updated from X to Y" line instead of one violation per file.
- [ ] `bdd init` takes the first baseline.
- [ ] The person acknowledges open violations by typing `/greenlight:approve integrity <reason>`, read by the UserPromptSubmit hook like any approval. The CLI records who, when and why. No agent and no shell command can do it.
- [ ] A change the person makes between prompts is accepted at the next prompt even when a background agent's tool call saw it first. The hook compares the change's time with the last prompt and the agent's start.

**You see.**

- [ ] After a plugin update, `bdd doctor` prints `integrity: plugin updated from 1.2.1 to 1.2.2; baseline refreshed` and no violation is open.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_tripwire.py` gains plugin-update, init-baseline, acknowledge and person-change-seen-by-agent cases. Run `python -m unittest tests.test_tripwire -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Swap the plugin folder for a copy with a new version at trunk and head, then send a prompt. Save `update.txt`. Pass when trunk records its per-file violations and head opens none.
- [ ] Lane 2. Run `bdd init` and send the first prompt. Save `init.txt`. Pass when no "baseline missing" violation is opened.
- [ ] Lane 3. Edit `.bdd/config.toml` by hand between prompts while a background agent runs. Save `person-edit.txt`. Pass when the change is accepted at the next prompt.
- [ ] Lane 4. Have an agent edit `.bdd/config.toml` with an unreadable spelling. Save `agent-edit.txt`. Pass when a violation opens and the implement gate refuses.
- [ ] Lane 5. Type `/greenlight:approve integrity tools reinstalled`. Save `ack.txt`. Pass when the violation closes with the reason recorded.
- [ ] Lane 6. Have the model run `bdd approve integrity` from Bash. Save `ack-agent.txt`. Pass when it is refused.
- [ ] Lane 7. Install a test package by hand with pnpm. Save `install.txt`. Pass when the change is accepted at the next prompt.
- [ ] Lane 8. Open `bdd report FEAT-1`. Save `report.png`. Pass when acknowledged violations show with their reason.
- [ ] Lane 9. Follow `docs/troubleshooting.md` for an open violation. Save `doc.txt`. Pass when no step asks for a JSON edit.
- [ ] Lane 10. Replay Fieldly's 151 violation causes in a scratch project. Save `fieldly.txt`. Pass when only the agent-made ones stay open.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. PostToolUse and UserPromptSubmit hook time.
- [ ] Probe. Each hook 20 times at trunk and head, interleaved, on the same project.
- [ ] Baseline. Record the trunk medians first.
- [ ] Rule. Each hook stays under 200 ms on macOS and Linux and 300 ms on Windows, and adds at most 20 ms to trunk.

**Review gate.** The operator reviews before merge.

- [ ] Copy a screenshot of lanes 1, 5 and 10 into `docs/dev/review/P1-review-*.png`.
- [ ] Record a 30 to 60 second video of lanes 1 and 5. Save it as `docs/dev/review/P1-review.mp4`, kept out of the commit.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P1.

## Stop the guard from refusing legitimate work, and let Claude edit settings safely (P2)

**Depends on.** P1.

**Files.**

- [ ] Create `tools/bdd/tests/fixtures/guard/fieldly-refusals.jsonl`, the 170 refused calls from the Fieldly run with paths and personal text anonymised, each labelled allow or refuse.
- [ ] Edit `tools/bdd/bddlib/guard.py`, `tools/bdd/bddlib/codexguard.py`, `tools/bdd/bddlib/claudepaths.py`, `tools/bdd/bddlib/tripwire.py`, `tools/bdd/bddlib/doctor.py`, `skills/init/SKILL.md`.
- [ ] Create `specs/features/guard-precision.feature` (FEAT-110).
- [ ] Edit `tools/bdd/tests/test_guard.py`, `tools/bdd/tests/test_doctor.py`, `docs/dev/decisions.md` (D64, amending D15), `CHANGELOG.md`.

**Build.**

- [ ] The bdd CLI's own path as the program word is not a write to the plugin.
- [ ] Quoted arguments and regular-expression literals are removed before the guard looks for write words and globs.
- [ ] A locked file is matched by its resolved path when the command names a path, not by its bare name anywhere in the text.
- [ ] Files under the system temp folder and outside every project are scratch, not production.
- [ ] `~/.claude/projects/*/memory/` is not a transcript.
- [ ] Read-only tool runs (`npx --no-install tsc --noEmit`, a runner under `node_modules/.bin`) are not installs.
- [ ] A settings edit is judged by its effect. The guard computes the new file, parses old and new as JSON, and refuses only a change to `hooks`, `disableAllHooks`, greenlight's `enabledPlugins` entry, greenlight's deny rules or `permissions.defaultMode`, or invalid JSON. Shell writes to settings stay refused.
- [ ] The tripwire fingerprints only those keys of the settings files.
- [ ] The recommended deny rules drop the two settings rules. The person adds the rest with one typed line, `! sh "<plugin>/tools/bdd/bdd" doctor --add-deny-rules`, which merges into the project's `.claude/settings.json` and refuses when run from a tool call. `/greenlight:init` offers it once.

**You see.**

- [ ] `python -m unittest tests.test_guard -k fieldly` prints the corpus result, `allowed 145 of 145 legitimate, refused 25 of 25 harmful`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_guard.py` replays the corpus and gains settings-key cases, including the `"hooks"` spelling. Run `python -m unittest tests.test_guard tests.test_doctor -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `bdd assume FEAT-1 --text "Move the identity" --alt "copy it"` through the plugin path from a Claude session at trunk and head. Save `assume.txt`. Pass when trunk refuses and head records it.
- [ ] Lane 2. A python one-liner with `re.sub(r" .*?", ...)` on a production file. Save `regex.txt`. Pass when head allows it.
- [ ] Lane 3. Write `api/src/ports/barrier.ts` while `tests/drivers/barrier.ts` is locked. Save `same-name.txt`. Pass when head allows it.
- [ ] Lane 4. Edit the locked `tests/drivers/barrier.ts`. Save `locked.txt`. Pass when head refuses it.
- [ ] Lane 5. A reviewer runs `npx --no-install tsc --noEmit`. Save `tsc.txt`. Pass when head allows it, and `pnpm add left-pad` is still refused.
- [ ] Lane 6. Claude adds an `env` entry to `.claude/settings.json`. Save `settings-ok.txt`. Pass when it is written and no violation opens.
- [ ] Lane 7. Claude sets `"disableAllHooks": true`, then writes `"hooks": {}`. Save `settings-bad.txt`. Pass when both are refused.
- [ ] Lane 8. The person types the deny-rules line, then the model runs the same command. Save `deny.txt`. Pass when the first merges and keeps existing keys, and the second is refused.
- [ ] Lane 9. Save a memory under `~/.claude/projects/<p>/memory/`. Save `memory.txt`. Pass when it is allowed and a transcript write is refused.
- [ ] Lane 10. Run `evals/platform-probe/guard_e2e.py`. Save `guard-e2e.txt`. Pass when every check passes.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. PreToolUse hook time on the corpus commands.
- [ ] Probe. Replay the corpus through the hook at trunk and head, interleaved, three passes.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head stays under 200 ms on macOS and Linux and 300 ms on Windows per call, and adds at most 20 ms to trunk.

**Review gate.** The operator reviews before merge.

- [ ] Copy a screenshot of the corpus result and of lanes 7 and 8 into `docs/dev/review/P2-review-*.png`.
- [ ] Record a 30 to 60 second video of lanes 6 to 8. Save it as `docs/dev/review/P2-review.mp4`, kept out of the commit.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P2.

## Lock shared test plumbing once for the project (P3)

**Depends on.** P2.

**Files.**

- [ ] Edit `tools/bdd/bddlib/lockfile.py`, `tools/bdd/bddlib/lockcmd.py`, `tools/bdd/bddlib/gates.py`, `tools/bdd/bddlib/changecmd.py`, `phases/bind.md`, `skills/change/SKILL.md`.
- [ ] Create `specs/features/shared-plumbing.feature` (FEAT-111).
- [ ] Edit `tools/bdd/tests/test_lockfile.py`, `docs/dev/decisions.md` (D65), `CHANGELOG.md`.

**Build.**

- [ ] A project-level lock in `.bdd/plumbing.lock.json` covers the shared drivers, support and runner settings. A feature's bind lock covers its own step and driver files and records the plumbing lock's digest.
- [ ] A file added to a bound folder by another feature is that feature's file, not a violation of this one.
- [ ] Changing shared plumbing is its own change, `bdd lock --plumbing`, after which every feature reruns its scenarios once. No feature is reopened to bind.

**You see.**

- [ ] With FEAT-1 done, binding FEAT-2 with a new driver leaves `bdd lock FEAT-1 --check --require` clean.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_lockfile.py` gains own-files, other-feature-file, plumbing-change and migration-from-old-lock cases. Run `python -m unittest tests.test_lockfile -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Bind FEAT-2 with a new driver while FEAT-1 is done, at trunk and head. Save `two-features.txt`. Pass when trunk reports FEAT-1's lock incomplete and head does not.
- [ ] Lane 2. Change a shared support file through `bdd lock --plumbing`. Save `plumbing.txt`. Pass when both features rerun and neither is reopened.
- [ ] Lane 3. Change a shared file without it. Save `plumbing-bad.txt`. Pass when every feature's gate refuses.
- [ ] Lane 4. Edit FEAT-1's own step file. Save `own.txt`. Pass when only FEAT-1 refuses.
- [ ] Lane 5. A project locked by trunk. Save `migrate.txt`. Pass when `bdd migrate` converts it and every check stays clean.
- [ ] Lane 6. Run CI's `bdd lock --check --require` on both features. Save `ci.txt`. Pass when both pass.
- [ ] Lane 7. Three features bound in turn. Save `three.txt`. Pass when no feature is reopened.
- [ ] Lane 8. `/greenlight:change` on FEAT-2's examples. Save `change.txt`. Pass when FEAT-1 is untouched.
- [ ] Lane 9. `bdd status`. Save `status.txt`. Pass when the plumbing lock is shown once.
- [ ] Lane 10. The guard on a write to a plumbing file by the implementer. Save `guard.txt`. Pass when it is refused as locked by the project.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `bdd lock FEAT-1 --check --require` time with three features.
- [ ] Probe. 20 runs at trunk and head, interleaved.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head is no slower than trunk plus 50 ms.

**Review gate.** None. P3 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P3.

## Move the checks the auditor makes by rule into earlier gates (P4)

**Depends on.** P3.

**Files.**

- [ ] Edit `tools/bdd/bddlib/lint.py`, `tools/bdd/bddlib/classify.py`, `tools/bdd/bddlib/route.py`, `tools/bdd/bddlib/gates.py`, `phases/test-design.md`, `review/checklist.md`.
- [ ] Create `specs/features/earlier-checks.feature` (FEAT-112).
- [ ] Edit the matching tests, `docs/dev/decisions.md` (D66), `CHANGELOG.md`.

**Build.**

- [ ] `bdd lint` refuses entity tables of one entity with different column sets within a feature.
- [ ] `bdd classify` flags a scenario tagged `@existing` that failed in the red run.
- [ ] The implement gate refuses a review older than the production files of its task, by hash.
- [ ] The test-design gate checks that each rule using a boundary card has the card's listed edges (first, last, one past, empty, maximum length, leap day for dates).

**You see.**

- [ ] `bdd lint` prints `EX-1.2.1: company table has columns name, phone; EX-1.1.1 has name; check one column set per entity` and exits 1.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] One test file per check gains its passing and failing cases. Run `python -m unittest tests.test_lint tests.test_run_classify tests.test_route -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Lint Fieldly's FEAT-001 examples before CR-001.2 at trunk and head. Save `columns.txt`. Pass when trunk is clean and head reports the mixed column sets.
- [ ] Lane 2. An `@existing` scenario that fails red. Save `existing.txt`. Pass when classify flags it.
- [ ] Lane 3. A review written, then a production edit. Save `stale-review.txt`. Pass when the implement gate refuses.
- [ ] Lane 4. A review rewritten after the edit. Save `fresh-review.txt`. Pass when the gate passes.
- [ ] Lane 5. A date rule using the boundary card with no leap day. Save `leap.txt`. Pass when the test-design gate refuses.
- [ ] Lane 6. A text rule with no maximum-length example. Save `length.txt`. Pass when it is refused.
- [ ] Lane 7. A paging rule with no page size 1. Save `paging.txt`. Pass when it is refused.
- [ ] Lane 8. A complete test design. Save `ok.txt`. Pass when every gate passes.
- [ ] Lane 9. The auditor on a feature that passed these gates. Save `audit.txt`. Pass when its checklist marks those items as checked by the CLI.
- [ ] Lane 10. Replay Fieldly's 15 change requests' causes. Save `fieldly-crs.txt`. Pass when at least 6 are caught by a gate before verify.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `bdd lint` time on a 2,000-line feature file.
- [ ] Probe. 20 runs at trunk and head, interleaved.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head is no slower than trunk plus 200 ms.

**Review gate.** None. P4 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P4.

## Make approvals something a person can read and give in one step (P5)

**Depends on.** P4.

**Files.**

- [ ] Edit `tools/bdd/bddlib/approvehook.py`, `tools/bdd/bddlib/approvals.py`, `tools/bdd/bddlib/htmlreport.py`, `skills/feature/SKILL.md`, `skills/approve/SKILL.md`, `skills/change/SKILL.md`.
- [ ] Create `specs/features/approval-summary.feature` (FEAT-113).
- [ ] Edit the matching tests, `docs/dev/decisions.md` (D67), `CHANGELOG.md`.

**Build.**

- [ ] Before asking, the orchestrator runs `bdd approve FEAT-n rules|examples --summary`, which prints the rules in plain words and, after a change, only what changed since the last approval. The HTML report shows the same.
- [ ] A message that holds an approval command plus other text, or two commands, is refused with `NOT recorded: send one approval per message`.
- [ ] When the latest approval cannot be verified, the newest verified approval for the same artifact hashes counts.

**You see.**

- [ ] `bdd approve FEAT-1 examples --summary` after a change prints `2 scenarios changed, 1 added` with each in plain words.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_approvals.py` gains summary, near-miss and fallback cases. Run `python -m unittest tests.test_approvals -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Type an approval plus a sentence in one message at trunk and head. Save `near-miss.txt`. Pass when trunk says nothing and head prints the refusal.
- [ ] Lane 2. A first approval. Save `summary-first.png`. Pass when the summary lists every rule in plain words.
- [ ] Lane 3. An approval after a change. Save `summary-change.png`. Pass when only the changes are listed.
- [ ] Lane 4. An unverifiable approval after a verified one. Save `fallback.txt`. Pass when the bind gate passes on the verified one.
- [ ] Lane 5. A changed artifact after a verified approval. Save `stale.txt`. Pass when the fallback does not apply.
- [ ] Lane 6. The HTML report. Save `report.png`. Pass when the summary is shown.
- [ ] Lane 7. A reject with a reason. Save `reject.txt`. Pass when it is recorded.
- [ ] Lane 8. The model tries `--summary --record`. Save `agent.txt`. Pass when nothing is recorded.
- [ ] Lane 9. A Chinese feature file. Save `zh.png`. Pass when the summary keeps the language.
- [ ] Lane 10. `/greenlight:status FEAT-1`. Save `status.txt`. Pass when it names what is waiting for approval.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. UserPromptSubmit hook time on an approval.
- [ ] Probe. 20 approvals at trunk and head, interleaved.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head stays under 300 ms on Windows and adds at most 20 ms.

**Review gate.** The operator reviews before merge.

- [ ] Copy lanes 2, 3 and 6 screenshots into `docs/dev/review/P5-review-*.png`.
- [ ] Record a 30 to 60 second video of an approval with the summary. Save it as `docs/dev/review/P5-review.mp4`, kept out of the commit.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P5.

## Give agents the tools they need and record costs truthfully (P6)

**Depends on.** P5.

**Files.**

- [ ] Edit `agents/qa-designer.md`, `agents/product-analyst.md`, `agents/system-analyst.md`, `tools/bdd/bddlib/agentcost.py`, `tools/bdd/bddlib/statecmd.py`, `tools/bdd/bddlib/config.py`, `tools/bdd/bddlib/statecmd.py`, `skills/feature/SKILL.md`.
- [ ] Create `specs/features/costs-and-models.feature` (FEAT-114).
- [ ] Edit the matching tests, `docs/dev/decisions.md` (D68), `CHANGELOG.md`.

**Build.**

- [ ] The three spec agents get the Edit tool. The guard keeps limiting which files they write.
- [ ] `bdd cost --collect` attributes an agent to the feature named in its prompt or description, so several features in progress work.
- [ ] `bdd cost --amend <entry> --reason "..."` corrects an entry and keeps the original.
- [ ] The report shows the orchestrator session's tokens next to the agents', labelled as Claude Code's own figure.
- [ ] `[models]` in `.bdd/config.toml` names a model per agent, and `bdd status` shows them. The orchestrator passes the model on each Agent call.

**You see.**

- [ ] `bdd status` prints `models: implementer sonnet, code-reviewer opus` and the cost lines for three features in progress.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_agentcost.py` and `test_config.py` gain attribution, amend and models cases. Run `python -m unittest tests.test_agentcost tests.test_config -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. `bdd cost --collect` with two features in progress at trunk and head. Save `collect.txt`. Pass when trunk attributes nothing and head attributes each agent.
- [ ] Lane 2. The qa-designer changes one scenario. Save `edit.txt`. Pass when it uses Edit and the rest of the file is byte-identical.
- [ ] Lane 3. The qa-designer edits a production file. Save `edit-guard.txt`. Pass when it is refused.
- [ ] Lane 4. Amend a wrong entry. Save `amend.txt`. Pass when the total changes and the original is kept.
- [ ] Lane 5. Set `[models] implementer = "opus"` and run a task. Save `model.txt`. Pass when the agent ran on that model.
- [ ] Lane 6. The HTML report. Save `cost.png`. Pass when both figures are shown and labelled.
- [ ] Lane 7. A Unicode escape in a feature edited by the qa-designer. Save `unicode.txt`. Pass when it is kept.
- [ ] Lane 8. An unknown model name. Save `bad-model.txt`. Pass when `bdd doctor` reports it.
- [ ] Lane 9. `bdd status` with no `[models]`. Save `default.txt`. Pass when the defaults from the agent files are shown.
- [ ] Lane 10. Run `login-return` end to end. Save `e2e.txt`. Pass when every agent's cost is attributed.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Tokens of the examples phase for a one-scenario change.
- [ ] Probe. One change request on the same feature at trunk and head.
- [ ] Baseline. Record the trunk tokens first.
- [ ] Rule. Head uses at most half of trunk's tokens.

**Review gate.** None. P6 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P6.

## Make the README and the docs match the code (P7)

**Depends on.** P6, so the docs describe P1 to P6.

**Files.**

- [ ] Edit `README.md`, `docs/quickstart.md`, `docs/troubleshooting.md`, `docs/upgrading.md`, `docs/adapters.md`.
- [ ] Create `tools/bdd/tests/test_readme.py`.
- [ ] Edit `adapters/ts-cucumber-js/adapter.toml` comments, `tools/bdd/bddlib/doctor.py`, `CHANGELOG.md`.

**Build.**

- [ ] Apply every wrong or outdated row of the two README audits of 2026-11-08 (pipeline diagram, phase list, auditor and `report.md`, `bdd check` needs configured tools, PASS meaning, CI workflow copy, Node 26 and JDK 25, seven to nine adapters, helper plugin names and ids, writers only for context7, guided stops, Windows claims).
- [ ] Add what a newcomer needs and the audits found missing. These are how to run `bdd` by its path, the deny-rules line, doctor's first-run warnings, `/greenlight:status`, `--quick`, the HTML report, mid-run autonomy switches, `FEAT-001` ids, uninstalling Codex hooks.
- [ ] `docs/upgrading.md` gains "Upgrading with features in progress", what a new version reopens and how.
- [ ] Commands the person runs are printed for the detected shell, quoted, with forward slashes. Doctor stops warning about Codex where Codex is not installed.
- [ ] `test_readme.py` fails when a README or quickstart command or flag is missing from `--help`, a relative link has no target, or a stated count differs from the files.

**You see.**

- [ ] `python -m unittest tests.test_readme -v` passes, and fails on a scratch copy with one misspelled command.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_readme.py` gains one case per check. Run `python -m unittest tests.test_readme -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Follow `docs/quickstart.md` step by step at trunk and head. Save `quickstart.txt`. Pass when head runs every step as written and trunk's first wrong step is recorded.
- [ ] Lane 2. Run every fenced command in README "See it work" and "Use". Save `commands.txt`. Pass when each prints what the README shows.
- [ ] Lane 3. Check every slash command against `skills/*/SKILL.md`. Save `skills.txt`. Pass when each exists.
- [ ] Lane 4. Check every helper plugin id against `bdd helpers`. Save `helpers.txt`. Pass when they agree.
- [ ] Lane 5. Check the phase list and diagram against `bddlib/state.py`. Save `phases.txt`. Pass when they agree.
- [ ] Lane 6. Check the agent list against `agents/*.md`. Save `roles.txt`. Pass when every agent is named once.
- [ ] Lane 7. Check every known limit against the code and decisions. Save `limits.txt`. Pass when each holds.
- [ ] Lane 8. Resolve every relative link and anchor. Save `links.txt`. Pass when none is broken.
- [ ] Lane 9. Follow "Upgrading with features in progress" from 1.2.1 to head on a project with a feature in implement. Save `upgrade.txt`. Pass when no step asks for a JSON edit.
- [ ] Lane 10. Doctor on a machine without Codex. Save `doctor.txt`. Pass when no Codex warning is printed.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of the unit suite in `tools/bdd`.
- [ ] Probe. The full suite at trunk and head, interleaved three times.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head adds at most 5 seconds.

**Review gate.** None. P7 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P7.

## Make init record the project's sources, quality tools and screens (P8)

**Depends on.** P7.

**Files.**

- [ ] Edit `tools/bdd/bddlib/initcmd.py`, `tools/bdd/bddlib/config.py`, `tools/bdd/bddlib/doctor.py`, `skills/init/SKILL.md`, `templates/standards.md`.
- [ ] Create `tools/bdd/bddlib/sources.py` and `specs/features/init-records.feature` (FEAT-115).
- [ ] Edit the matching tests, `docs/dev/decisions.md` (D69), `README.md`, `CHANGELOG.md`.

**Build.**

- [ ] `bdd init` writes `.bdd/sources.toml` from the project's dependencies, one entry per external service or SDK with its official documentation URL, its CLI and MCP server when installed, and the version.
- [ ] `sources.toml` also records the vendor plugins and MCP servers installed for those services (Expo, Supabase, Stripe, Sentry, Cloudflare, AWS, Firebase and the like) as official sources, and `bdd helpers` suggests the vendor plugin of a service the project uses when it is not installed. Installing stays the person's typed line.
- [ ] `bdd init` fills `[adapters.quality.*]` from the detected toolchain (formatter, linter, type checker, architecture checker), in force by default.
- [ ] `bdd init` records a `[design]` table when the project has a `design/` folder with `DESIGN.md` or an inventory.
- [ ] `bdd init` lists the surfaces of the product (web, iOS, Android, API, CLI) and which adapter covers each, and records "screens unverified" when none does.

**You see.**

- [ ] `bdd init` in a Fieldly copy prints `sources: line, google, apple, supabase`, `quality: tsc, eslint, dependency-cruiser` and `mobile screens: no adapter, recorded as unverified`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_init.py` and `test_sources.py` gain detection cases per ecosystem. Run `python -m unittest tests.test_init tests.test_sources -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. `bdd init` on a Fieldly copy at trunk and head, then `bdd check`. Save `check.txt`. Pass when trunk says no check is configured and head runs the tools.
- [ ] Lane 2. A Python project. Save `python.txt`. Pass when ruff, mypy and import-linter are proposed.
- [ ] Lane 3. A Go project. Save `go.txt`. Pass when gofmt, go vet and golangci-lint are proposed.
- [ ] Lane 4. A project without a `design/` folder. Save `no-design.txt`. Pass when no `[design]` table is written.
- [ ] Lane 5. A Supabase project with the Supabase CLI installed. Save `supabase.txt`. Pass when the CLI is recorded.
- [ ] Lane 6. An Expo project. Save `expo.txt`. Pass when mobile screens are named as unverified.
- [ ] Lane 7. Re-run init. Save `rerun.txt`. Pass when nothing the person changed is overwritten.
- [ ] Lane 8. `bdd doctor`. Save `doctor.txt`. Pass when sources and quality tools are listed.
- [ ] Lane 9. An agent writes `sources.toml`. Save `guard.txt`. Pass when it is refused as person-owned.
- [ ] Lane 10. `bdd status`. Save `status.txt`. Pass when unverified surfaces are shown.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `bdd init --detect` time on a Fieldly copy.
- [ ] Probe. 10 runs at trunk and head, interleaved.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head stays under 2 seconds.

**Review gate.** None. P8 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P8.

## Add a design stage the person approves by looking (P9)

**Depends on.** P8.

**Files.**

- [ ] Create `agents/ux-designer.md`, `agents/ui-designer.md`, `phases/design.md`, `tools/bdd/bddlib/gallery.py`.
- [ ] Edit `agents/ui-reviewer.md`, `skills/init/SKILL.md`, `skills/change/SKILL.md`, `tools/bdd/bddlib/roles.py`, `tools/bdd/bddlib/guard.py`, `tools/bdd/bddlib/lockfile.py`, `tools/bdd/bddlib/approvals.py`.
- [ ] Create `specs/features/design-stage.feature` (FEAT-116).
- [ ] Edit the matching tests, `docs/dev/decisions.md` (D70), `README.md`, `CHANGELOG.md`.

**Build.**

- [ ] The stage starts from a product spec alone. `/greenlight:init --product <spec file>` turns it into `PRODUCT.md` (who uses it, their jobs, the platforms), a feature map in `.bdd/product.md` (every feature with its id, its dependencies and its build order, as Fieldly's inventory has 24), and a system architecture in `.bdd/architecture.md` decided once for the product (stack per surface, layers, hosting and environments, the authentication model, the data store, the security baseline and threat model, observability, CI and delivery). The person approves the feature map and the architecture together with the design.
- [ ] The ux-designer writes the screen inventory (id, screen, states, feature) and `flows.html`. The ui-designer writes `DESIGN.md`, `tokens.json` and `screens/*.html`. Both use impeccable's `shape`, `init`, `generate`, `document` and `polish` in design files only when it is installed, and greenlight's cards otherwise. Each has an explicit tool list and writes only under the design folder.
- [ ] The ui-reviewer reviews the design with impeccable's `audit` and the finish-gate criteria.
- [ ] `bdd gallery --out design/gallery.html` builds one page with every screen and state, the flows and the inventory grouped by feature.
- [ ] The person approves with `/greenlight:approve design`, after which the design folder is locked. A change goes through `/greenlight:change`.
- [ ] The stage runs from `/greenlight:init` for the whole project, so the number of skills stays six.

**You see.**

- [ ] `design/gallery.html` shows every inventory row as a card linking its screen, and `bdd status` prints `design: approved, locked`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_gallery.py` and `test_approvals.py` gain gallery, design approval and design lock cases. Run `python -m unittest tests.test_gallery tests.test_approvals -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `/greenlight:init` on `shop-web` at trunk and head. Save `init.txt`. Pass when trunk records no design stage and head produces the design folder and gallery.
- [ ] Lane 2. Open the gallery. Save `gallery.png`. Pass when every screen and state is shown.
- [ ] Lane 3. The same with impeccable not installed. Save `no-impeccable.png`. Pass when the design is still produced.
- [ ] Lane 4. Approve the design. Save `approve.txt`. Pass when it is locked.
- [ ] Lane 5. The implementer edits a design screen. Save `guard.txt`. Pass when it is refused.
- [ ] Lane 6. `/greenlight:change` on a screen. Save `change.txt`. Pass when the design gate reopens.
- [ ] Lane 7. The ui-reviewer's design report. Save `review.txt`. Pass when it has a verdict and evidence.
- [ ] Lane 8. A design with a screen missing a state. Save `states.txt`. Pass when the review reports it.
- [ ] Lane 9. Open each screen at 375 px and 1280 px. Save `widths.png`. Pass when both render without overflow.
- [ ] Lane 10. A Fieldly copy's existing design folder. Save `fieldly.png`. Pass when the gallery is built from it without regenerating.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `bdd gallery` time on Fieldly's 148-row inventory.
- [ ] Probe. 10 runs at head. Trunk lacks the command, so this is an absolute budget.
- [ ] Baseline. Record that trunk has no gallery.
- [ ] Rule. Head builds the gallery in under 3 seconds.

**Review gate.** The operator reviews before merge.

- [ ] Copy lanes 2, 3 and 10 screenshots into `docs/dev/review/P9-review-*.png`.
- [ ] Record a 30 to 60 second video of the gallery and the design approval. Save it as `docs/dev/review/P9-review.mp4`, kept out of the commit.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P9.

## Write and review a checked technical design before code (P10)

**Depends on.** P9.

**Files.**

- [ ] Create `cards/practices/standard-values.md`, `tools/bdd/bddlib/designsections.py`.
- [ ] Edit `templates/design.md`, `templates/system.md`, `phases/discover.md`, `phases/specify.md`, `phases/system-map.md`, `agents/product-analyst.md`, `agents/system-analyst.md`, `agents/code-reviewer.md`, `agents/security-reviewer.md`, `agents/ui-reviewer.md`, `tools/bdd/bddlib/design.py`, `tools/bdd/bddlib/docsrecord.py`, `tools/bdd/bddlib/gates.py`, `cards/index.json`, `templates/standards.md`, `skills/feature/SKILL.md`.
- [ ] Create `specs/features/technical-design.feature` (FEAT-117).
- [ ] Edit the matching tests, `docs/dev/decisions.md` (D71), `README.md`, `CHANGELOG.md`.

**Build.**

- [ ] Specify reads the inventory rows and screens of the feature. Every field, state and action becomes a rule, an example or a question.
- [ ] `design.md` has these sections, each a table `designsections.parse` reads. A section that does not apply holds one row with the reason.
  - [ ] Design trace. Each screen element to its rule, API field and component.
  - [ ] Building blocks. Each field's standard and library.
  - [ ] External services. Each SDK or API call with its evidence from `sources.toml`, its quota, cost and failure behaviour.
  - [ ] Architecture. Where each new piece lives in `.bdd/architecture.md`'s layers.
  - [ ] Patterns. The project's patterns to copy, each with an example file.
  - [ ] API contract. The schema fragment, its versioning and what older clients still get.
  - [ ] Data and performance. Tables, migrations with their rollback, an index per query, volumes, a budget per operation, caching.
  - [ ] Security and privacy. The threats of this feature (who may do what, on which object), authorisation checks on the server, input validation, secrets, personal data with its retention, rate limits.
  - [ ] Errors and resilience. Every failure the feature can meet (network, timeout, conflict, duplicate request, partial failure), what the user sees, retries and idempotency, concurrent writes.
  - [ ] State and offline. Client-side state, what is cached, what happens offline and on reconnect, background jobs and notifications.
  - [ ] Accessibility and language. Labels, focus, contrast and text size per screen, the strings to translate, locale formats for dates, numbers, money and addresses.
  - [ ] Observability. The logs, metrics and traces that show the feature works in production, with no personal data in them.
  - [ ] Configuration and delivery. New settings and secrets per environment, feature flags, the migration order on deploy.
  - [ ] Test strategy. Which levels test what (unit, contract, scenario, end to end, performance), beyond the scenarios.
- [ ] The card `standard-values` names the standard and library per kind of value. Phone is E.164 with libphonenumber and a country-code picker, country is ISO 3166-1 with names from the platform, money is ISO 4217 in minor units, time zone is IANA, address follows the country's format.
- [ ] `bdd design FEAT-n` refuses an untraced inventory row, a field with no building block, an external call without evidence from `sources.toml` (a page, an MCP lookup or a CLI run, recorded with `bdd docs`), a missing example file for a pattern, a query without an index, an operation without a budget, a migration without a rollback, an endpoint without an authorisation row, a screen without its states, and an empty section without a reason.
- [ ] A design review runs the code-reviewer, security-reviewer and ui-reviewer on `design.md` in parallel. Their must-fix items go back to the system analyst before tasks.
- [ ] A building block not installed is one install command for the person before implement.

**You see.**

- [ ] On a Fieldly copy, `bdd design FEAT-001` prints `design row O-ST-01 (Company profile) is not traced` and `field "contact phone" has no building block`, and exits 1.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_designsections.py` gains one passing and one failing case per section. Run `python -m unittest tests.test_designsections -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. The system-map gate on a feature with a phone field and an inventory row, at trunk and head. Save `gate.txt`. Pass when trunk records that it lacks the checks and head refuses both gaps.
- [ ] Lane 2. A complete design. Save `ok.txt`. Pass when the gate passes.
- [ ] Lane 3. An external call whose source is `package.json`. Save `source.txt`. Pass when it is refused.
- [ ] Lane 4. A query without an index. Save `index.txt`. Pass when it is refused.
- [ ] Lane 5. The design review on a sign-in design with no rate limit. Save `review.txt`. Pass when the security-reviewer reports it.
- [ ] Lane 6. A building block not installed. Save `install.txt`. Pass when the implement gate prints the install command and the guard still refuses the agent's install.
- [ ] Lane 7. A feature with no data fields. Save `empty.txt`. Pass when an empty table with a reason passes.
- [ ] Lane 8. `bdd report FEAT-1`. Save `report.png`. Pass when the seven sections are shown.
- [ ] Lane 9. Run a new request `profile-phone` on `shop-web` end to end at head. Save `e2e.txt` and the diff. Pass when the diff stores E.164, uses a phone library and the platform's country names, and every inventory field is built.
- [ ] Lane 10. The same request at trunk. Save `e2e-trunk.txt`. Pass when its result is recorded for comparison.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Total time from request to a green audited feature on `profile-phone`, and the number of audit rounds.
- [ ] Probe. Lanes 9 and 10, one run each.
- [ ] Baseline. Record the trunk run first.
- [ ] Rule. Head needs no more audit rounds than trunk, and takes at most 20% longer in total.

**Review gate.** The operator reviews before merge.

- [ ] Copy lanes 1, 5 and 9 screenshots into `docs/dev/review/P10-review-*.png`.
- [ ] Record a 30 to 60 second video of lanes 1 and 9. Save it as `docs/dev/review/P10-review.mp4`, kept out of the commit.
- [ ] Post the screenshots, the video and the card in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P10.

## Implement against the design with known risks and parallel reviews (P11)

**Depends on.** P10.

**Files.**

- [ ] Edit `templates/tasks.md`, `phases/tasks.md`, `phases/implement.md`, `agents/implementer.md`, `agents/ui-engineer.md`, `agents/code-reviewer.md`, `agents/ui-reviewer.md`, `tools/bdd/bddlib/route.py`, `tools/bdd/bddlib/trace.py`, `cards/practices/pre-mortem.md`, `skills/feature/SKILL.md`.
- [ ] Create `specs/features/task-risks.feature` (FEAT-118).
- [ ] Edit `tools/bdd/tests/test_route.py`, `docs/dev/decisions.md` (D72), `README.md`, `CHANGELOG.md`.

**Build.**

- [ ] Each task names its design sections and a `Risks:` line from a fixed list (concurrent writes, retries, rate limits, unmapped storage errors, authorisation, personal data, time zones, large lists), derived by `bdd route` and extendable by the orchestrator.
- [ ] The writer gets its sections, building blocks and sources, and checks each external call with the MCP or CLI that `sources.toml` names.
- [ ] `bdd check` runs the quality tools after each task, the architecture checker included.
- [ ] A task's reviewers start together, capped at three at once. The next independent task's writer may start while they run.
- [ ] The ui-reviewer opens the built screen and the design screen side by side in the browser and reports differences in layout, tokens and states.
- [ ] The code-reviewer's report has one line per listed risk.

**You see.**

- [ ] `bdd route FEAT-1` on a sign-in task prints `risks: concurrent writes, rate limits, authorisation` and `design: Architecture, External services`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tools/bdd/tests/test_route.py` gains risk derivation, unknown risk word and review-line cases. Run `python -m unittest tests.test_route -v` in `tools/bdd`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. `bdd route FEAT-1` on a sign-in task at trunk and head. Save `route.txt`. Pass when trunk lists no risks and head lists them.
- [ ] Lane 2. A code-review report without a line for a listed risk. Save `review.txt`. Pass when the implement gate refuses it.
- [ ] Lane 3. The ui-reviewer on a screen that differs from its design. Save `compare.png`. Pass when the difference is reported with both screenshots.
- [ ] Lane 4. `bdd check` after a task that imports the infrastructure layer from the domain. Save `arch.txt`. Pass when the architecture checker fails it.
- [ ] Lane 5. Run `login-return` end to end at head. Save `e2e-head.txt`. Pass when it passes and records implement seconds.
- [ ] Lane 6. The same at trunk. Save `e2e-trunk.txt`. Pass when its seconds are recorded.
- [ ] Lane 7. The orchestrator log of lane 5. Save `parallel.txt`. Pass when one task's reviewers started within a minute of each other and never more than three ran.
- [ ] Lane 8. Dependent tasks. Save `deps.txt`. Pass when no dependent writer starts before its parent's reviews pass.
- [ ] Lane 9. A writer calling an SDK listed in `sources.toml`. Save `sdk.txt`. Pass when its docs record names the official page or the MCP lookup.
- [ ] Lane 10. An old `tasks.md` without `Risks:` lines. Save `old.txt`. Pass when it still works and the missing lines are reported once.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Implement-phase seconds and audit rounds on `login-return`.
- [ ] Probe. Lanes 5 and 6, one run each.
- [ ] Baseline. Record the trunk run first.
- [ ] Rule. Head takes no more implement seconds than trunk plus 10%, and needs no more audit rounds.

**Review gate.** The operator reviews before merge.

- [ ] Copy lanes 1, 3 and 7 screenshots into `docs/dev/review/P11-review-*.png`.
- [ ] Record a 30 to 60 second video of lane 3. Save it as `docs/dev/review/P11-review.mp4`, kept out of the commit.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The operator squash-merges P11.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the report the execution playbook names.

## Appendix A. Prototype evidence

No prototype ran yet. The evidence is the Fieldly run, read on 2026-11-08 from its `.bdd` records and its 59 session transcripts. All 170 guard refusals were rebuilt and replayed through the 1.2.1 guard, which still refuses every one. About 145 of them were legitimate work. The integrity file holds 151 violations, 143 caused by plugin updates, and 147 were closed by hand-editing the file. The three features had 15 change requests, 8 of them bind reworks caused by shared drivers and 10 raised by the system analyst or the auditor. The person typed 71 messages, 21 of them approvals. The phone field is free text of up to 40 characters, and inventory row O-ST-01 lists fields the API did not build. Two questions stay unproven until P10 lanes 9 and 10 run. Whether a model follows the design sections without more prompting is one. Whether the design stage changes the code a model writes is the other.

## Appendix B. Alternatives rejected

Copying The Agency's four design agents was rejected, because they have no tool lists or output files and overlap with impeccable. Letting writers add dependencies was rejected, because installs stay the person's act. Dropping the guard's shell checks was rejected, because they still stop real harm in the corpus. P2 makes them precise instead. A per-language import checker for hand-rolled code was rejected for the reason D61 gives. A seventh skill for the design stage was rejected, because the project allows six. Locking the whole settings file was rejected at the operator's request, because it blocks ordinary edits.

## Appendix C. Risks

P2 loosens a protection. The corpus labels decide what is legitimate, and the operator reviews them before the code. P3 changes the lock format. `bdd migrate` must convert old locks, and P3 lane 5 gates it. P9 adds the largest new surface, two agents, a phase, a gallery and a design lock. P10's card can age, and each row names its source for the weekly pins report to check later. P11's parallel reviewers raise peak memory, the cause of the killed evaluation runs on 2026-11-05, so they are capped at three. End-to-end lanes cost money and can be killed by memory pressure. An owner reports a killed lane and retries it at most once.

## Appendix D. Plugins each stage uses when installed

Every stage works without any of these, with greenlight's cards and agents alone. When one is installed, the stage uses it as follows, and the agent's tool list and playbook name it.

| Stage | Plugins and what for |
|---|---|
| Product and architecture (P9) | `feature-dev` code-architect and code-explorer for the architecture of an existing code base; context7 and microsoft-docs for the stack's current documentation; the vendor plugins for the services the spec names |
| Design (P9) | impeccable `shape`, `init`, `generate`, `document`, `polish` on design files, its finish-reviewer for the review; `frontend-design` for the visual direction; figma when the person has a Figma file; chrome-devtools-mcp for screenshots of every screen and width |
| Technical design (P10) | context7, microsoft-docs and the vendor MCP servers (Supabase, Stripe, Expo, Cloudflare, AWS, Sentry and the like) for each external call, recorded with `bdd docs`; the vendor CLIs named in `sources.toml` |
| Design review (P10) | pstack `thermos` and `interrogate` for the code-reviewer; the security-guidance plugin's rules for the security-reviewer; impeccable `audit` for the ui-reviewer |
| Implement (P11) | context7, microsoft-docs and the vendor MCP servers for the writers; frontend-design and figma for the ui-engineer |
| Code review (P11) | code-metrics and api-drift-detector for the code-reviewer; open-code-review's `ocr review`; chrome-devtools-mcp and impeccable `audit` for the ui-reviewer's side-by-side check |

The helper catalog (`bddlib/helpers.py`) today lists only plugins from Anthropic's directories, which is why impeccable, pstack and open-code-review are never offered. P8 adds them as optional entries that name their own marketplace, so the person sees where each comes from before typing the install line.

## Appendix E. Links and reading list

Before editing, read `docs/dev/decisions.md` D11, D15, D30, D37, D57 to D62, `phases/`, `agents/`, `tools/bdd/bddlib/guard.py`, `tripwire.py`, `lockfile.py`, `route.py`, `approvals.py`, `docsrecord.py` and `design.py`. P1, P2, P3, P9 and P10 get `skills/how/SKILL.md` before code, and P2, P9 and P10 get `skills/interrogate/SKILL.md` before merge. The decision trail is kept per `skills/show-me-your-work/SKILL.md` in the program store.
