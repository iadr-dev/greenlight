# Phase 1: Discover

Agent: **product-analyst**. Cards: `request-decoder`, `blocking-questions`, `story-splitting`.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- The person's request, word for word.
- `.bdd/glossary.md` and any related documents or code the analyst may read (read-only).
- `templates/brief.md`.

## Steps

1. The feature exists (the orchestrator ran `bdd state init FEAT-n --title "<title>"`).
2. Read the `request-decoder` card, then fill `brief.md` from `templates/brief.md`: the ask verbatim, the job
   behind it, the problem statement, goals, non-goals, must-haves, candidate rules. No solutions, screens or
   technology.
3. List the gaps. Read `blocking-questions` and rank them by risk.
4. If the request is larger than a handful of rules, read `story-splitting`, write the slices into the brief
   and continue with the first slice only.
5. Return the blocking questions (at most three), each with a recommendation; the orchestrator asks them one at
   a time and runs you again with the answers, which you record in the brief. List every other gap in the brief
   as an assumption (text, rationale, rejected alternatives); the orchestrator records it with `bdd assume
   FEAT-n --text "..." --rationale "..." --alt "..."`.
6. Under `autopilot`, do not ask: answer each blocking question with the most conservative reasonable
   choice and record it as an assumption with the alternatives rejected.
7. Report the tokens and time you spent; the orchestrator records them with `bdd cost FEAT-n --phase discover
   --tokens N --seconds S`.

## Output files

`.bdd/features/FEAT-n-slug/brief.md`; assumptions in `state.json` (through `bdd assume`).

## Gate

The brief has no `[blocking]` question left. Record it:

```sh
bdd gate FEAT-n discover --result pass
```

Record `--result fail` with `--detail blocking_questions=N` when questions remain, and ask them.

## Pitfalls

- Designing the solution in the brief. The rules come next, and the person approves them first.
- Asking many questions at once, or questions about technology the person cannot answer.
- Burying a risky assumption among trivial ones. Order them by risk.
- Replacing the person's words with your reading of them. Keep both.
