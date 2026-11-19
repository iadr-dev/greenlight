---
id: pre-mortem
kind: practice
apply_when: the draft rules and examples are ready and before the person is asked to approve them
output: a short list of how this feature could fail in the real world, each marked blocking, tracked or noise, with a rule or example added for every blocking one
phase: specify
pairs_with: [negative-cases, blocking-questions]
---
## Intent

Approval is the last cheap moment to change a rule. Imagine the feature has shipped and failed, and ask why.
Doing this on the draft finds the missing rule before tests and code depend on it.

## How to apply

1. Read the draft rules and examples as if the feature has launched and caused a complaint.
2. Write the causes, aiming at: a case nobody wrote down, a different kind of user, a failure of something the
   feature depends on, data that is dirty or huge, two things happening at once, and a rule that is correct
   but surprising.
3. Mark each cause **blocking** (the feature is wrong or unsafe without a fix), **tracked** (real, but can follow
   later; record it as an assumption or a later slice) or **noise** (unlikely or harmless; drop it).
4. For every blocking cause, add or change a rule and at least one example; for every tracked one, write the
   assumption in the brief. Show the person the list with the rules.
5. Keep it short: ten minutes of thought and at most ten causes.
6. In the tasks phase, run it again per task against the known risks, the failures that late audits keep finding in
   code that passed its scenarios: concurrent writes (two sign-ins linking one account at once), retries and
   idempotency, rate limits, unmapped storage errors (a database error shown raw), authorisation, personal data, time
   zones and large lists. `bdd route` names the ones the rules, steps and design raise; write any it missed on the
   task's `Risks:` line, and the code reviewer answers each one.

## Worked example

Draft: "A saved card is charged when the order ships."
Causes: the card is declined on the ship date (blocking: add a rule for what happens); the customer changed
their address (tracked); the carrier ships twice (blocking: charge once); the price changed since ordering
(blocking: charge the ordered price).

## Known pitfalls

- A list of everything that could possibly go wrong. Rank it; most items are noise.
- Fixing a blocking cause in the prose only. It needs a rule and an example, or the tests will not catch it.
- Marking everything blocking to be safe, which stops the feature from ever being approved.
- Skipping it for small features. A one-rule change still gets a two-minute version.
- Dropping a known risk from a task because it "does not apply". Keep it on the `Risks:` line; the code reviewer
  writes `not applicable` with the reason, which costs one line and shows someone looked.
