---
id: ui-design
kind: practice
apply_when: writing or reviewing a screen, page or component, on the web or on a mobile device
output: screens built from the project's design system, with every state designed, that follow the platform's conventions and fit the widths the project supports
phase: implement
pairs_with: [accessibility, language-typescript, language-nextjs, language-expo, language-dart, language-kotlin, language-swift]
---
## Intent

A screen is consistent when it is made of the parts the project already has. Most UI defects in generated code are not
in the logic but in what was invented next to the design system: a new shade of a colour, a spacing that exists
nowhere else, a second button component, a state nobody designed. Read what exists, use it, and design every state.

## How to apply

1. **Find the design system before writing.** Look for the tokens (colours, spacing, radius, type scale, shadows) in
   the theme file, CSS variables, a Tailwind config, a `ThemeData`, `MaterialTheme` or asset catalogue; the shared
   components; the layout primitives; how screens are routed. A `DESIGN.md`, a Storybook or a Figma file the project
   names is the reference. Use them by name; a value typed directly where a token exists is a finding.
2. **Design every state of the screen**, not only the one in the scenario: loading (with a skeleton or an indicator
   that does not shift the layout), empty (says what to do next), error (says what happened and how to recover, keeps
   what the person entered), success, and the partial states in between (some items failed, a slow call). A list has a
   long and a very long case.
3. **Layout.** Mobile first: build for the narrowest width the standards name, then add space. Use the layout
   primitives (flex, grid, stacks) instead of absolute positions and fixed sizes. Check the widths and orientations the
   project supports, and on mobile the safe areas, the keyboard covering a field, and the system's text size.
4. **Hierarchy and text.** One primary action per screen; secondary actions look secondary. Headings in order. Copy is
   short and says what the button does ("Save address", not "Submit"). Strings come from the project's translation
   files when it has them; no text inside images.
5. **Follow the platform.** On iOS and Android use the platform's navigation, back behaviour, sheets, pickers and
   gestures rather than imitating the web; on the web, links navigate and buttons act.
6. **Behaviour.** Interactions answer within a moment (disable a button while its request runs, prevent a double
   submit); optimistic updates roll back visibly on failure; motion is short, purposeful and respects reduced motion.
7. **Performance a person feels.** Images sized for their slot and lazily loaded below the first screen; no layout
   shift when data or fonts arrive; long lists virtualised; nothing heavy on the main thread during input.
8. **When a design is given** (a Figma node, a mock, a `DESIGN.md`), match it with the project's components and tokens,
   and list every place the design asks for something the system does not have: that is a question for the person, not
   a new token.

## Known pitfalls

- A one-off component that duplicates one the project has, because the existing one was not found. Search first.
- Hard-coded colours and sizes that break the dark theme, a brand change or the system's text size.
- Designing only the happy path, so the first slow network shows a blank screen or a spinner forever.
- Copying a web pattern to mobile (a hamburger menu where the platform uses a tab bar, a custom back button).
- Layouts tested at one width only; text that fits in English and not in German or Finnish.
- Changing a test id, label or component name a step relies on while restyling: the scenarios are locked, so the
  screen must keep the names they use.
- Adding a UI or icon library for one widget. A new dependency is a question for the person.
