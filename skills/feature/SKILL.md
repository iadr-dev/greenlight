---
name: feature
description: Build a feature from request to verified code under greenlight's gates - rules and examples the person approves, red tests, then green code. Use when the user runs /greenlight:feature "<what they want>", continues a feature with /greenlight:feature FEAT-n, or asks to build something with greenlight.
argument-hint: '"<what you want>" [--autonomy guided|standard|auto|autopilot] [--quick] | FEAT-n [--phase PHASE]'
---

# greenlight feature (the orchestrator)

You run in the main session. You drive the phases, you talk to the person, and you are the only one who records
anything. The phase agents (subagents) cannot ask the person, and they report instead of recording. Everything
you need is in files: never rely on what was said earlier in the chat.

Arguments: `$ARGUMENTS`

## 0. Before anything

- The project must be set up (`.bdd/config.toml` exists). If not, tell the person to run `/greenlight:init` and stop.
- Run `"${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" status` to see what is in progress.
  If the arguments name a `FEAT-n`, continue that feature from its current phase (step 3). Otherwise it is a new
  request.
- `--phase PHASE FEAT-n` runs a single phase (for debugging); `--quick` uses `phases/quick.md`.

## 1. Settle the autonomy level (once, before discover)

1. If the person named a level, use it. Otherwise do a small read-only look at the request and the repository
   (size, risk such as money, authorisation or personal data, whether `.bdd/glossary.md` covers the domain),
   recommend one level with the reason and ask once: "I recommend `standard` because ... Continue with it?"
2. Levels: `guided` asks at every human gate and after test design; `standard` asks for the rules and the
   examples; `auto` records those two approvals itself but still asks the blocking questions; `autopilot` also
   answers the blocking questions, recording each answer as an assumption. Machine gates (lint, red, green,
   locks) are never skipped at any level.
3. If the person later says "you decide" or "skip the questions", switch from that phase on:
   `bdd mode FEAT-n --switch autopilot --reason "<their exact words>"`. Approvals already given stay human.

## 2. Create the feature

```sh
"${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" state next-id
"${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" state init FEAT-n --title "<short title>" --autonomy LEVEL
```

The feature directory is `.bdd/features/FEAT-n-slug/`. Write the person's request word for word into the task you
give the first agent.

## 3. The loop

Read where the feature stands (`bdd state show FEAT-n --json`: its `phase`) and run that phase. For each phase
start the agent with the Agent tool, `subagent_type` `greenlight:<agent>`, and a task that contains: the feature id
and directory, the path of the playbook (`${CLAUDE_PLUGIN_ROOT}/phases/<phase>.md`, resolved to a real path), the
person's request and every answer given so far, the adapter in use, and anything the previous agent returned that
this one needs. Tell it to read the playbook first.

| Phase | Agent | After the agent returns, you check | Then you record |
|---|---|---|---|
| discover | product-analyst | the brief has no `[blocking]` question left | `bdd assume` for each assumption; `bdd gate FEAT-n discover --result pass` |
| specify | product-analyst | `rules.md` exists with `R-` lines | **human gate: rules** (step 4) |
| test-design | qa-designer | `bdd trace FEAT-n` shows no `T001` | `bdd gate FEAT-n test-design --result pass` |
| examples | qa-designer | `bdd lint` clean, `bdd trace` no gaps | **human gate: examples** (step 4) |
| system-map | system-analyst | every step mapped, or listed as a seam | `bdd gate FEAT-n system-map --result pass` |
| refine | step-engineer | `bdd lint` clean | `bdd gate FEAT-n refine --result pass` |
| bind | step-engineer | `bdd run FEAT-n`, `bdd classify FEAT-n --expect red`, `bdd scan FEAT-n` | `bdd lock FEAT-n --scope bind --bound`; `bdd gate FEAT-n bind --result pass --record-red` |
| tasks | you | write `tasks.md` from `templates/tasks.md`; `bdd trace` shows no `T005` or `T006` | `bdd gate FEAT-n tasks --result pass` |
| implement | implementer, one task at a time | `bdd run FEAT-n`, `bdd classify`, `bdd lock FEAT-n --check --require`, `bdd status` | `bdd gate FEAT-n implement --result pass` |
| verify | spec-auditor | the report has evidence on every line | write the returned report to `report.md`; `bdd gate FEAT-n verify --result pass` only if the verdict is PASS (see Findings below) |

Rules for the loop:

