---
id: language-typescript
kind: practice
apply_when: writing or judging production code in a TypeScript or JavaScript project, including Node, Expo and Next.js
output: code that follows the declared TypeScript and Node versions, passes type check lint and format checks, and uses no deprecated API
phase: implement
pairs_with: [language-expo, language-nextjs]
---
## Intent

The versions declared in `package.json` (`engines`, the TypeScript and framework versions) and `tsconfig.json` are the
standard. Write for them with their current APIs; the project's own tools say whether the code is clean.

## How to apply

1. Read `.bdd/standards.md`, `tsconfig.json`, the ESLint configuration and the scripts in `package.json`. Use the
   package manager the lockfile names (`npm ci`, `pnpm install --frozen-lockfile`, `yarn install --immutable`); never
   mix them.
2. Commands:
   - types: `npx tsc --noEmit` (with `"strict": true` in `tsconfig.json`)
   - lint: `npx eslint .`, with the `@typescript-eslint/no-deprecated` rule set to `error` so a deprecated API fails the check (the rule needs type information: set `languageOptions.parserOptions.projectService: true`; `tsc --noEmit` does not report deprecations by itself)
   - format: `npx prettier --check .`
   - Node deprecations as errors in tests: `NODE_OPTIONS=--throw-deprecation` (set by the test script, not by greenlight)
3. Agents cannot run `npx` or install packages; the orchestrator runs the checks with `bdd check`, and an agent may run the
   project's own scripts (`npm run lint`, `npm test`). To have greenlight run the tools, add tables to `.bdd/config.toml`:

   ```toml
   [adapters.quality.typecheck]
   command = 'npx tsc --noEmit'

   [adapters.quality.lint]
   command = 'npx eslint .'

   [adapters.quality.format]
   command = 'npx prettier --check .'
   ```

4. Read the current documentation of every library you call (the project's docs, or a documentation tool such as
   context7). The type definitions show `@deprecated` tags; the editor and ESLint surface them, so do not ignore them.

## Known pitfalls

- `any`, `as unknown as T` and non-null `!` to silence the compiler; model the type or narrow it.
- `// @ts-ignore` and `eslint-disable` without a reason. Prefer `@ts-expect-error` with a comment, so it fails when it stops being needed.
- Adding or upgrading a dependency to solve a small problem. Dependencies are the person's decision.
- Mixing CommonJS and ES modules; follow the `type` field and the project's module setting.
- Unhandled promises (`floating promises`) and `async` functions passed where a callback is expected.
- Running `npm install`, `npx` of a package that is not already a dependency, or editing `node_modules`: agents may not.
- A type-aware ESLint setup (`projectService`) reports `Parsing error: ... was not found by the project service` for a JavaScript config file such as `eslint.config.mjs` that `tsconfig.json` does not include: ignore the config file in the ESLint configuration or list it in `allowDefaultProject`, rather than turning type-aware rules off.
- Run on 2026-10-21 with Node 26, TypeScript 5.9.3, ESLint 9.39.5, typescript-eslint 8 and Prettier 3.9.10 on a small project with a `@deprecated` function: `tsc --noEmit` exited 0 (it does not report the deprecation), `eslint .` exited 1 with `@typescript-eslint/no-deprecated` on the call, `prettier --check .` exited 1 on unformatted files, and `NODE_OPTIONS=--throw-deprecation` turned `new Buffer()` into a thrown error.
