# Phase 2: Specify

Agent: **product-analyst**. Cards: `pre-mortem`, `negative-cases`.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- `brief.md` with the discover gate passed.
- `templates/rules.md`, `.bdd/glossary.md`.
- When the product has an approved design: the feature's screen rows (`bdd design FEAT-n --screens`) and their screen
  files.

## Steps

1. Write `rules.md` from `templates/rules.md`: one rule per line that starts with its id (`R-<feature>.<n>`),
   each with why, source and priority. Measurable non-functional requirements get `N-<feature>.<n>`.
2. Write the rules the request implies, and those the pre-mortem shows are blocking; nothing else. A rule the
   person did not ask for is a deferred question in the brief, not a rule. Each rule states what must be true, in
   the person's language. A rule that names a screen, a table or a
   URL is a design: rewrite it.
3. When the product has an approved design, run `bdd design FEAT-n --screens` and read the screen files it names.
   Every field, state and action of those rows becomes a rule, is covered by a rule the examples will show, or is a
   question for the person in the brief. A field nobody asked for is not dropped in silence: the system analyst traces
   every one of them to a rule before code (`design.md`, *Design trace*). In the Fieldly run the design listed a tax ID,
   an invoice footer and bank details, the rules named none of them, and the API built other fields.
4. Add new domain terms to `.bdd/glossary.md`.
5. Read `pre-mortem` and run it on the draft: imagine the feature failed, rank the causes as blocking, tracked
   or noise. Add or change a rule for every blocking cause and record every tracked one as an assumption.
6. Show the person the rule list compactly, with the assumptions and the pre-mortem result.

## Output files

`rules.md`, `.bdd/glossary.md` (new terms).

## Gate (human)

The person approves the rules by typing `/greenlight:approve FEAT-n rules` (or rejects with a reason:
`/greenlight:approve FEAT-n rules reject <reason>`). Stop and ask; do not run `bdd approve` yourself.

- Under `auto` and `autopilot` the orchestrator records it with `bdd approve FEAT-n rules --auto`; it is shown as
  auto-approved, never as human-approved.
- In a project without hooks (soft enforcement), after the person says yes in the session, record it with
  `bdd approve FEAT-n rules --self-reported`. The command refuses when the project requires hard enforcement
  or hooks have run.

A rejection returns here: change `rules.md` and ask again.

## Pitfalls

- Rules that cannot fail: "the system works properly". A rule must be something an example can contradict.
- Packing two rules in one line. One statement, one id.
- Editing `rules.md` after approval. The approval records its hash; a changed file needs approval again.
- Treating the pre-mortem as a formality. Every blocking cause needs a rule.