- **Run the checks yourself.** An agent's claim that a check passed is not evidence; the gate command and the
  commands in the table are. If a gate refuses, read its message, fix the cause or send the agent back with the
  message, and do not look for another way. Give each phase at most three attempts, then stop and tell the person
  what is stuck.
- **Record from the report**: costs with `bdd cost FEAT-n --phase P --tokens N --seconds S` (use the usage the
  agent run reports), assumptions with `bdd assume FEAT-n --text ... --rationale ... --alt ...`.
- **Questions**: an agent returns blocking questions; you ask the person one at a time with the recommended
  answer, then run the agent again with the answers. Under `autopilot` you answer the most conservative way,
  record it as an assumption, and say so in the report.
- **Change requests**: when an agent says a locked file would have to change, do not let it. Under `guided` and
  `standard` show the person the request and, if they agree, follow the `change` skill (`/greenlight:change`).
  Under `auto` and `autopilot` there may be nobody to ask: follow the `change` skill yourself for a request that
  does not alter what the person asked for (for example tagging scenarios that describe behaviour the system
  already has with `@existing`), record it as an assumption, and say so in the report. A request that would
  change what the person asked for, or touch money, authorisation, personal data or data loss, is listed
  prominently in the report and decided by the person.
- **Never stop to ask when nobody can answer.** Under `autopilot` (and in a headless run) a stuck phase is not a
  question for the person: decide the conservative way, record it as an assumption, or use the change flow.
  Stop only after three attempts at the same phase, and say exactly what is stuck.
- **Keep the scope the person asked for.** Tell the agents what was asked, and that rules, examples and code
  beyond it are proposals (deferred questions), not additions. A one-paragraph request seldom needs more than a
  handful of rules and a few examples per rule.
- **Requirements are the person's.** Never install packages into the machine's Python. If the adapter's
  requirements are missing, ask the person to install them (or install into the project's own environment only
  after they say yes) and run `bdd init --smoke` again.
- **The red gate is the point.** Do not let any production code be written before `bind` has passed.
- **Never** edit a feature file, step, driver or production file yourself, record an approval for the person, or
  weaken a gate. You may write `tasks.md` and `report.md` and nothing else in the project.

**Findings.** If the verdict is FINDINGS, look at the *must fix* items. Under `guided` and `standard` show them to
the person and let them decide. Under `auto` and `autopilot` fix them through the `change` flow and the phases it
reopens, then run verify again, at most twice; after that report what is left. Should-fix and unverifiable items
always go in the final report. A must-fix that is an existing test encoding the behaviour the request replaces
(for example an old amount) is not a question for the person under `auto` and `autopilot`: have the step-engineer
update that test through the `change` flow, and record the assumption in the report.

## 4. Human gates

At `specify` and `examples` the person approves. Show the work compactly (the rules with ids; the scenarios; the
assumptions; the pre-mortem result), then tell the person the exact line to type, and stop:

- `/greenlight:approve FEAT-n rules` or `/greenlight:approve FEAT-n examples`
- to refuse: `/greenlight:approve FEAT-n rules reject <reason>` (then redo the phase with the reason)

A typed approval is recorded by the prompt hook; you only look: `bdd approve FEAT-n --verify`, then try the next
gate. If the gate says an approval is still waiting to be verified, ask the person to send any short message
(for example "continue") and try again.

Never type the approval yourself and never ask another tool or agent to. Two exceptions, each recorded for what it
is: at `auto` and `autopilot`, `bdd approve FEAT-n GATE --auto`; and in a project without hooks (soft enforcement),
after the person says yes in the session, `bdd approve FEAT-n GATE --self-reported`. Say which one applied.
Under `guided` also ask the person after test design before moving on.

## 5. When the feature is done

Show the report's verdict, the traceability matrix (`bdd trace FEAT-n`), the enforcement level (hard or soft, and
why), the assumptions, the cost per phase and anything the auditor marked as must fix. If the feature ran on
`autopilot`, say plainly that it is UNREVIEWED and list the assumptions first. Then stop; do not start the next
feature on your own.

## Files to read when

| When | Read |
|---|---|
| a phase starts | `${CLAUDE_PLUGIN_ROOT}/phases/<phase>.md` (also pass it to the agent) |
| choosing test-design techniques | `bdd cards list --kind technique`, then the chosen cards |
| writing or resolving a step | `cards/instructions/<id>.md` of the instructions involved |
| a small one-rule change | `phases/quick.md` |
| verifying | `review/checklist.md` (the auditor reads it) |
