# P1 (tripwire) independent review, 2026-11-09

Reviewer read `git diff fea8da7..HEAD` of the P1 worktree (`.claude/worktrees/agent-a56bb78df804ee27a`, branch `worktree-agent-a56bb78df804ee27a`) and reproduced B1, B2, S1 and S2 with scratch probes. `tests.test_tripwire` and `tests.test_approvehook` pass (57 tests). No lock deadlock found. The P1 owner was stopped before it applied the earlier two security findings fully, so re-check what is already done.

## Blocking
- **B1.** An agent edit of a file whose earlier change is already open as `before_call` is never reported, and the next prompt accepts it (`tripwire.py` around 413, 466 `_take_seen_first`, 484 `_take`). Fix: store `seen_digest` when the `before_call` finding is made; on each check, if the current digest differs, clear `before_call` or open a new violation; at the prompt accept `seen_digest`, not the current digest.
- **B2.** An edit made inside a still-running call is dated as the person's when another call sees it first (`tripwire.py` around 382 and 422 `_dated`; `call_start` is computed after the lock wait). Fix: PreToolUse records `{tool_use_id: start}` in `.bdd/.integrity/calls.json`; PostToolUse removes its own entry only after a successful check; grant `before_call` only if `changed_at` is earlier than the start of every call still listed; expire stale entries after a long timeout. This also removes the dependence on `duration_ms` and `HOOK_DELAY`.

## Should fix
- **S1.** The plugin-update rule trusts any new folder with a new version; `installed_plugins.json` and `known_marketplaces.json` are not watched. Fix: watch them, accept an update only when the new root is under `claudepaths.config_dir()/plugins/cache/`, keep a separate plugin record per host (Claude Code, Codex).
- **S2.** A failure in `settle_held` (malformed `acknowledgements.json`, `OSError` on the transcript) aborts the comparison and the gates pass. Fix: run `settle_held` in its own try, always run `_check`, turn unreadable acknowledgements or baseline into a `corrupt` finding.
- **S3.** `before_call` depends on `duration_ms`, never seen in a live payload (P44). Fix: capture a PostToolUse payload in `evals/platform-probe/probe.py`, or adopt B2's registry.
- **S4.** In Codex the model is told to type a command Codex does not offer. Fix: `run_accept(root, offer_ack=False)` from `codexhook`.

## Nits
- N1 `approvehook.acknowledge` does not catch KeyError, TypeError, ValueError from a malformed `violations.json`.
- N2 A pending acknowledgement re-reads the whole transcript on every check; skip when size/mtime are unchanged, write only when a verdict changes.
- N3 A late "whole" acknowledgement can roll the baseline back; merge only covered paths or compare with the baseline's `taken_at`.
- N4 `bdd init` takes a baseline when both copies are missing; name it in D63's residuals.
- N5 A migrated old baseline has no `taken_at`; document it.
