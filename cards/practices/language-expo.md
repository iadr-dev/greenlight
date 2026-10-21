---
id: language-expo
kind: practice
apply_when: the project is an Expo or React Native app and production code is written or judged
output: code that matches the Expo SDK the project declares, with compatible native module versions and no deprecated API of that SDK
phase: implement
pairs_with: [language-typescript]
---
## Intent

The Expo SDK version in `package.json` fixes which React Native version, which native modules and which APIs are
valid. An SDK upgrade is a project decision with its own procedure, never a side effect of a feature.

## How to apply

1. Read `.bdd/standards.md`, `app.json` or `app.config.ts`, and the `expo` version in `package.json`.
2. Commands (in addition to those of the TypeScript card):
   - versions match the SDK: `npx expo install --check`
   - project health: `npx expo-doctor`
   - lint: `npx expo lint`
3. Add configuration to `.bdd/config.toml` for the checks you want, for example:

   ```toml
   [adapters.quality.doctor]
   command = 'npx expo-doctor'

   [adapters.quality.lint]
   command = 'npx expo lint'
   ```

4. Use the routing and APIs of the declared SDK (Expo Router file-based routes if the project uses it). Read the
   documentation for that SDK version, because module APIs change between releases.

## Known pitfalls

- Installing a native module with `npm install` instead of `npx expo install`, which picks the version for the SDK. An agent may do neither; return the requirement.
- Upgrading the SDK, React Native or the New Architecture setting inside a feature. Use the upgrade procedure, as its own change, with the person's approval.
- Code that works on one platform only (web or iOS or Android) without a platform check or a file suffix (`.ios.ts`).
- Importing a module that needs a development build into an app that runs in Expo Go.
- Deprecated modules still present in older tutorials; check the SDK's documentation before using a package.
- `npx expo lint` in a project without an ESLint setup installs `eslint` and `eslint-config-expo` into `package.json` and writes `eslint.config.js`, and fails on that first run. That is a dependency change: run it only where ESLint is already configured, and treat a missing setup as a requirement for the person.
- `npx expo-doctor` and `npx expo install --check` need the network (they check the registry and the SDK's version list).
- Run on 2026-10-21 with Node 26, Expo SDK 58 (`expo` 58.0.16, React Native 0.88.0) on a project from `create-expo-app --template blank-typescript`: `npx expo install --check` exited 0 ("Dependencies are up to date"), `npx expo-doctor` (1.21.5) passed 20 of 20 checks, and `npx expo lint` behaved as described above and then exited 0.
