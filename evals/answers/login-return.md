Scripted answers for the login-return request. A run at a level that asks questions is answered from this file; under autopilot the assumptions the run records are compared with it.

- Which pages remember where the visitor was going? The cart and the checkout page (the pages that require a sign-in); the orders page too, for consistency.
- Where is the wanted page kept? In the address of the sign-in page, as a path.
- May the wanted page be any address? No: only a path on the shop itself, starting with a single slash. Anything else goes to the cart.
- What after a failed sign-in? The sign-in page is shown again with the same wanted page.
- Does signing in with no wanted page still go to the cart? Yes.
