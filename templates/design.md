# Design: FEAT-000 <title>

<!-- Written by the system-analyst in the system-map phase, from the approved scenarios and the code it read.
     Only the views this feature needs, each small enough to review in a minute. Plain Mermaid, nothing active
     (no click, href or init directives). `%% interface: NAME` comments say which rows of the Interfaces table in
     system.md a diagram shows; `bdd design FEAT-n` checks that they exist. -->

## Components and data flow

```mermaid
flowchart LR
  %% interface: place order
  client[Client] -->|POST /orders| api[Orders API]
  api --> pricing[Discount rule]
  api --> db[(Orders table)]
```

## Key interaction

```mermaid
sequenceDiagram
  %% interface: place order
  participant C as Client
  participant A as Orders API
  C->>A: POST /orders
  A-->>C: 201 with the discounted total
```

## Data model

<!-- For a feature that changes the schema: the tables it adds or changes, with keys and the cardinality of each
     relation, so the person sees them before binding (card `database-schema`). -->

```mermaid
erDiagram
  ORDER ||--|{ LINE : contains
```

## Decisions the diagrams show

- <choice made, and why, in one line each>
