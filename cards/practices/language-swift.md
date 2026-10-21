---
id: language-swift
kind: practice
apply_when: writing or judging production code in a Swift project, for Apple platforms or on the server
output: code that follows the project's declared Swift language mode and deployment targets, builds with warnings as errors, passes the linter, and uses no deprecated API
phase: implement
pairs_with: [mutation-check]
---
## Intent

The Swift language mode, the Xcode or toolchain version and the deployment targets the project declares are the
standard. Write for them with their current APIs; raising the toolchain or the deployment target is the person's decision.

## How to apply

1. Read `.bdd/standards.md`, `Package.swift` or the Xcode project settings, `.swiftlint.yml` and `.swift-format`.
2. Commands:
   - Swift package, warnings as errors (deprecations included): `swift build -Xswiftc -warnings-as-errors`
   - Xcode project: `xcodebuild build -scheme <scheme> SWIFT_TREAT_WARNINGS_AS_ERRORS=YES`
   - lint: `swiftlint --strict`
   - format: `swift-format lint --recursive --strict Sources Tests`
   - tests: `swift test` or `xcodebuild test` on a simulator; concurrency checking as the declared language mode requires
3. To have greenlight run them, add tables to `.bdd/config.toml`:

   ```toml
   [adapters.quality.build]
   command = 'swift build -Xswiftc -warnings-as-errors'
   timeout = 1800

   [adapters.quality.lint]
   command = 'swiftlint --strict'
   ```

4. Read the current documentation of every Apple framework API you call (the project's docs, or a documentation tool such
   as context7). Frameworks deprecate APIs release by release; the availability notes name the release.

## Known pitfalls

- Force unwraps (`!`), `try!` and `as!` outside tests.
- `@unchecked Sendable` and `nonisolated(unsafe)` to quiet concurrency checking; fix the isolation.
- Old patterns where the declared deployment target has the modern API: `ObservableObject` and `@Published` where `@Observable` is available, `NavigationView` instead of `NavigationStack`, completion handlers instead of `async` functions.
- `// swiftlint:disable` without a reason, and warnings left in the build.
- Editing the Xcode project file or build settings by hand to make a build pass; those are the person's decisions.
- Code that needs a newer OS than the deployment target without an `#available` check.
- The commands in this card come from the tools' documentation and were not run against a real project: Swift needs macOS or a Swift toolchain, and none was available when the cards were checked on 2026-10-21.
