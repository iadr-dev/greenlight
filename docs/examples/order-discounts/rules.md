# Rules: FEAT-007 Order discounts

## Business rules

R-007.1 An order whose total is 1000 or more gets 10% off the total.
- Why: larger baskets are what the shop wants to encourage.
- Source: the person's request.
- Priority: must

R-007.2 An order takes at most one coupon; a second coupon is refused and the order stays as it was.
- Why: stacking coupons would let a discount grow without limit.
- Source: the person's answer to the coupon question.
- Priority: must

## Non-functional requirements

N-007.1 Placing an order with a discount responds within 300 ms for 95% of requests.
- Source: existing service objective.

## Out of scope

- Tiered volume discounts, coupon creation, and discounts on shipping.

## Glossary additions

- Order total: the sum of the item prices before shipping and before any discount.
