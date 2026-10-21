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
     and run `./gradlew build`
   - format: `./gradlew ktlintCheck` or `./gradlew spotlessCheck`
   - static analysis: `./gradlew detekt`; Android: `./gradlew lint`
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
- The commands in this card come from the tools' documentation and were not run against a real project (no ktlint, detekt or Kotlin compiler was available when the cards were checked on 2026-10-21). The Gradle form of the Kotlin and Android adapters was run for real in CI, but not these quality tools.
