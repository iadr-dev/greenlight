# Test design: FEAT-007 Order discounts

## R-007.1 An order of 1000 or more gets 10% off

Techniques: boundary-value, negative-cases
Why these: there is one threshold (1000), so both sides and the edge are needed; the order total is an input
that can be malformed, so one refusal example is needed.

- EX-007.1.1 Just below the threshold (boundary-value: 999.99 gets no discount)
- EX-007.1.2 Exactly on the threshold (boundary-value: 1000.00 gets 10% off)
- EX-007.1.3 A negative total is refused (negative-cases: malformed input, nothing changes)

Excluded:
- Totals far above the threshold, because they follow the same path as the edge example.

## R-007.2 An order takes at most one coupon

Techniques: negative-cases
Why these: the rule is a limit; the interesting case is the second coupon being refused.

- EX-007.2.1 A second coupon is refused (negative-cases: wrong state, the order is unchanged)

## Coverage check

- Every rule has at least one example: yes
- Every decision-table row and every state transition is an example or an exclusion: not applicable
- Cards read, including their Known pitfalls: boundary-value, negative-cases
