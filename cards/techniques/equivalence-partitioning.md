---
id: equivalence-partitioning
kind: technique
apply_when: an input can take many values that the rule treats in a few distinct ways
output: one example per class of input, valid and invalid, each with a reason it is its own class
cost: low
pairs_with: [boundary-value, decision-table]
---
## Intent

Inputs that the system handles the same way need one example, not twenty. Divide the inputs into classes,
test one representative of each, and spend the saved effort on the edges between classes.

## How to apply

1. For each input, list the classes the rule distinguishes: valid values by how they are treated
   (member, guest, staff) and invalid values by why they are invalid (missing, wrong type, out of range,
   unknown).
2. Pick one realistic representative for each class. Use data that looks like production, not `foo`.
3. Combine classes of *different* inputs only when you are checking a rule that depends on both; otherwise
   keep every other input valid and ordinary, so a failure points at one class.
4. Record the classes in the test-design file with the reason each exists. A class that you cannot explain
   is probably the same as another.
5. Put the edges between ordered classes through the boundary-value card.

## Worked example

Rule R-012.2: a coupon works for members and staff, never for guests.

| Class | Representative | Expected |
|---|---|---|
| member | a member signed in | discount applied |
| staff | a staff user signed in | discount applied |
| guest | not signed in | rejected, sign in first |
| unknown coupon code | code that does not exist | rejected, unknown coupon |

## Known pitfalls

- Treating "invalid" as one class. Each reason an input can be invalid is its own class and its own message.
- Merging classes because the code looks the same today. The classes come from the rule, not the code.
- Forgetting the empty and absent cases, which are usually their own classes.
- Using the same representative for different classes, which proves nothing about the difference.
