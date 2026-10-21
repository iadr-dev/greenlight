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
   - known vulnerabilities in the dependencies (needs `cargo install cargo-audit --locked` once): `cargo audit`
   - a plain `cargo build` only warns about a `#[deprecated]` item; `-D warnings` makes clippy refuse it (the compiler's
     `deprecated` lint is a warning), and a crate that states `#![deny(deprecated)]` makes every build refuse it
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
- A `cargo audit` installed on a Windows machine with the GNU toolchain fails to build (`dlltool.exe` missing); install it with the MSVC toolchain or run it in CI.
- Checked for real by `evals/language-cards/rust.sh` in CI (Ubuntu) and locally on Windows (GNU toolchain), 2026-10-21, with
  Rust 1.99.1, rustfmt 1.10.0, clippy 0.1.99 and cargo-audit 0.22.2 on a small crate (edition 2024, the default of
  `cargo new`): each command fails on its finding (unformatted code, a deprecated call) and passes once it is fixed.
