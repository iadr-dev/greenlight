# Tasks: FEAT-007 Order discounts

## T-007.1 Volume discount on order placement

Covers: EX-007.1.1, EX-007.1.2, EX-007.1.3
Areas: app/orders/service.py, app/orders/api.py
Depends on: none
Size: S

## T-007.2 One coupon per order

Covers: EX-007.2.1
Areas: app/orders/coupons.py
Depends on: T-007.1
Size: S
