---
id: request-decoder
kind: practice
apply_when: a feature request has just arrived, in the person's own words, before any rule is written
output: the literal ask, the job behind it, must-haves and nice-to-haves, a problem statement with goals and non-goals, and a list of gaps
phase: discover
pairs_with: [blocking-questions, story-splitting]
---
## Intent

People ask for a solution ("add a discount code field"). The brief needs the problem behind it ("returning
customers abandon checkout when they cannot apply the promotion they were emailed"). Decode the request
first, so the rules describe what the person needs and not only what they typed.

## How to apply

1. Copy the request word for word as **the literal ask**. Do not improve it.
2. Write **the job behind it** in one sentence: who is trying to do what, in which situation, and why it
   matters. Write it as a hypothesis if you are inferring, and mark it so.
3. Split the ask into **must-haves** (without them the job is not done) and **nice-to-haves**. When unsure,
   it is a question, not a must-have.
4. Write a **problem statement** (the problem, who has it, what success looks like in observable terms) and
   the **goals and non-goals**. Non-goals matter most: they stop the rules from growing.
5. List the **gaps and ambiguities**: anything a rule would need that the request does not say. Infer only
   what is safe and say that you did; never invent a fact to fill a gap.
6. Hand the gaps to the blocking-questions card and write the result into `brief.md`. No solutions, screens
   or technology in the brief.

## Worked example

Literal ask: "Let customers pay with a saved card."
Job behind it (hypothesis): returning customers want to check out in one step.
Must-have: pay with a card the customer saved earlier. Nice-to-have: choose among several saved cards.
Non-goal: storing new card types. Gap: may guests save a card?

## Known pitfalls

- Replacing the literal ask with your reading of it. Keep both, side by side.
- A job statement that is only the solution turned around ("the customer wants a saved card field").
- Goals that cannot be observed ("improve the experience"). Say what would be different and for whom.
- Listing gaps as one vague "needs more detail". Each gap is a specific question a rule depends on.
- Writing architecture or screens into the brief, which commits the design before the rules are approved.
