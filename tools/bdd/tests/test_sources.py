"""The manifests of a project, the services they name, and `.bdd/sources.toml`."""
import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from bddlib import sources


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def deps(self, rel: str) -> dict[str, str]:
        (found,) = [m for m in sources.manifests(self.root) if m.path == rel]
        return found.deps


class ManifestTest(ProjectCase):
    def test_package_json_reads_every_dependency_section_and_the_package_manager(self):
        self.write("package.json", json.dumps({"dependencies": {"fastify": "5.0.0"}, "devDependencies": {"typescript": "^5"},
                                               "peerDependencies": {"react": "*"}, "packageManager": "pnpm@9.1.0", "bin": "cli.js"}))
        (found,) = sources.manifests(self.root)
        self.assertEqual(found.deps, {"fastify": "5.0.0", "typescript": "^5", "react": "*"})
        self.assertEqual(found.ecosystem, "npm")
        self.assertEqual(found.flags, {"bin", "pm:pnpm"})

    def test_pyproject_reads_project_groups_and_poetry_and_names_its_tool_tables(self):
        self.write("pyproject.toml", '[project]\nname = "x"\ndependencies = ["Django>=5.0", "requests[socks]==2.32"]\n'
                   '[project.optional-dependencies]\nweb = ["fastapi"]\n[project.scripts]\nx = "x:main"\n'
                   '[dependency-groups]\ndev = ["ruff>=0.6", {include-group = "web"}]\n'
                   '[tool.poetry.dependencies]\npython = "^3.11"\nflask = "^3"\n[tool.ruff]\nline-length = 100\n')
        (found,) = sources.manifests(self.root)
        self.assertEqual(found.deps["Django"], ">=5.0")
        self.assertEqual(found.deps["requests"], "==2.32")
        self.assertEqual(set(found.deps) - {"python"}, {"Django", "requests", "fastapi", "ruff", "flask"})
        self.assertEqual(found.flags, {"scripts", "tool:ruff", "tool:poetry"})

    def test_requirements_files_skip_options_comments_and_paths(self):
        self.write("requirements-dev.txt", "# tools\n-r base.txt\n--index-url https://x\n./local\nruff==0.6.1  # pinned\nmypy\n")
        self.assertEqual(self.deps("requirements-dev.txt"), {"ruff": "==0.6.1", "mypy": ""})

    def test_go_mod_reads_requires_and_tools_and_skips_indirect_ones(self):
        self.write("go.mod", "module x\n\ngo 1.24\n\nrequire github.com/gin-gonic/gin v1.10.0\n\nrequire (\n"
                   "\tgithub.com/stripe/stripe-go/v79 v79.1.0\n\tgolang.org/x/sys v0.1.0 // indirect\n)\n\n"
                   "tool github.com/golangci/golangci-lint/cmd/golangci-lint\n")
        self.assertEqual(self.deps("go.mod"), {"github.com/gin-gonic/gin": "v1.10.0", "github.com/stripe/stripe-go/v79": "v79.1.0",
                                               "github.com/golangci/golangci-lint/cmd/golangci-lint": ""})

    def test_pom_reads_dependencies_the_parent_and_plugins(self):
        self.write("pom.xml", "<project><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent"
                   "</artifactId><version>3.3.0</version></parent><dependencies><dependency><groupId>com.stripe</groupId>"
                   "<artifactId>stripe-java</artifactId><version>26.0.0</version></dependency></dependencies><build><plugins>"
                   "<plugin><groupId>com.diffplug.spotless</groupId><artifactId>spotless-maven-plugin</artifactId></plugin>"
                   "</plugins></build></project>")
        deps = self.deps("pom.xml")
        self.assertEqual(deps["org.springframework.boot:spring-boot-starter-parent"], "3.3.0")
        self.assertEqual(deps["com.stripe:stripe-java"], "26.0.0")
        self.assertIn("com.diffplug.spotless:spotless-maven-plugin", deps)

    def test_gradle_reads_coordinates_plugins_and_the_version_catalog_and_flags_android(self):
        self.write("build.gradle.kts", 'plugins { id("com.android.application"); kotlin("android"); id("io.gitlab.arturbosch.detekt") }\n'
                   'dependencies { implementation("io.sentry:sentry-android:7.0.0") }\n')
        self.write("gradle/libs.versions.toml", '[libraries]\nktor = { module = "io.ktor:ktor-server-core", version = "3.0" }\n'
                   'okhttp = "com.squareup.okhttp3:okhttp:4.12.0"\n[plugins]\nktlint = { id = "org.jlleitschuh.gradle.ktlint" }\n')
        (found,) = [m for m in sources.manifests(self.root) if m.path == "build.gradle.kts"]
        self.assertEqual(found.deps["io.sentry:sentry-android"], "7.0.0")
        for name in ("io.gitlab.arturbosch.detekt", "io.ktor:ktor-server-core", "com.squareup.okhttp3:okhttp", "org.jlleitschuh.gradle.ktlint"):
            self.assertIn(name, found.deps)
        self.assertIn("android", found.flags)

    def test_csproj_pubspec_cargo_and_gemfile(self):
        self.write("App.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web"><ItemGroup><PackageReference Include="Stripe.net" Version="45.0.0" />'
                   "</ItemGroup></Project>")
        self.write("pubspec.yaml", "name: a\ndependencies:\n  flutter:\n    sdk: flutter\n  supabase_flutter: ^2.5.0  # auth\n"
                   "dev_dependencies:\n  flutter_lints: ^4.0.0\nflutter:\n  uses-material-design: true\n")
        self.write("Cargo.toml", '[package]\nname = "a"\n[dependencies]\naxum = "0.7"\nserde = { version = "1", features = ["derive"] }\n'
                   "[[bin]]\nname = \"a\"\n")
        self.write("Gemfile", "source 'https://rubygems.org'\ngem 'rails', '~> 7.1'\ngem \"rubocop\"\n")
        self.assertEqual(self.deps("App.csproj"), {"Stripe.net": "45.0.0", "Microsoft.AspNetCore.App": ""})
        self.assertEqual(self.deps("pubspec.yaml"), {"flutter": "", "supabase_flutter": "^2.5.0", "flutter_lints": "^4.0.0"})
        self.assertEqual(self.deps("Cargo.toml"), {"axum": "0.7", "serde": "1"})
        self.assertEqual(self.deps("Gemfile"), {"rails": "~> 7.1", "rubocop": ""})

    def test_a_broken_file_is_a_project_with_no_dependencies_not_a_failure(self):
        self.write("package.json", "{not json")
        self.write("pyproject.toml", "[[[")
        self.write("Cargo.toml", "= =")
        self.assertEqual([m.deps for m in sources.manifests(self.root)], [{}, {}, {}])

    def test_hostile_files_are_empty_projects_and_cannot_hold_setup_up(self):
        import time
        self.write("package.json", "[" * 100000)
        self.write("pyproject.toml", "a = " + "[" * 100000)
        self.write("go.mod", "require " + "a." * 50000 + " v1\n")
        self.write("App.csproj", "<PackageReference " * 20000)
        self.write("pubspec.yaml", "dependencies:\n  a:" + " " * 100000 + "x\n")
        self.write("pom.xml", "<dependency>" * 20000)
        (self.root / ".mcp.json").write_text("[" * 100000, encoding="utf-8")
        started = time.perf_counter()
        found = sources.manifests(self.root)
        self.assertEqual(sources.project_mcp_servers(self.root), [])
        self.assertLess(time.perf_counter() - started, 5)
        self.assertEqual({m.path for m in found}, {"package.json", "pyproject.toml", "go.mod", "App.csproj", "pubspec.yaml", "pom.xml"})
        self.assertEqual({k: v for m in found if m.path in ("package.json", "pyproject.toml", "go.mod") for k, v in m.deps.items()}, {})

    def test_a_directory_named_like_a_manifest_and_a_file_that_is_too_big_are_not_read(self):
        (self.root / "package.json").mkdir()
        self.write("go.mod", "require github.com/stripe/stripe-go v1.0.0\n" + "x" * (sources.MAX_FILE_BYTES + 1))
        self.assertEqual([(m.path, m.deps) for m in sources.manifests(self.root)], [("go.mod", {})])

    def test_go_mod_tool_blocks_are_read(self):
        self.write("go.mod", "module x\n\ntool (\n\tgithub.com/a/b // note\n\t// comment\n\n\tgithub.com/c/d\n)\n\nrequire github.com/e/f v1.0.0\n")
        self.assertEqual(self.deps("go.mod"), {"github.com/a/b": "", "github.com/c/d": "", "github.com/e/f": "v1.0.0"})

    def test_folders_are_read_two_levels_down_and_dependency_folders_never(self):
        self.write("package.json", "{}")
        self.write("api/package.json", "{}")
        self.write("apps/web/package.json", "{}")
        self.write("apps/web/deep/package.json", "{}")
        self.write("node_modules/x/package.json", "{}")
        self.write("api/node_modules/y/package.json", "{}")
        self.write(".hidden/package.json", "{}")
        self.assertEqual([m.path for m in sources.manifests(self.root)], ["package.json", "api/package.json", "apps/web/package.json"])

    def test_files_that_are_not_the_projects_are_skipped(self):
        self.write("package.json", "{}")
        self.write("tests/package.json", "{}")
        self.assertEqual([m.path for m in sources.manifests(self.root, frozenset({"tests/package.json"}))], ["package.json"])


