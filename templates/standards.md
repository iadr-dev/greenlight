# Engineering standards

Status: DRAFT

<!-- Edited and approved by the person; no agent can write this file. When you have read and changed it to describe how
     this project's code is written, change the status line above to `Status: APPROVED`. The implementer, the
     step-engineer and the auditor read it on every feature. A change to it makes the recorded quality results out of
     date, so they are run again. Delete what does not apply; keep it short enough to be read. -->

## Language and toolchain

<!-- The declared toolchain is the standard. A new project starts on the current stable release; an existing one keeps
     its version until you decide to upgrade (an agent never upgrades a toolchain, framework or dependency on its own). -->
- Language and version: <for example Python 3.12, Kotlin 2.x with JVM 21, Swift 6, TypeScript 5.x on Node 22, Go 1.23, Rust stable>
- Build and package tool: <uv, Gradle, SwiftPM, pnpm, go modules, cargo>
- Frameworks: <for example FastAPI, Expo SDK n, Next.js n (app router)>

## Style

- Formatter: <ruff format, ktlint, swift-format, prettier, gofmt, rustfmt>; code is formatted, never hand-aligned.
- Naming and structure: <the conventions of the code base, in a few lines>

## Quality rules

- Linter and type checker: <ruff and mypy, detekt, SwiftLint, eslint and tsc, go vet, clippy>, run by `bdd check` once they are in `[adapters.quality]`.
- <for example: no unused code, no silent exception handling, public functions have types, no new global state>

## Deprecation policy

- Code uses the current, non-deprecated API of the declared toolchain and of every library it calls.
- Deprecation warnings are errors where the toolchain supports it (<the switch for this stack>).
- Before using a library API, the current documentation is read (the project's docs, or a documentation tool such as context7), not recalled from memory.

## Dependencies

- A new dependency is a decision the person makes; it is named in the report, never added silently.
- <licence, size or security rules, if any>
