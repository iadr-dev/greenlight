---
id: language-kotlin
kind: practice
apply_when: writing or judging production code in a Kotlin project, on the JVM or Android
output: code that follows the project's declared Kotlin and JVM or Android versions, builds without warnings, passes the formatter and static analysis, and uses no deprecated API
phase: implement
pairs_with: [mutation-check]
---
## Intent

The Kotlin version, the JVM toolchain and the Android compile and target SDK declared in the Gradle build files are the
standard. Write for them with their current APIs; a toolchain, plugin or library upgrade is a decision of the person.

## How to apply

1. Read `.bdd/standards.md`, `build.gradle.kts` (or the Groovy build files), `gradle/libs.versions.toml` and
   `gradle.properties`. Use the Gradle wrapper of the project (`./gradlew`), never a system Gradle.
2. Commands (the task names depend on the plugins the project applies):
   - compile with warnings as errors, which makes every Kotlin deprecation fail: set
     `kotlin { compilerOptions { allWarningsAsErrors.set(true) } }` in the build (the person's file or a standards decision)
     and run `./gradlew compileKotlin`; `./gradlew build` also runs ktlint and detekt once their plugins are applied (they
     hook into `check`), so a build failure may be a lint finding, not a compiler error
   - format: `./gradlew ktlintCheck` (`./gradlew ktlintFormat` rewrites the files) or `./gradlew spotlessCheck`
   - static analysis: `./gradlew detekt`; Android: `./gradlew lint`
   - ktlint's official style allows lines of 140 characters and detekt's default limit is 120, so `ktlintFormat` can join a
     line that detekt then refuses: set one limit for both in `.editorconfig` (`max_line_length = 120` under `[*.{kt,kts}]`)
3. To have greenlight run them, add tables to `.bdd/config.toml`:

   ```toml
   [adapters.quality.build]
   command = './gradlew build -x test'
   timeout = 1800

   [adapters.quality.format]
   command = './gradlew ktlintCheck'

   [adapters.quality.lint]
   command = './gradlew detekt'
   ```

4. Read the current documentation of every library and Android API you call (the project's docs, or a documentation tool
   such as context7). Android deprecates APIs per API level; check the level you compile against.

## Known pitfalls

- `!!` and unchecked casts to silence nullability; model the null case.
- `GlobalScope`, `runBlocking` in production code, and blocking calls on the main dispatcher.
- `kapt` where the project has moved to KSP, and Java date classes where `java.time` or `kotlinx-datetime` is in use.
- `@Suppress("DEPRECATION")` added to pass the build. Replace the API; a suppression needs a reason beside it.
- Changing `build.gradle.kts`, the version catalog or the wrapper to make a build pass. Those are the person's decisions; return the question.
- Android: permissions, lifecycle-unaware work, and APIs available only above the project's `minSdk` without a version check.
- detekt's default rules include `MagicNumber` and `MaxLineLength`; a first run on an existing code base reports many
  findings. Start from a baseline (`./gradlew detektBaseline`) the person agrees to, not by suppressing rules in a feature.
- Checked for real by `evals/language-cards/kotlin.sh` in CI (Ubuntu), 2026-10-21, with Kotlin 2.4.21, Gradle 9.8.2,
  JDK 21, the ktlint Gradle plugin 14.2.0 and detekt 1.23.8 on a small module: `allWarningsAsErrors` refuses a deprecated
  call, ktlint and detekt fail on their findings (spacing, magic numbers, the line-length disagreement) and everything
  passes once fixed. `./gradlew spotlessCheck` and Android `./gradlew lint` were not run.
