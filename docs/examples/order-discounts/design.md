# Design: FEAT-007 Order discounts

## Components and data flow

```mermaid
flowchart LR
  %% interface: place order
  %% interface: apply coupon
  client[Client] -->|POST /orders| api[Orders API]
  client -->|POST /orders/id/coupons| api
  api --> discount[Discount rule]
  api --> db[(Orders table)]
```

## Key interaction

```mermaid
sequenceDiagram
  %% interface: place order
  participant C as Client
  participant A as Orders API
  C->>A: POST /orders (total 1000)
  A-->>C: 201 with the 10% discounted total
```

## Decisions the diagrams show

- The discount rule is a pure function of the order total, so it needs no seam.
