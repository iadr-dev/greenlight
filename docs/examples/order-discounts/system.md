# System map: FEAT-007 Order discounts

## Interfaces

| Logical name | Kind | Where in this system |
|---|---|---|
| place order | API operation | POST /orders |
| apply coupon | API operation | POST /orders/{id}/coupons |

## Data

- order: table `orders` (id, status, total, discount); seeded through the orders service, read through the
  repository.
- coupon: table `coupons` (code, valid_until); exists already.

## Dependencies

- payments: payment provider, stubbed with a recorded response

## Clock

The service reads time through `app.clock.now()`, which the tests replace.

## Events and jobs

None for this feature.

## Seams that do not exist yet

- discount calculation in `POST /orders`: must apply 10% when the total is 1000 or more.
- one-coupon limit in `POST /orders/{id}/coupons`: must refuse a second coupon.

## Contracts

`POST /orders` returns `{ "total": number, "discount": number }`.
