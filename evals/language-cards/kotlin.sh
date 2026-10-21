#!/usr/bin/env bash
# Runs the commands of cards/practices/language-kotlin.md on a small Kotlin/JVM Gradle project and checks that each one
# behaves as the card says. CI runs it; it needs a JDK and Gradle on PATH (to create the wrapper the card insists on).
set -euo pipefail

. "$(dirname "$0")/expect.sh"

KOTLIN_VERSION=2.4.21
KTLINT_PLUGIN=14.2.0
DETEKT_PLUGIN=1.23.8

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
java -version 2>&1 | head -n 1
gradle --version | grep -E "^Gradle "

mkdir -p src/main/kotlin/pricing src/test/kotlin/pricing
cat > settings.gradle.kts <<'EOF'
rootProject.name = "pricing"
EOF
cat > build.gradle.kts <<EOF
plugins {
    kotlin("jvm") version "$KOTLIN_VERSION"
    id("org.jlleitschuh.gradle.ktlint") version "$KTLINT_PLUGIN"
    id("io.gitlab.arturbosch.detekt") version "$DETEKT_PLUGIN"
}

repositories { mavenCentral() }

dependencies { testImplementation(kotlin("test")) }

kotlin {
    compilerOptions { allWarningsAsErrors.set(true) }
}

tasks.test { useJUnitPlatform() }
EOF
cat > src/main/kotlin/pricing/Pricing.kt <<'EOF'
package pricing

/** The total after a 10% discount on orders of 1000 or more. */
fun totalAfterDiscount(amount: Long): Long = if (amount >= 1000) amount - amount / 10 else amount

@Deprecated("use totalAfterDiscount", ReplaceWith("totalAfterDiscount(amount)"))
fun oldTotal(amount: Long): Long = amount

fun totalOfSmallOrder(): Long =    oldTotal(5)
EOF
# The same code, cleaned up: named constants instead of magic numbers, no deprecated call, formatted.
cat > Pricing.kt.clean <<'EOF'
package pricing

private const val DISCOUNT_THRESHOLD = 1000L
private const val DISCOUNT_DIVISOR = 10L
private const val SMALL_ORDER = 5L

/** The total after a 10% discount on orders of [DISCOUNT_THRESHOLD] or more. */
fun totalAfterDiscount(amount: Long): Long =
    if (amount >= DISCOUNT_THRESHOLD) amount - amount / DISCOUNT_DIVISOR else amount

@Deprecated("use totalAfterDiscount", ReplaceWith("totalAfterDiscount(amount)"))
fun oldTotal(amount: Long): Long = amount

fun totalOfSmallOrder(): Long = totalAfterDiscount(SMALL_ORDER)
EOF
cat > src/test/kotlin/pricing/PricingTest.kt <<'EOF'
package pricing

import kotlin.test.Test
import kotlin.test.assertEquals

class PricingTest {
    @Test
    fun theThresholdGetsTheDiscount() {
        assertEquals(900, totalAfterDiscount(1000))
    }
}
EOF

gradle wrapper --quiet
expect_fail "allWarningsAsErrors refuses the deprecated call" ./gradlew compileKotlin --quiet
expect_fail "ktlintCheck finds the extra spaces" ./gradlew ktlintCheck --quiet
expect_fail "detekt finds the magic numbers" ./gradlew detekt --quiet
expect_fail "build runs detekt and ktlint too, once their plugins are applied" ./gradlew build -x test --quiet

mv Pricing.kt.clean src/main/kotlin/pricing/Pricing.kt
cp src/main/kotlin/pricing/Pricing.kt Pricing.kt.before
expect_pass "ktlintFormat rewrites the code into the project's style" ./gradlew ktlintFormat --quiet
echo "      what ktlintFormat changed:"
diff Pricing.kt.before src/main/kotlin/pricing/Pricing.kt | sed 's/^/        /' || true
expect_pass "compile with warnings as errors once the deprecated call is replaced" ./gradlew compileKotlin --quiet
expect_pass "ktlintCheck on formatted code" ./gradlew ktlintCheck --quiet
expect_fail "ktlint allows 140 characters and detekt 120, so the two disagree" ./gradlew detekt --quiet

printf 'root = true\n\n[*.{kt,kts}]\nmax_line_length = 120\n' > .editorconfig
expect_pass "ktlintFormat with the line length detekt uses, from .editorconfig" ./gradlew ktlintFormat --quiet
expect_pass "ktlintCheck with the shared line length" ./gradlew ktlintCheck --quiet
expect_pass "detekt with named constants and the shared line length" ./gradlew detekt --quiet
expect_pass "build, linters included, on clean code" ./gradlew build -x test --quiet
expect_pass "the tests" ./gradlew test --quiet

report_and_exit
