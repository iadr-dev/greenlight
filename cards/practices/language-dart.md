---
id: language-dart
kind: practice
apply_when: the project is a Dart or Flutter app and production code is written or judged
output: code that matches the Dart and Flutter versions the project declares, passes the analyzer and the formatter, and uses no deprecated API
phase: implement
pairs_with: [mutation-check]
---
## Intent

The `environment:` block of `pubspec.yaml` (the Dart `sdk` constraint and, for Flutter, the `flutter` constraint) and the
locked `pubspec.lock` are the standard. Write for that SDK with its current framework APIs; raising the SDK, Flutter or a
package version is a decision of the person, with its own change.

## How to apply

1. Read `.bdd/standards.md`, `pubspec.yaml`, `pubspec.lock` and `analysis_options.yaml` first.
2. Commands (Flutter projects use `flutter`, plain Dart projects use `dart`):
   - analysis: `flutter analyze` (`dart analyze`), with deprecation reported as an error in `analysis_options.yaml`
     (`deprecated_member_use: error`)
   - formatting: `dart format --output=none --set-exit-if-changed .`
   - packages from the lock file: `flutter pub get --enforce-lockfile`
3. Add the checks you want to `.bdd/config.toml`, for example:

   ```toml
   [adapters.quality.analyze]
   command = 'flutter analyze'

   [adapters.quality.format]
   command = 'dart format --output=none --set-exit-if-changed .'
   ```

4. Use the current API of the declared Flutter version; read its documentation (api.flutter.dev, or a documentation tool)
   instead of recalling a widget or a package method. Keep the analyzer's `flutter_lints` clean rather than silencing a
   rule with `// ignore:`.

## Known pitfalls

- Installing or upgrading a package with `flutter pub add` or `pub upgrade` inside a feature. An agent may not; return the
  requirement.
- Code that works on one platform only (`dart:io` in code that also runs on the web) without a platform check or a
  conditional import.
- A `BuildContext` used after an `await` without a `mounted` check.
- Deprecated widgets and members still present in older tutorials (`FlatButton`, `RaisedButton`, `WillPopScope`,
  `textScaleFactor`); the analyzer names the replacement.
- Business logic inside `build` methods, which makes it testable only through the widget tree; keep it in plain Dart classes
  that a library call can reach.
