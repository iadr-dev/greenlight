# Bundled data

`gherkin-languages.json` is a trimmed copy of
[`gherkin-languages.json`](https://github.com/cucumber/gherkin/blob/main/gherkin-languages.json)
from the Cucumber Gherkin project (MIT License, Copyright (c) Cucumber Ltd). Only the keyword
lists greenlight's parser needs are kept; the content is otherwise unchanged. It is what lets
`.feature` files be written with localized keywords (`# language: zh-TW`).

`services.json` is greenlight's own catalog of the services and frameworks `bdd init` recognises in a project's
dependency files (`bddlib/sources.py`). Each entry has an id, a name, a `kind` (`service` or `framework`), the official
documentation, the vendor's command-line tool and plugin when there is one, the surfaces a framework ships (`web`, `ios`,
`android`, `api`), project `files` that show the service without a dependency, and the package names per ecosystem
(`npm`, `pypi`, `go`, `maven`, `nuget`, `pub`, `cargo`, `gem`; `*` matches any run of characters). A package that is not
listed is never guessed. A plugin id is one `claude plugin list` shows in Anthropic's directory.
