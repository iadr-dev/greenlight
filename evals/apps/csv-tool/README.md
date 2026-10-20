# csv-tool

A tiny Go command-line tool (`csvtool count FILE`, no reports yet) used to evaluate greenlight end to end with the
`generic-junit` adapter and the `cli` profile. It has no BDD setup on purpose: the evaluation adds it.

```sh
go test ./...
go run . count data.csv
```

Standard library only (no `go.sum`). The feature request to try on it is in `evals/requests/csv-report.md`.
