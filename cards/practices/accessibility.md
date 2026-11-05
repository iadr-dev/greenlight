---
id: accessibility
kind: practice
apply_when: writing or reviewing a screen or component that a person sees or operates, on the web or on a mobile device
output: screens that meet WCAG 2.2 level AA, checked with the keyboard, a screen reader's view and the project's own tools, with each finding rated
phase: implement
pairs_with: [ui-design, language-typescript, language-dart, language-kotlin, language-swift]
---
## Intent

A screen that works only with a mouse, only with good eyesight or only in one language shuts people out, and in many
places the law requires level AA of WCAG 2.2. Most problems are cheap when the screen is built and expensive later,
and the commonest ones are found by reading the code and by using the screen without a mouse.

## How to apply

1. **Names and roles.** Use the platform's real controls (`button`, `a`, `input`, `select`; on mobile the framework's
   own buttons and fields) instead of a clickable box. Every control has an accessible name: its visible text, a
   `<label>` tied to the input, or an `aria-label`/`contentDescription`/`Semantics` label when there is no text. An icon
   button always has one. ARIA only where no native element fits, and then with the keyboard behaviour it promises.
2. **Keyboard and focus.** Everything that works with a pointer works with the keyboard, in an order that follows the
   screen. Focus is always visible (WCAG 2.4.7, 2.4.11), is not hidden behind sticky bars, moves into a dialog when it
   opens, stays there, and returns to the control that opened it. Composite widgets follow their usual keys: arrow keys
   in tabs, menus and radio groups, Escape closes, Enter or Space activates.
3. **Not by one sense alone.** Colour is never the only sign of state or error; text contrast at least 4.5:1 (3:1 for
   large text and for the edges of controls); nothing depends on hover, a gesture with a path, or dragging without an
   alternative (2.5.7); targets at least 24 by 24 CSS pixels (2.5.8), and the platform's own minimum on mobile (44 pt
   on iOS, 48 dp on Android).
4. **Text and layout.** Text resizes to 200% without loss and reflows at 320 CSS pixels wide (1.4.4, 1.4.10); spacing
   can be increased (1.4.12); the language of the page is set; headings and landmarks describe the structure.
5. **Forms and errors.** Required fields and formats are said before the person submits; an error names the field,
   says how to fix it, is tied to the field and is announced; nothing the person typed is lost on an error. Do not ask
   twice for what the person already gave (3.3.7); sign-in needs no memory test such as retyping a code from memory
   when a paste or a password manager would do (3.3.8).
6. **Motion and time.** Animation respects the reduced-motion setting; nothing flashes more than three times a second;
   a time limit can be extended.
7. **Check it.** Use the screen with the keyboard only. Read the accessibility tree (the browser's, or the platform's
   inspector). Run the project's own checks when it has them (an axe or Lighthouse step, `eslint-plugin-jsx-a11y`,
   Android lint's accessibility checks, Flutter's `meetsGuideline` in widget tests) through `[adapters.quality.NAME]`.
   Rate each finding:
   - **critical**: a person cannot complete the task at all (a control with no name, a keyboard trap);
   - **serious**: possible only with great effort, or breaks a level A criterion;
   - **moderate**: a level AA criterion broken in a way people can work around;
   - **minor**: inconsistency or polish.
   Critical and serious are must-fix.

## Known pitfalls

- `div` or `Container` with a click handler and no role, name or keyboard handling.
- A placeholder used as the label: it disappears when the person types, and is often too faint.
- `outline: none` with nothing in its place, so the focus cannot be seen.
- `aria-hidden` or `display: none` on something that still takes focus; or ARIA that contradicts the element
  (`role="button"` on a link that navigates).
- Error text shown in red only, or an error that is visible but not announced and not tied to its field.
- A modal that does not trap focus or return it, so keyboard users land at the top of the page.
- Automated checks find about a third of the problems. A clean axe run is not a pass on its own: name what was checked
  by hand.
- Fixed heights and widths that cut text when it is enlarged or translated into a longer language.
