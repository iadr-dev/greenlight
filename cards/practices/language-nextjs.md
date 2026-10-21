---
id: language-nextjs
kind: practice
apply_when: the project is a Next.js app and production code is written or judged
output: code that matches the Next.js version and router the project declares and uses no API that version deprecates
phase: implement
pairs_with: [language-typescript]
---
## Intent

The Next.js version in `package.json` and the router in use (the `app` directory or the older `pages` directory) decide
which APIs are current. Features follow the project's router; migrating between routers or upgrading Next.js is its own
decision.

## How to apply

1. Read `.bdd/standards.md`, `next.config.*`, the `next` version in `package.json` and whether `app/` or `pages/` is used.
2. Commands (in addition to those of the TypeScript card):
   - the production build type-checks the project: `npx next build`
   - lint with the project's own ESLint script; older versions have `next lint`, newer ones call ESLint directly, so use
     the script in `package.json`
3. Add configuration to `.bdd/config.toml` for the checks you want, for example:

   ```toml
   [adapters.quality.build]
   command = 'npx next build'
   timeout = 900
   ```

4. Read the documentation and the upgrade guide of the declared version before using an API; names and file conventions
   change between major versions.

## Known pitfalls

- Marking everything `use client`. Components are server components by default in the app router; add the client directive only where state, effects or browser APIs need it.
- Fetching data in a client component what a server component could do, and leaking secrets by reading non-public environment variables in client code.
- Mixing app-router and pages-router conventions in one route.
- APIs removed or deprecated in the declared version (for example older image and export helpers); the build and the ESLint deprecation rule report them.
- Upgrading Next.js, React or the router inside a feature.
- `next lint` no longer exists in current versions: in Next.js 16 `npx next lint` reads `lint` as a project directory and fails ("Invalid project directory"). Use the `lint` script of `package.json`, which calls `eslint` directly.
- Run on 2026-10-21 with Node 26 and Next.js 16.4.2 (React 19.3.0) on a project from `create-next-app` (app router, TypeScript, ESLint): `npx next build` type-checked and built (exit 0), `npm run lint` exited 0.
