---
name: change
description: Change something that was already approved or locked - a rule, an example, a step or the code - without breaking the audit trail. Use when the user runs /greenlight:change FEAT-n "<what changes>" or when an agent returns a change request.
argument-hint: 'FEAT-n "<what changes and why>"'
---

# greenlight change

A feature whose rules or examples are approved, or whose steps are bound, cannot simply be edited: the locks, the
approvals and the recorded red would all be wrong. This flow reopens the feature at the right phase, redoes only
what the change touches, and leaves the history intact.

The person decides what changes. Never reopen the specification because an agent asked: an agent only
*proposes*, in a change request (`templates/change-requests.md`).

1. **Understand the change.** Take the person's words (`$ARGUMENTS`) or the change request the agent returned.
   Read the feature's `brief.md`, `rules.md`, `test-design.md` and feature files, then run:

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" trace FEAT-n
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" status
   ```

   List what the change touches by id: rules, examples, scenarios, tasks, and whether the steps or drivers
   (bound files) or the system map are affected.

2. **Choose where to reopen**, the earliest phase that has to be redone:

   | The change is to | Reopen at |
   |---|---|
   | what the feature is for, or a rule | `specify` (or `discover` if the problem itself changed) |
   | an example or a scenario's wording | `examples` |
   | the interfaces the steps use | `system-map` |
   | a step, a driver or a seam of the adapter | `bind` |
   | the order or split of the work | `tasks` |
   | production code only | `implement` |

3. **Show the person the consequences and ask for a clear yes**, in plain words: which locks are released, which
   approvals they will have to give again (reopening `specify` revokes the rules and the examples; `examples`
   revokes the examples), which gate results are forgotten, and which ids are affected. Do not go on without
   the yes. Under `auto` and `autopilot` the approvals are recorded by the orchestrator as automatic, but a
   change to the specification is still shown first.

4. **Reopen.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" change FEAT-n --reopen PHASE --reason "<the person's words>"
   ```

   Show its output unchanged. Write the request in `change-requests.md` with its status.

5. **Redo the phases from there**, for the affected items only, following the playbooks in `phases/` with the
   same agents and the same gates. Give each agent the old and the new wording. At every human gate show the
   difference between the old and the new rules or scenarios, and let the person approve again with
   `/greenlight:approve FEAT-n rules` or `examples`. Approving the examples locks the new text.

6. **Run the checks again.** The red gate again after a rebind (`bdd run`, `bdd classify --expect red`, lock the
   bound files, `bdd gate FEAT-n bind --result pass --record-red`), and `bdd run` and the green check after the
   code. The auditor's report will list the change and the unlocks it finds in the lock history.
   If the production code was already written when the feature was reopened, a plain `bdd run` passes and is no red.
   Use `bdd run FEAT-n --against-red` instead: it runs today's tests in a temporary worktree of the production source
   the first red was proven on, and the bind gate accepts that run. Never stash, revert or hide the code to get a red,
   and never tag a scenario `@existing` that the feature's code made pass.

Never edit a locked file by any other route, never unlock with `bdd unlock` directly, and never remove an old
approval or a gate result by hand: this command is the one sanctioned way.
