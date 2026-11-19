---
id: product-design
kind: practice
apply_when: turning a product spec into the product description, the feature map, the screen inventory, the flows and the screens of the whole product, before any feature is built
output: a design folder a person can approve by looking at one page, in which every screen of the product is drawn with every state, every screen belongs to a feature of the map, and every screen uses the tokens
pairs_with: [ui-design, accessibility, story-splitting]
---
## Intent

A person who gives only a product spec cannot review code, but they can look at screens. The design stage gives them
the whole product to look at before anything is built: who uses it and for what, the features in the order they will
be built, and every screen in every state, drawn in the product's own visual language. This card is what the
ux-designer and the ui-designer follow when the `impeccable` plugin is not installed, and the bar they meet when it is.

## How to apply

1. **Read the spec for facts, not for words.** Write `PRODUCT.md` with a section each on the users (who, where, how
   often, what they already use), their jobs (what each one must finish, the most frequent first) and the platforms
   (web, iOS, Android, LINE, a command line). Mark what you inferred **(inferred)** and list what the spec leaves open
   under *Open questions*; you cannot ask the person, so never fill a gap with an invented fact.
2. **Cut the product into features a person can approve one at a time** (`story-splitting`). Each gets an id
   (`FEAT-001` onwards), a name, one sentence that says what a user can do after it, the features it depends on and a
   build order. Sign-in and the data every other feature needs come first. A feature that needs another is built after
   it; nothing depends on a later feature.
3. **List every screen before drawing any.** The inventory has one row per screen: a stable id (`O-ST-01`: side, area,
   number), the screen, its states, the feature that builds it and the file that draws it. A list has loading, empty,
   error and success at least; a form adds validation errors and saving; anything on a phone adds offline. Add the
   states the domain has (a job in progress, a payment overdue, an expired invitation).
4. **Draw the flows** in `flows.html`: the path through the screens for each job of step 1, by inventory id, with the
   branches (cancel, fail, retry) as well as the happy path.
5. **Write the design contract before the screens** (`DESIGN.md`): the first thing the eye must find on the main
   screen, the one primary action, the density and why, the type scale, the colour roles, and the generic defaults this
   product does not use. Then the tokens (`tokens.json`, and `tokens.css` with the same values as CSS custom
   properties) and the components.
6. **Draw every state of every row**, as real HTML that links `tokens.css` and uses its variables, one element per
   state: `<section data-screen="O-ST-01" data-state="empty">`. Use realistic content from one shared made-up dataset
   (names, amounts, long and short strings, the longer language when there are two). No lorem ipsum.
7. **Check it before anyone else does.** Run `bdd gallery --check` and fix every finding, then `bdd gallery` and look
   at the page at 375 px and 1280 px.

## Known pitfalls

- A screen drawn only in its success state. The first slow network is the state a person sees most.
- A generic dashboard, card grid or hero that could belong to any product. The main screen shows the user's real work
  (their jobs, their orders, their schedule) and the decision they make there.
- Colours and sizes typed into a screen instead of taken from the tokens, so the code later invents a second palette.
- A feature map that follows the screens rather than what a user can do; a feature with no screen of its own is fine
  (an import, a nightly job), a screen with no feature is not.
- Inventing a fact the spec does not give (a price, a legal rule, a provider) instead of listing it as an open question.
- Renaming an inventory id after it is used: features, flows and later the scenarios refer to it.
