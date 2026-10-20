---
id: blocking-questions
kind: practice
apply_when: the brief has gaps that would change a rule, and the person is available to answer
output: at most three questions asked one at a time, and every other gap recorded as an assumption with its rationale and alternatives
phase: discover
pairs_with: [request-decoder, pre-mortem]
---
## Intent

Questions cost the person's attention; assumptions cost correctness. Ask only what you cannot responsibly
guess, ask it well, and write down everything else as a visible assumption instead of burying it in a rule.

## How to apply

1. Take the gaps from the request decoder and rank them by risk: how wrong could the rule be if you guessed,
   and how expensive is it to find out later (after tests and code exist, a wrong rule is costly).
2. A gap is **blocking** if two plausible answers lead to different rules and a wrong guess would be
   expensive. Ask at most three blocking questions. If more seem blocking, the request is too big: use the
   story-splitting card.
3. Ask one question at a time, with a recommended answer and the reason. Offer short numbered choices where
   the answers are few. Skip any question the person has already answered.
4. Record everything non-blocking as an assumption (`bdd assume`): the text, why it is reasonable, and the
   alternatives you rejected. The assumption list goes in front of the person with the rules.
5. When the person answers, update the brief and the rules; when they say "you decide", record each decision
   as an assumption and move on.

## Worked example

Gap: when a saved card expires, what happens to a pending order?
Question: "If the card on file expires before an order ships, should we (1) ask the customer for a new card,
(2) cancel the order, or (3) keep it and retry later? I recommend 1, because it keeps the sale."
Non-blocking, recorded as an assumption: "Guests cannot save cards (rejected alternative: guests may save
with an email address)."

## Known pitfalls

- Asking everything at once, which gets skimmed answers. One question, then the next.
- Questions the person cannot answer ("how should the database look?"). Ask about behaviour, not design.
- Questions with no recommendation. The person should be able to say "yes".
- Hiding a risky assumption among trivial ones. Order assumptions by risk.
- Treating silence as agreement for blocking items. Wait, or record the assumption and flag it for approval.
