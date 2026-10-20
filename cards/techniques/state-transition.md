---
id: state-transition
kind: technique
apply_when: something has a lifecycle with states and events, such as orders, subscriptions, tickets or approvals
output: the allowed transitions as a table, an example per transition, and an example per forbidden transition
cost: medium
pairs_with: [decision-table, equivalence-partitioning]
---
## Intent

A thing that moves through states is described by what it may do next in each state. Test every legal move and
a sample of the illegal ones, because the bugs are in the moves nobody allowed.

## How to apply

1. List the states and the events (user actions, timers, messages) that can happen to the thing.
2. Fill a table of state × event. Each cell is the next state, "stays", or "not allowed". An empty cell is a
   question for the person.
3. Write one example per legal transition: given the thing in that state, when the event happens, then the new
   state and any side effect (a message sent, a record written).
4. Write one example per forbidden transition that has a visible result (an error, no change). Use the
   *no X records changed* style step to show nothing happened.
5. Cover the paths too: the shortest route from start to end, and any loop (retry, reopen). Time-based
   transitions need the clock steps, never real waiting.

## Worked example

Rule R-033.1: an order can be cancelled until it ships.

| State | Cancel | Ship |
|---|---|---|
| placed | cancelled | shipped |
| shipped | not allowed | not allowed |
| cancelled | not allowed | not allowed |

## Known pitfalls

- Testing only the happy path through the states. Forbidden moves and repeated events (double submit, event
  received twice) are where the defects are.
- Forgetting the side effects of a transition, such as a refund on cancel.
- Starting every example from the first state. Seed the thing directly in the state under test.
- Hidden states: "processing" or "pending" that the rules never name. Ask for them.
