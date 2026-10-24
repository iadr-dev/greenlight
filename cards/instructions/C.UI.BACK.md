---
id: C.UI.BACK
kind: instruction
apply_when: a person returns to the previous screen, with the back button, the back gesture or the browser's back
---
## Semantics

Return to the previous screen, the way the platform's back action does.

Kind: **when**. Profile: ui. Carries: nothing.

## In practice

Say what happens, not how it is triggered: "alice goes back". The driver does what a person on that platform does (the browser's back, the Android back action, the route pop of a Flutter app). Follow it with a check of the screen that comes back (`alice sees ... showing:`), because going back is only worth a scenario when what it returns to matters, such as a form that keeps what was typed or a list that keeps its place.

## Patterns

- `{actor} goes back`

## Good and bad Gherkin

Good:

```gherkin
When alice opens the orders page
And alice clicks first order link
And alice goes back
Then alice sees order list showing:
  | item     |
  | 7 placed |
```

Bad:

```gherkin
When alice presses the back arrow in the top left corner
```

## Known pitfalls

- Going back with nothing to go back to. A browser or an app with a single screen stays where it is; open a second screen first.
- Describing the gesture or the button ("the back arrow", "swipes from the edge"). The platform decides how a person goes back; the feature says only that they do.
- Checking nothing afterwards. A scenario that goes back and asserts nothing proves only that nothing crashed.
- Expecting the back action to undo a change. It leaves the screen; what the screen did stays done.
