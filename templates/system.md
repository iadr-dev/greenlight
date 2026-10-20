# System map: FEAT-000 <title>

<!-- Written by the system-analyst after the examples are approved. For every step of the scenarios: the
     interface it uses in this code base. Unknown interfaces are design decisions to list, not to guess.
     `bdd scan` reads the Dependencies list below. -->

## Interfaces

| Logical name | Kind | Where in this system |
|---|---|---|
| place order | API operation | POST /orders |
| export report | command | python -m app export |
| round money | library function | app.money:round_money |

## Data

- <entity>: <table or model, and how a test seeds and reads it>

## Dependencies

<!-- External systems the tests may stub, one per line. A stub of anything not listed here is a finding. -->
- payments: payment provider, stubbed with a recorded response

## Clock

<how time reaches the code: a clock seam, or the process clock frozen by the test tools>

## Events and jobs

- <event or job, and how a test delivers it or runs it>

## Seams that do not exist yet

<!-- These stay as ExpectedMissing in tests/drivers/system.py until the implementer builds them -->
- <seam>: <what it must do>

## Contracts

<!-- When the project has a schema file (OpenAPI, GraphQL, protobuf), name it and copy the operations and types this
     feature uses, exactly as the file has them; say which of them the feature adds or changes. When it has none, say
     so here instead of inventing one. For a database, name the migration folder and the tables this feature reads or
     changes. -->
<schemas or interface fragments the implementation must satisfy>
