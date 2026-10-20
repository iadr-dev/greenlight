# Brief: FEAT-007 Order discounts

## The ask

> Give big orders a discount, and let people use a coupon code too.

## The job behind it

Shop owners want larger baskets, and customers who arrive with a promotion code want it to work at checkout
(hypothesis: the code arrives by email, so it is the way most returning customers pay less).

## Problem statement

Customers who buy in volume or hold a coupon pay full price, so large orders are rarer than the shop would like.
It is solved when an order of 1000 or more shows a 10% reduction and one valid coupon can be applied to an
order, both visible in the order total.

## Goals

- An order total of 1000 or more is reduced by 10%.
- A customer can apply one coupon to an order.

## Non-goals

- Tiered discounts above 1000.
- Stacking several coupons on one order.
- Managing or creating coupons (they already exist).

## Must-haves and nice-to-haves

- Must: the volume discount; one coupon per order.
- Nice: a message explaining why a coupon was refused.

## Candidate rules

- Orders of 1000 or more get 10% off.
- An order takes at most one coupon.

## Assumptions

- A-007.1 The 10% applies to the order total before shipping. Why: shipping is quoted separately today.
  Rejected: discounting shipping too.
- A-007.2 Totals are in a single currency. Why: the shop sells in one. Rejected: per-currency thresholds.

## Open questions

- [deferred] Should a coupon combine with the volume discount? Recommended: yes, volume first, then the coupon.
  Waits for: the coupon rules, a later slice.

## Non-functional concerns

None known.