class DetectTest(ProjectCase):
    def sources_of(self, **manifest) -> list[str]:
        self.write("package.json", json.dumps(manifest))
        return [s.service.id for s in sources.detect(self.root, sources.manifests(self.root))]

    def test_a_known_package_gives_its_service_with_the_declared_version(self):
        self.write("package.json", json.dumps({"dependencies": {"@supabase/supabase-js": "^2.45.0"}}))
        (source,) = sources.detect(self.root, sources.manifests(self.root))
        self.assertEqual((source.service.id, source.package, source.version, source.found_in),
                         ("supabase", "@supabase/supabase-js", "^2.45.0", "package.json"))
        self.assertEqual((source.service.docs, source.service.cli), ("https://supabase.com/docs", "supabase"))

    def test_a_package_the_catalog_does_not_know_is_not_guessed(self):
        self.assertEqual(self.sources_of(dependencies={"left-pad": "1", "supabase-lookalike": "1", "stripe-mock-x": "1"}), [])

    def test_a_pattern_matches_a_family_of_packages(self):
        self.assertEqual(self.sources_of(dependencies={"@sentry/react-native": "6", "@aws-sdk/client-s3": "3"}), ["sentry", "aws"])

    def test_the_same_name_in_another_ecosystem_is_another_package(self):
        self.write("go.mod", "module x\n\nrequire github.com/line/line-bot-sdk-go/v8 v8.1.0\n")
        self.write("requirements.txt", "Line_Bot_SDK==3\nstripe\n")
        self.assertEqual([s.service.id for s in sources.detect(self.root, sources.manifests(self.root))], ["stripe", "line"])

    def test_the_catalog_order_is_kept_and_the_projects_own_manifest_wins(self):
        self.write("package.json", json.dumps({"dependencies": {"stripe": "17.0.0"}}))
        self.write("api/package.json", json.dumps({"dependencies": {"stripe": "16.0.0", "express": "5"}}))
        found = {s.service.id: s for s in sources.detect(self.root, sources.manifests(self.root))}
        self.assertEqual(list(found), ["stripe", "express"])
        self.assertEqual((found["stripe"].version, found["express"].found_in), ("17.0.0", "api/package.json"))

    def test_a_file_only_that_service_has_shows_it_when_no_dependency_does(self):
        self.write("supabase/migrations/20261104_create.sql", "select 1;")
        self.write("firebase.json", "{}")
        found = {s.service.id: s for s in sources.detect(self.root, sources.manifests(self.root))}
        self.assertEqual(list(found), ["supabase", "firebase"])
        self.assertEqual((found["supabase"].package, found["supabase"].found_in), ("", "supabase/migrations"))
        text = sources.entry_text(found["supabase"])
        self.assertNotIn("package =", text)
        self.assertEqual(tomllib.loads(text)["supabase"]["cli"], "supabase")
        self.write("package.json", json.dumps({"dependencies": {"@supabase/supabase-js": "2"}}))
        (again,) = [s for s in sources.detect(self.root, sources.manifests(self.root)) if s.service.id == "supabase"]
        self.assertEqual(again.package, "@supabase/supabase-js", "a dependency is the better evidence")

    def test_a_project_mcp_server_of_the_same_name_is_recorded(self):
        self.write(".mcp.json", json.dumps({"mcpServers": {"supabase-local": {"command": "x"}}}))
        self.write("package.json", json.dumps({"dependencies": {"@supabase/supabase-js": "2"}}))
        (source,) = sources.detect(self.root, sources.manifests(self.root))
        self.assertEqual(source.mcp, "supabase-local")
        self.assertIn('mcp = "supabase-local"', sources.entry_text(source))


