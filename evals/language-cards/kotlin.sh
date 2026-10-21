#!/bin/sh
# Runs the commands of cards/practices/language-kotlin.md on a small Kotlin/JVM Gradle project and checks that each one
# behaves as the card says. CI runs it; it needs a JDK and Gradle on PATH (to create the wrapper the card insists on).
set -eu

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
expect_fail "allWarningsAsErrors refuses the deprecated call" ./gradlew build -x test --quiet
expect_fail "ktlintCheck finds the extra spaces" ./gradlew ktlintCheck --quiet

sed 's/fun totalOfSmallOrder(): Long =    oldTotal(5)/fun totalOfSmallOrder(): Long = totalAfterDiscount(5)/' \
    src/main/kotlin/pricing/Pricing.kt > Pricing.kt.new
mv Pricing.kt.new src/main/kotlin/pricing/Pricing.kt
expect_pass "build with warnings as errors once the deprecated call is replaced" ./gradlew build -x test --quiet
expect_pass "ktlintCheck on formatted code" ./gradlew ktlintCheck --quiet
expect_pass "detekt" ./gradlew detekt --quiet
expect_pass "the tests" ./gradlew test --quiet

report_and_exit
