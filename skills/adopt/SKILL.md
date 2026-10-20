---
name: adopt
description: Bring existing code under greenlight by writing rules and examples that describe what it already does, with tests that pass today and locks that keep them honest. Use when the user runs /greenlight:adopt "<area of the code>", or asks to add tests and specs to code that already exists before changing it.
argument-hint: '"<module, API area or command to describe>" [--autonomy guided|standard|auto|autopilot]'
---

# greenlight adopt (the orchestrator for existing code)

You run in the main session, exactly as the `feature` skill does: you drive the phases, you talk to the person, and you
are the only one who records anything. The phase agents cannot ask the person and report instead of recording. Read
`${CLAUDE_PLUGIN_ROOT}/skills/feature/SKILL.md` for the loop, the rules for questions, change requests, costs and
assumptions, and the human gates; they all apply. Then read `${CLAUDE_PLUGIN_ROOT}/phases/adopt.md`: it lists what is
different, and it is the plan.

Arguments: `$ARGUMENTS`

## What an adoption is

A normal feature goes red, then green, with new code in between. An adoption describes behaviour the system **already
has**: every scenario is tagged `@existing`, the tests pass from the start, and **no production code is written or
changed**. Its value is the safety net: afterwards a change to that area goes through `/greenlight:feature` or
`/greenlight:change` with locked, traced tests behind it.

## Before anything

- The project must be set up (`.bdd/config.toml` exists); if not, tell the person to run `/greenlight:init` and stop.
- The arguments must name an area of the code that can be described in a handful of rules. If it is vague or large,
  look at the repository read-only, propose slices, and ask which one to start with. One slice per adoption.
- If the person actually wants the behaviour to change, say so and offer `/greenlight:feature` instead.
- Settle the autonomy level once, as the `feature` skill does.
- The working tree should be committed or at least understood: the bind gate pins the production source as it is then.

## Run it

1. `bdd state next-id`, then `bdd state init FEAT-n --title "<area>" --adopt --autonomy LEVEL`.
2. Follow the loop of the `feature` skill phase by phase with these differences (details in `phases/adopt.md`):
   - Tell every agent in its task: this is an adoption, describe existing behaviour, tag every scenario `@existing`,
     change no production code, cite where each rule was observed.
   - Code that looks wrong is a question for the person, never a rule and never a fix.
   - At bind: lock the bound files, then `bdd gate FEAT-n bind --result pass --record-red` (the run is a valid red
     because every scenario is `@existing` and passes).
   - `tasks` and `implement` have no agent. Pass tasks with `--detail adopt=true`. For implement run `bdd run FEAT-n`,
     `bdd classify FEAT-n --expect green` and `bdd adopt FEAT-n --check` yourself, then
     `bdd gate FEAT-n implement --result pass --detail adopt=true`. Never start the implementer.
   - Verify with the spec-auditor as usual.
3. The person types `/greenlight:approve FEAT-n rules` and `/greenlight:approve FEAT-n examples`. You never do.

## Never

- Edit a production file, a feature file, a step or a driver yourself, or let an agent edit production code. The gates
  `implement` and `verify` refuse an adoption whose production source changed since the bind gate.
- Turn a failing scenario into a passing one by changing the code. Fix the scenario (the reading was wrong) or ask the
  person.
- Present an adoption as a change of behaviour, or the reverse.

## When it is done

Show the report's verdict, `bdd trace FEAT-n`, the enforcement level, the assumptions, the cost per phase, any code
that looked wrong (as questions the person may want to turn into a feature), and the next slice if there was one. Then
stop; do not start the next adoption on your own.
