# Architecture

<!-- Decided once for the whole product, from the product spec, before any feature is built. The person approves it
     together with the design (/greenlight:approve design), and every feature's technical design starts from it.
     `bdd gallery --check` checks this structure: every section below is present and filled in, and the stack table
     has a row for every surface in [surfaces] of .bdd/config.toml. Replace each comment with the decision and why. -->

## Stack per surface

<!-- One row per surface the product ships (web, ios, android, api, cli): the framework, the language and its version.
     Name the official documentation the writers will follow; .bdd/sources.toml lists the services. -->

| Surface | Stack | Why |
|---|---|---|

## Layers

<!-- The layers and which may call which (for example: screens -> application services -> domain -> data access).
     Name where validation, authorisation and error handling live. The architecture checker in [adapters.quality]
     enforces these rules when the project has one. -->

## Hosting and environments

<!-- Where each surface runs, the environments (local, preview, staging, production), how configuration and secrets
     reach each one, and who may deploy. -->

## Authentication

<!-- How people sign in (providers, sessions or tokens, lifetime, sign-out), the roles, and where each permission is
     checked. Authorisation is checked on the server, never only on the screen. -->

## Data store

<!-- The database or storage per kind of data, the schema and migration tool, backups, and what personal data is kept,
     where, and for how long. -->

## Security baseline and threat model

<!-- The baseline every feature follows (input validation, output escaping, secrets out of the code, dependency
     updates, rate limits, safe errors and logs) and the threats that matter for this product, each with its control. -->

| Threat | Control |
|---|---|

## Observability

<!-- Logs, metrics, traces and error tracking: the tools, what is never logged (secrets, personal data), and the
     alerts someone acts on. -->

## CI and delivery

<!-- What runs on every pull request (the scenarios, `bdd check`, the locks and approvals), how a change reaches each
     environment, and how a release is rolled back. -->
