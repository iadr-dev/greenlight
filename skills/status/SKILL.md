---
name: status
description: Show where every greenlight feature stands, what each is waiting for, and anything that needs attention. Use when the user runs /greenlight:status or asks what is in progress, blocked, or waiting for approval.
argument-hint: '[FEAT-n]'
---

# greenlight status

Everything here is computed by the tool; do not infer state from the conversation.

1. Run, and show the output unchanged:

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" status
   ```

   If the arguments name a feature (`$ARGUMENTS`), also run `bdd state show FEAT-n` and `bdd trace FEAT-n`.

2. Then say in a few lines, in plain words:
   - which feature needs the person next, and the exact line to type if it is waiting for an approval
     (`/greenlight:approve FEAT-n rules` or `examples`);
   - anything blocked: a failed gate, an approval marked "not valid" (changed after approval or revoked by a change),
     an open integrity violation and which file it names;
   - anything unreviewed (autopilot) or soft (hooks were not active), and why.

3. Do not change anything. Offer `/greenlight:feature FEAT-n` to continue a feature, or `/greenlight:change` if an
   approved item has to change.
