# money-lib

A tiny TypeScript money library (parse, add, format; no currency conversion and no rounding rules) used to evaluate
greenlight end to end with the `generic-junit` adapter and the `lib` profile. It has no BDD setup on purpose: the
evaluation adds it.

```sh
npm ci
npm test
```

The feature request to try on it is in `evals/requests/money-convert.md`.