class CatalogTest(unittest.TestCase):
    def test_every_entry_names_its_official_documentation_and_a_known_ecosystem(self):
        ids = [s.id for s in sources.catalog()]
        self.assertEqual(len(ids), len(set(ids)))
        for s in sources.catalog():
            with self.subTest(service=s.id):
                self.assertRegex(s.id, r"^[a-z][a-z0-9-]*$")
                self.assertRegex(s.docs, r"^https://")
                self.assertIn(s.kind, ("service", "framework"))
                self.assertTrue(s.packages and set(s.packages) <= set(sources.ECOSYSTEMS))
                self.assertTrue(set(s.surfaces) <= {"web", "ios", "android", "api", "cli"})
                if s.plugin:
                    self.assertRegex(s.plugin, r"^[a-z0-9-]+@claude-plugins-official$")

    def test_the_named_services_are_there(self):
        have = {s.id for s in sources.catalog()}
        for wanted in ("supabase", "stripe", "line", "google", "apple", "expo", "firebase", "sentry", "cloudflare", "aws", "resend",
                       "twilio", "revenuecat", "mongodb", "redis", "next", "react", "fastify", "express", "django", "flask", "fastapi",
                       "spring", "ktor"):
            self.assertIn(wanted, have)


class FileTest(ProjectCase):
    def detected(self, **deps) -> list[sources.Source]:
        self.write("package.json", json.dumps({"dependencies": deps}))
        return sources.detect(self.root, sources.manifests(self.root))

    def test_the_file_is_written_and_reads_back(self):
        added, problem = sources.write_missing(self.root, self.detected(stripe="17.0.0", fastify="5.1.0"))
        self.assertEqual((added, problem), (["stripe", "fastify"], None))
        data = tomllib.loads(sources.path_of(self.root).read_text(encoding="utf-8"))
        self.assertEqual(data["stripe"]["docs"], "https://docs.stripe.com")
        self.assertEqual(data["fastify"]["kind"], "framework")
        entries, bad = sources.load(self.root)
        self.assertEqual((list(entries), bad), (["stripe", "fastify"], None))

    def test_an_entry_the_person_edited_or_ignored_is_never_rewritten_and_a_new_one_is_added(self):
        path = sources.path_of(self.root)
        path.parent.mkdir()
        path.write_text('# mine\n[stripe]\nname = "Ours"\n\n[express]\nignore = true\n', encoding="utf-8")
        added, _ = sources.write_missing(self.root, self.detected(stripe="17", express="5", resend="4"))
        self.assertEqual(added, ["resend"])
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith('# mine\n[stripe]\nname = "Ours"\n\n[express]\nignore = true\n'))
        self.assertNotIn("express", sources.load(self.root)[0], "an ignored entry is not offered to anything")
        self.assertEqual(sources.write_missing(self.root, self.detected(stripe="17", express="5", resend="4")), ([], None))

    def test_a_file_that_cannot_be_read_is_left_alone_and_said(self):
        path = sources.path_of(self.root)
        path.parent.mkdir()
        path.write_text("[stripe\n", encoding="utf-8")
        added, problem = sources.write_missing(self.root, self.detected(stripe="17"))
        self.assertEqual(added, [])
        self.assertIn("could not be read", problem)
        self.assertEqual(path.read_text(encoding="utf-8"), "[stripe\n")
        entries, bad = sources.load(self.root)
        self.assertEqual((entries, bool(bad)), ({}, True))

    def test_no_string_a_manifest_can_hold_ends_the_toml_string_or_adds_a_key(self):
        for value in ('a"b', "a\\b", "line\nbreak", "tab\there", "del\x7fchar", 'x"\nevil = 1\n[other]', "nul\x00", "\x1b[0m",
                      "bad\udcff", "日本語", " "):
            with self.subTest(value=value):
                (read,) = tomllib.loads("v = " + sources.toml_string(value) + "\n").values()
                self.assertEqual(read, value.replace("\udcff", "�"))

    def test_a_package_name_with_control_characters_is_written_and_reads_back(self):
        source = sources.Source(sources.catalog()[0], "pkg\x7f\x1b", "1\n2", "package.json")
        added, problem = sources.write_missing(self.root, [source])
        self.assertEqual((added, problem), (["supabase"], None))
        self.assertEqual(sources.load(self.root)[0]["supabase"]["package"], "pkg\x7f\x1b")

    def test_a_sources_file_in_another_encoding_is_left_alone_and_said(self):
        path = sources.path_of(self.root)
        path.parent.mkdir()
        path.write_bytes('[stripe]\nname = "Caf\xe9"\n'.encode("cp1252"))
        added, problem = sources.write_missing(self.root, self.detected(resend="4"))
        self.assertEqual(added, [])
        self.assertIn("could not be read", problem)
        self.assertEqual(sources.load(self.root)[0], {})

    def test_a_value_with_a_quote_cannot_break_the_file(self):
        source = sources.Source(sources.catalog()[0], 'pkg"\nx = 1', 'v"1', "package.json")
        self.assertEqual(tomllib.loads(sources.entry_text(source))[source.service.id]["package"], 'pkg"\nx = 1')
        self.assertTrue(re.fullmatch(r"\[supabase\]\n(name|docs|package|version|cli|plugin|mcp|kind|found_in) = .*\n(?s:.*)",
                                     sources.entry_text(source)))
