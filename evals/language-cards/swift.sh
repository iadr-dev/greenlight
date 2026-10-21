#!/bin/sh
# Runs the commands of cards/practices/language-swift.md on a small Swift package and checks that each one behaves as
# the card says. CI runs it on macOS; it needs the Swift toolchain (Xcode) and SwiftLint on the PATH;
# the CI job puts SwiftLint 0.65.1 there from its release, checksum pinned. A missing one fails the check, nothing is fetched here.
set -eu

. "$(dirname "$0")/expect.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
swift --version

mkdir -p Sources/Pricing Tests/PricingTests
cat > Package.swift <<'EOF'
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
  name: "Pricing",
  targets: [
    .target(name: "Pricing"),
    .testTarget(name: "PricingTests", dependencies: ["Pricing"])
  ]
)
EOF
# One deprecated call, one force cast (a SwiftLint rule that is on by default) and badly indented lines.
cat > Sources/Pricing/Pricing.swift <<'EOF'
/// The total after a 10% discount on orders of 1000 or more.
public func totalAfterDiscount(_ amount: Int) -> Int {
      amount >= 1000 ? amount - amount / 10 : amount
}

@available(*, deprecated, message: "use totalAfterDiscount(_:)")
public func oldTotal(_ amount: Int) -> Int {
  amount
}

/// The total of an order of five.
public func totalOfSmallOrder() -> Int {
  oldTotal((5 as Any) as! Int)
}
EOF
cat > Tests/PricingTests/PricingTests.swift <<'EOF'
import Pricing
import XCTest

final class PricingTests: XCTestCase {
  func testTheThresholdGetsTheDiscount() {
    XCTAssertEqual(totalAfterDiscount(1000), 900)
  }
}
EOF

# swift-format ships with the Swift 6 toolchain; with Xcode it is reached through xcrun or as `swift format`.
if command -v swift-format >/dev/null 2>&1; then
    swift_format="swift-format"
elif xcrun --find swift-format >/dev/null 2>&1; then
    swift_format="xcrun swift-format"
else
    swift_format="swift format"
fi
echo "swift-format is reached as: $swift_format"
# SwiftLint comes with the macOS runner image; nothing unpinned is installed here. A missing one is reported, not fetched.
echo "swiftlint $(swiftlint version)"

expect_pass "a plain build only warns about the deprecated call" swift build
expect_fail "warnings as errors refuses the deprecated call" swift build -Xswiftc -warnings-as-errors
expect_pass "the tests" swift test
expect_fail "swift-format in strict mode finds the indentation" $swift_format lint --recursive --strict Sources Tests
expect_fail "swiftlint --strict finds the force cast" swiftlint lint --strict Sources Tests

sed 's/  oldTotal((5 as Any) as! Int)/  totalAfterDiscount(5)/' Sources/Pricing/Pricing.swift > Pricing.swift.new
mv Pricing.swift.new Sources/Pricing/Pricing.swift
$swift_format format --in-place --recursive Sources Tests
expect_pass "warnings as errors once the deprecated call is replaced" swift build -Xswiftc -warnings-as-errors
expect_pass "swift-format in strict mode after formatting" $swift_format lint --recursive --strict Sources Tests
expect_pass "swiftlint --strict on clean, formatted code" swiftlint lint --strict Sources Tests
expect_pass "the tests" swift test
expect_fail "from the package root, swiftlint also lints the generated files in .build" swiftlint --strict
printf 'excluded:\n  - .build\n' > .swiftlint.yml
expect_pass "from the package root, once .swiftlint.yml excludes .build" swiftlint --strict

report_and_exit
