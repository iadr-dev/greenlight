#!/bin/sh
# Runs the commands of cards/practices/language-rust.md on a small crate and checks that each one behaves as the card
# says: it fails on the finding it exists for and passes once the finding is fixed. CI runs it; it needs cargo with
# rustfmt and clippy, and installs cargo-audit if it is missing.
set -eu

. "$(dirname "$0")/expect.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
cargo new --lib demo --quiet
cd demo
rustc --version
cargo --version

cat > src/lib.rs <<'EOF'
#[deprecated(since = "0.2.0", note = "use `total_after_discount`")]
pub fn old_total(amount: u64) -> u64 { amount }

/// The total after a 10% discount on orders of 1000 or more.
pub fn total_after_discount(amount: u64) -> u64 {
    if amount >= 1000 { amount - amount / 10 } else { amount }
}

pub fn total_of_small_order() -> u64 {
    old_total(5)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_threshold_gets_the_discount() {
        assert_eq!(total_after_discount(1000), 900);
    }
}
EOF

expect_fail "unformatted code" cargo fmt --check
expect_pass "a plain build only warns about the deprecated call" cargo build --quiet
expect_fail "clippy with warnings denied refuses the deprecated call" cargo clippy --quiet --all-targets -- -D warnings
expect_pass "the tests" cargo test --quiet

cargo fmt
sed 's/    old_total(5)/    total_after_discount(5)/' src/lib.rs > src/lib.rs.new && mv src/lib.rs.new src/lib.rs
expect_pass "formatted code" cargo fmt --check
expect_pass "clippy once the deprecated call is replaced" cargo clippy --quiet --all-targets -- -D warnings
expect_pass "build" cargo build

sed 's/    total_after_discount(5)/    old_total(5)/' src/lib.rs > src/lib.rs.new && mv src/lib.rs.new src/lib.rs
{ printf '#![deny(deprecated)]\n'; cat src/lib.rs; } > src/lib.rs.new && mv src/lib.rs.new src/lib.rs
expect_fail "#![deny(deprecated)] in the crate makes a plain build refuse it" cargo build --quiet

command -v cargo-audit >/dev/null 2>&1 || cargo install cargo-audit --locked --quiet
cargo audit --version
cargo generate-lockfile --quiet
expect_pass "cargo audit on a crate without dependencies" cargo audit

report_and_exit
