# Product and design stage

Agent: **ux-designer**, then **ui-designer** and **ui-reviewer**. Cards: `product-design`, `ui-design`, `accessibility`, `story-splitting`.

Run once per product, before any feature, from `/greenlight:init --product <spec file>`. A person who has only a product
spec ends with the product described, every feature in build order, the architecture decided and every screen drawn in
every state, and approves all of it by looking at one page. The stage is not a feature and has no feature id; its
record is `.bdd/design-stage.json`, written only by the command line.

Recording is the orchestrator's job. The agents write their files and report; they run no `bdd gate`, `bdd approve`,
`bdd lock` or `bdd change`. The person's approval is typed by the person.

## Inputs

- The product spec, word for word (its path is in `.bdd/design-stage.json`).
- `.bdd/config.toml`: `[design]` (the design folder, `design/` unless it says otherwise) and `[surfaces]`.
- `.bdd/sources.toml`: the services and their official documentation, when `bdd init` found any.
- An existing design folder, when the project has one: it is read and completed, never regenerated.
- `templates/product.md` and `templates/architecture.md` (`bdd init --product` copied them into `.bdd/`).

## Steps

1. **Start.** `bdd init --product <spec file>` records the stage, adds `[design]` when the configuration has none, and
   copies the feature map and architecture templates into `.bdd/` when they are missing. It never overwrites a file.
2. **The product and its features.** Run the ux-designer. It writes `PRODUCT.md` in the design folder (users, jobs,
   platforms) and the feature map, `.bdd/product.md`: every feature with its id, a one-line description, what it
   depends on and its build order.
3. **The architecture.** The orchestrator fills `.bdd/architecture.md` from the spec, the feature map and
   `.bdd/sources.toml`: the stack per surface, the layers, hosting and environments, authentication, the data store,
   the security baseline and the threat model, observability, CI and delivery. Every section states a decision and
   why. For an existing code base, read it first (with the `feature-dev` plugin's code-explorer and code-architect
   agents when it is installed) and record what is there rather than what would be nice. Check every framework and
   service against its current documentation (context7 or microsoft-docs when installed, else the official site named
   in `sources.toml`). A choice only the person can make (a paid provider, where the data may live) is listed in the
   section as an open question with a recommendation, not decided silently.
4. **The screens on paper.** Run the ux-designer again (or in the same run) for the screen inventory in the design
   folder's `inventory.md`, one row per screen: `| ID | Screen | States | Feature | File | Fields |`, and `flows.html`.
5. **The visual design.** Run the ui-designer. It writes `DESIGN.md` (the design system and the design contract),
   `tokens.json` and `tokens.css`, and `screens/*.html`: every state of every row in an element marked
   `data-screen="<row id>" data-state="<state>"`, styled only through the tokens.
6. **Check.** Run `"${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" gallery --check`. Each finding names a file and a code; give it
   to the agent that owns the file and run that agent again with the finding, word for word:

   | Codes | Owner |
   |---|---|
   | `DS2`, `PM*`, `IN1` to `IN4`, a missing `PRODUCT.md`, `inventory.md` or `flows.html` | ux-designer |
   | `IN5`, `IN6`, `SC*`, a missing `DESIGN.md` or `tokens.json` | ui-designer |
   | `AR*`, a missing `.bdd/architecture.md` | the orchestrator (step 3) |

   Repeat until it prints `the design checks found nothing`.
7. **Review.** Run the ui-reviewer with the instruction *review the design*, and give it the design digest that
   `bdd gallery --check` printed. It writes `.bdd/design-reviews/design-ui-reviewer.md` with that `Design:` digest and a
   `Verdict:` line. For every *Must fix* item, run the owning designer again with the item and go back to step 6; a
   changed design has a new digest, so the review runs again. After two rounds that still end in `FINDINGS`, stop and
   show the person the open items with the gallery: they decide.
8. **Show the person.** Build the page and the summary, and show the summary unchanged:

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" gallery
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" approve design --summary
   ```

   Tell the person where the page is (`design/gallery.html`, opened in any browser; it needs no network) and what to
   look at: each feature with its screens, every state, the flows, the screens at a phone and a desktop width. List the
   open questions of `PRODUCT.md` and `.bdd/architecture.md` in plain words. Then ask them to type, alone in the
   message, `/greenlight:approve design`, or `/greenlight:approve design reject <what should change>`. The approval is
   refused while a check finds a gap, while the review does not name the design as it is, and while the page is not
   the one `bdd gallery` builds from the design now; relay the refusal and fix its cause.
9. **After the approval.** `bdd status` prints `design: approved, locked`. The design folder, the feature map and the
   architecture are now read-only for every agent and the orchestrator. Build the features in the map's order with
   `/greenlight:feature`, each with its id from the map (`bdd state init FEAT-001 --title "<name>"`); each feature's
   discover gate waits for the approved design. The ui-engineer builds each screen from its inventory rows.
10. **A rejection or a later change.** A rejection names what should change: go back to the step that owns it. A
    change after the approval goes through `/greenlight:change`, which runs `bdd change --reopen design --reason
    "<the person's words>"`: it releases the lock and revokes the approval, and steps 6 to 8 run again; the summary
    then lists only what changed.

## Helpers, when installed

Every step works without them, with the cards above. When one is installed, it is used only as listed, and only on the
files of the design folder: never on production code.

| Step | Helper and what for |
|---|---|
| 2, 4 | `impeccable` `init` (the product context in `PRODUCT.md`) and `shape` (the screens and states before drawing) |
| 3 | `feature-dev` code-explorer and code-architect for an existing code base; context7 and microsoft-docs for the stack's current documentation; the vendor plugins of the services in `sources.toml` |
| 5 | `impeccable` `document` (a `DESIGN.md` from an existing design), `generate` (variants of an element, picked by the designer against the contract) and `polish` (the last pass over the screen files); `frontend-design` for the visual direction; the `figma` plugin when the person names a Figma file; chrome-devtools for screenshots of every screen at 375 px and 1280 px |
| 7 | `impeccable` `audit` and the criteria of its finish-reviewer agent, in report mode only |

## Output files

`<design folder>/PRODUCT.md`, `DESIGN.md`, `tokens.json`, `tokens.css`, `inventory.md`, `flows.html`, `screens/*.html`
and `gallery.html`; `.bdd/product.md`, `.bdd/architecture.md`, `.bdd/design-reviews/design-ui-reviewer.md`. The approval
is in `.bdd/design-stage.json` and the lock in `.bdd/design.lock.json`, both written only by the command line.

## Gate

There is no `bdd gate` for the stage. It is done when `bdd approve design --check` passes: the person's approval is
verified, the design has not changed since, and it is locked.

## Pitfalls

- Regenerating a design folder the project already has. Read it, complete what the checks find missing, and keep its
  ids: features, flows and scenarios refer to them.
- Asking the person to approve before the gallery is rebuilt, or showing them a page from an earlier version. The
  approval is refused for exactly that reason.
- Letting an agent ask the person a question. The designers list open questions in `PRODUCT.md`; the orchestrator
  asks them at step 8.
- Using `impeccable` `polish`, `harden` or any other mode that edits code on production files. In this stage they
  touch the design folder only.
- Editing the design after the approval to fix a detail found while building a feature. A change goes through
  `/greenlight:change`, so the person sees it.
