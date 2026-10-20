# Phase 1: Discover

Agent: **product-analyst**. Cards: `request-decoder`, `blocking-questions`, `story-splitting`.

## Inputs

- The person's request, word for word.
- `.bdd/glossary.md` and any related documents or code the analyst may read (read-only).
- `templates/brief.md`.

## Steps

1. Create the feature if it does not exist: `bdd state init FEAT-n --title "<title>"`.
2. Read the `request-decoder` card, then fill `brief.md` from `templates/brief.md`: the ask verbatim, the job
   behind it, the problem statement, goals, non-goals, must-haves, candidate rules. No solutions, screens or
   technology.
3. List the gaps. Read `blocking-questions` and rank them by risk.
4. If the request is larger than a handful of rules, read `story-splitting`, write the slices into the brief
   and continue with the first slice only.
5. Ask the blocking questions one at a time (at most three), each with a recommendation. Record the answers
   in the brief. Record every other gap as an assumption: `bdd assume FEAT-n --text "..." --rationale "..."
   --alt "..."`, and list it in the brief.
6. Under `autopilot`, do not ask: answer each blocking question with the most conservative reasonable
   choice and record it as an assumption with the alternatives rejected.
7. Record the cost: `bdd cost FEAT-n --phase discover --tokens N --seconds S`.

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
