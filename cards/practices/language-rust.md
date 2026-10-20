---
id: language-rust
kind: practice
apply_when: writing or judging production code in a Rust project
output: code that follows the edition and rust-version in Cargo.toml, is rustfmt clean, passes clippy with warnings denied, and uses no deprecated API
phase: implement
pairs_with: [mutation-check]
---
## Intent

The `edition` and `rust-version` in `Cargo.toml` (and `rust-toolchain.toml`, if present) are the standard. Write for them
with their current standard library and crate APIs; raising the edition, the toolchain or a crate version is a decision of the person.

## How to apply

1. Read `.bdd/standards.md`, `Cargo.toml`, `rust-toolchain.toml` and `clippy.toml`.
2. Commands:
   - format: `cargo fmt --check`
   - lint, with every warning (deprecations included) as an error: `cargo clippy --all-targets -- -D warnings`
   - build and tests: `cargo build`, `cargo test`
   - `-D warnings` includes the compiler's `deprecated` lint, so a use of a `#[deprecated]` item fails; a project can also state it in the crate with `#![deny(deprecated)]`
3. To have greenlight run them, add tables to `.bdd/config.toml`:

   ```toml
   [adapters.quality.format]
   command = 'cargo fmt --check'

   [adapters.quality.lint]
   command = 'cargo clippy --all-targets -- -D warnings'
   timeout = 1800
   ```

4. Read the current documentation of every crate you call (docs.rs for the declared version, or a documentation tool such
   as context7). `#[deprecated]` items name their replacement.

## Known pitfalls

- `unwrap()` and `expect()` in production paths; return a `Result` and let the caller decide.
- Blanket `#[allow(...)]` or `#![allow(warnings)]` to get a build through; allow a single lint at the narrowest scope, with a reason.
- `clone()` to satisfy the borrow checker without understanding the ownership problem.
- `unsafe` without a safety comment that states the invariant.
- Adding a crate or enabling a feature flag for a small convenience; dependencies are the person's decision.
- Editing `Cargo.lock` by hand.
