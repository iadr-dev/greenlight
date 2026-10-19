---
name: approve
description: Approve or reject the rules or the examples of a feature. Only the person can run this by typing /greenlight:approve FEAT-n rules|examples (add "reject <reason>" to reject); the AI never invokes it.
disable-model-invocation: true
---

# greenlight approve

The person typed `/greenlight:approve $ARGUMENTS`.

The approval itself is recorded by a hook before you see this prompt, from exactly what the person
typed. You do not record it and you cannot: never run `bdd approve ... --self-reported` or `--auto`
to stand in for the person when the hook has run.

1. Look for a line starting with `greenlight approval:` in the context of this prompt.
   - If it says the approval was recorded, run the check below and tell the person the result.
   - If it says `NOT recorded`, repeat its reason and what has to happen first. Do not retry.
2. Check where the feature stands and show the output unchanged:

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" approve <FEAT-n> --verify
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" state show <FEAT-n>
   ```

   An approval shows `pending` until Claude Code has written the person's prompt to the session
   transcript; run the check again after the next turn if it does. An approval that is `invalid`
   or `unverifiable` does not count: tell the person to type the command again themselves.
3. If there is **no** `greenlight approval:` line at all, hooks are not active in this session.
   Say so. In a project that allows it (`enforcement = "soft"`, or hooks never having run), ask the
   person to confirm in plain words, and only then record their answer with
   `bdd approve <FEAT-n> <gate> --self-reported`. The command refuses when the project requires
   hard enforcement; relay that refusal and do not look for another way.
