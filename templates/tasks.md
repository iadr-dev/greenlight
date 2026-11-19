# Tasks: FEAT-000 <title>

<!-- Written by the orchestrator after the red gate. Vertical slices in build order. Each task starts with its
     id (T-<feature>.<n>) and names the examples it turns green; `bdd trace` reads both.
     Design and Risks: copy them from `bdd route FEAT-000`, then add what it missed. Design names the sections of
     design.md the task builds and the inventory rows of its screens; Risks names known risks only (concurrent writes,
     retries and idempotency, rate limits, unmapped storage errors, authorisation, personal data, time zones, large
     lists), or none. Tasks that share no Areas path and wait for no other task may be built at the same time.
     The gate: every example is owned by exactly one task. -->

## T-000.1 <task title>

Covers: EX-000.1.1, EX-000.1.2
Areas: <files or modules likely touched>
Depends on: none
Design: <sections of design.md>; <inventory row ids>
Risks: <known risks, or none>
Size: S | M | L

## T-000.2 <task title>

Covers: EX-000.1.3
Areas:
Depends on: T-000.1
Design:
Risks:
Size:
