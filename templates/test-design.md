# Test design: FEAT-000 <title>

<!-- Written by the qa-designer. For each rule: which techniques (card ids) and why, then the examples.
     One example line per example, starting with its id (EX-<feature>.<rule>.<n>); `bdd trace` reads them.
     Every rule with inputs needs a negative example or a reason it has none. -->

## R-000.1 <rule, short>

Techniques: boundary-value, negative-cases
Why these: <the card's apply-when, matched to this rule>

- EX-000.1.1 <name> (boundary-value: just below the edge)
- EX-000.1.2 <name> (boundary-value: on the edge)
- EX-000.1.3 <name> (negative-cases: malformed input, nothing changes)

Excluded:
- <case> because <reason>

## Coverage check

- Every rule has at least one example: yes | no
- Every decision-table row and every state transition is an example or an exclusion: yes | no | not applicable
- Cards read, including their Known pitfalls: <card ids>
