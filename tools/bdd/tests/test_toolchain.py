"""The quality checks, design table and surfaces `bdd init` records from a project's own files."""
import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from bddlib import config as cfg
from bddlib import sources, toolchain


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()

    def write(self, rel: str, text: str = "") -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def checks(self) -> dict[str, toolchain.Check]:
        return {c.name: c for c in toolchain.proposed_checks(self.root, sources.manifests(self.root))}


class QualityTest(ProjectCase):
    def test_a_python_project_gets_only_the_tools_it_declares(self):
        self.write("pyproject.toml", '[project]\nname = "x"\ndependencies = []\n[dependency-groups]\ndev = ["ruff", "mypy"]\n')
        found = self.checks()
        self.assertEqual(list(found), ["ruff", "ruff-format", "mypy"])
        self.assertEqual(found["mypy"].command, "{project_python} -m mypy .")
        self.assertEqual(found["ruff"].command, "{project_python} -m ruff check .")

    def test_the_adapters_own_test_folder_is_left_out_of_the_tools_that_can_leave_a_folder_out(self):
        self.write("pyproject.toml", '[project]\nname = "x"\n[dependency-groups]\ndev = ["ruff", "mypy", "flake8", "black"]\n')
        found = {c.name: c.command for c in toolchain.proposed_checks(self.root, sources.manifests(self.root), ("tests",))}
        self.assertEqual(found["ruff"], "{project_python} -m ruff check . --extend-exclude tests")
        self.assertEqual(found["ruff-format"], "{project_python} -m ruff format --check . --extend-exclude tests")
        self.assertEqual(found["mypy"], "{project_python} -m mypy . --exclude ^tests/")
        self.assertEqual(found["flake8"], "{project_python} -m flake8 . --extend-exclude tests")
        self.assertEqual(found["black"], "{project_python} -m black --check . --extend-exclude /tests/")
        self.assertEqual(self.checks()["mypy"].command, "{project_python} -m mypy .", "nothing is left out without an adapter")

    def test_a_folder_below_the_project_leaves_out_only_the_adapter_folder_inside_it(self):
        self.write("api/package.json", json.dumps({"devDependencies": {"eslint": "9"}}))
        self.write("api/eslint.config.js", "")
        for owned, expected in ((("tests",), "npx --no-install eslint ."), (("api/tests",), "npx --no-install eslint . --ignore-pattern tests")):
            with self.subTest(owned=owned):
                (check,) = toolchain.proposed_checks(self.root, sources.manifests(self.root), owned)
                self.assertEqual(check.command, expected)

    def test_a_tsconfig_that_does_not_leave_the_adapters_folder_out_is_said(self):
        self.write("package.json", json.dumps({"devDependencies": {"typescript": "5"}}))
        self.write("tsconfig.json", '{"compilerOptions": {"strict": true}}')
        checks = list(self.checks().values())
        (note,) = toolchain.overlap_notes(self.root, checks, ("tests",))
        self.assertIn('add "tests" to its exclude', note)
        self.write("tsconfig.json", '{"exclude": ["tests", "node_modules"]}')
        self.assertEqual(toolchain.overlap_notes(self.root, checks, ("tests",)), [])
        self.assertEqual(toolchain.overlap_notes(self.root, checks, ()), [])

    def test_the_folder_of_each_adapters_own_tests_is_the_one_its_files_share(self):
        adapters = {"adapters": [{"features": "tests/features", "steps": "tests/steps", "drivers": "tests/drivers"},
                                 {"root": "web", "features": "tests/features", "steps": "tests/steps"},
                                 {"features": "src/test/resources/features", "steps": "src/test/java/steps"},
                                 {"features": "features"}, {"name": "no paths"}]}
        self.assertEqual(toolchain.owned_folders(adapters), ("tests", "web/tests"))
        self.assertEqual(toolchain.owned_folders({}), ())

    def test_a_python_tool_with_only_a_config_file_is_not_proposed_because_nothing_says_it_is_installed(self):
        self.write("pyproject.toml", "[tool.black]\nline-length = 100\n[tool.ruff]\nline-length = 100\n")
        self.write("mypy.ini", "[mypy]\n")
        self.write("Gemfile", "source 'x'\n")
        self.write(".rubocop.yml", "")
        self.assertEqual(self.checks(), {})

    def test_golangci_lint_declared_in_go_mod_runs_through_go_and_one_with_only_its_config_runs_from_the_path(self):
        self.write("go.mod", "module x\n\ngo 1.24\n\ntool (\n\tgithub.com/golangci/golangci-lint/cmd/golangci-lint\n\texample.com/other/tool\n)\n")
        self.write(".golangci.yml", "version: 2\n")
        self.assertEqual(self.checks()["golangci-lint"].command, "go tool golangci-lint run ./...")
        self.write("go.mod", "module x\n")
        self.assertEqual(self.checks()["golangci-lint"].command, "golangci-lint run ./...")
        (self.root / ".golangci.yml").unlink()
        self.assertEqual(list(self.checks()), ["gofmt", "go-vet"])

    def test_each_kotlin_plugin_gets_the_task_it_defines(self):
        self.write("gradlew", "")
        self.write("build.gradle.kts", 'plugins { id("org.jmailen.kotlinter") }\ndependencies { implementation("com.pinterest.ktlint:ktlint-core:1.0") }\n')
        self.assertEqual({n: c.command for n, c in self.checks().items()}, {"kotlinter": "./gradlew -q lintKotlin"})
        self.write("build.gradle.kts", 'plugins { id("org.jlleitschuh.gradle.ktlint") }\n')
        self.assertEqual({n: c.command for n, c in self.checks().items()}, {"ktlint": "./gradlew -q ktlintCheck"})

    def test_a_name_is_never_longer_than_the_config_allows_and_two_folders_never_share_one(self):
        for folder in ("services/notifications-email", "services/notifications-sms", "services/billing"):
            self.write(f"{folder}/pyproject.toml", '[project]\nname = "x"\n[dependency-groups]\ndev = ["ruff"]\n')
        self.write("dart/pubspec.yaml", "name: a\n")
        self.write("dotnet/App.csproj", "<Project />")
        names = [c.name for c in toolchain.proposed_checks(self.root, sources.manifests(self.root))]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", n) for n in names), names)
        self.assertEqual(len([n for n in names if n.startswith("ruff-format")]), 3, "no check is dropped for a long or equal name")
        lines = "\n".join(f"[adapters.quality.{n}]\ncommand = 'x'\n" for n in names)
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "f"\n' + lines)
        self.assertEqual([c.name for c in cfg.load(self.root).quality.checks], names)

    def test_a_folder_the_config_cannot_name_is_not_given_a_check(self):
        for folder in ("a:b", "ok"):
            try:
                self.write(f"{folder}/go.mod", "module x\n")
            except OSError:
                self.skipTest("this file system has no folder called a:b")
        self.assertEqual({c.cwd for c in self.checks().values()}, {"ok"})

    def test_a_tool_that_checks_a_whole_folder_is_not_proposed_where_the_locked_tests_sit_inside_it(self):
        self.write("package.json", json.dumps({"devDependencies": {"prettier": "3"}}))
        found = sources.manifests(self.root)
        self.assertEqual(list(self.checks()), ["prettier"])
        self.assertEqual(toolchain.proposed_checks(self.root, found, ("tests",)), [])
        (note,) = toolchain.skipped_for_overlap(self.root, found, ("tests",))
        self.assertIn("prettier is not recorded for the project", note)
        self.assertEqual(toolchain.skipped_for_overlap(self.root, found, ()), [])

    def test_a_check_for_a_tool_that_leaves_a_folder_out_never_has_a_word_the_windows_launchers_refuse(self):
        from bddlib import runner
        self.write("package.json", json.dumps({"devDependencies": {"eslint": "9", "prettier": "3", "typescript": "5"}}))
        self.write("eslint.config.js", "")
        self.write("tsconfig.json", "{}")
        for check in toolchain.proposed_checks(self.root, sources.manifests(self.root), ("tests",)):
            for word in check.command.split():
                self.assertFalse(set(word) & set(runner.CMD_METACHARACTERS), (check.name, word))

    def test_a_tool_table_or_config_file_that_is_not_a_dependency_is_not_a_declaration(self):
        self.write("requirements.txt", "import-linter\n")
        self.write(".importlinter", "[importlinter]\nroot_package = x\n")
        self.assertEqual(list(self.checks()), ["import-linter"])
        (self.root / "requirements.txt").unlink()
        self.assertEqual(self.checks(), {})

    def test_import_linter_needs_its_contracts_and_a_tool_without_them_is_not_proposed(self):
        self.write("requirements.txt", "import-linter\n")
        self.assertEqual(self.checks(), {})
        self.write(".importlinter", "[importlinter]\nroot_package = x\n")
        self.assertIn("import-linter", self.checks())
        self.assertIn("lint_imports_command", self.checks()["import-linter"].command)

    def test_a_node_project_gets_tsc_eslint_and_dependency_cruiser_only_with_their_config(self):
        self.write("package.json", json.dumps({"devDependencies": {"typescript": "5", "eslint": "9", "dependency-cruiser": "16"}}))
        self.assertEqual(self.checks(), {})
        self.write("tsconfig.json", "{}")
        self.write("eslint.config.js", "export default []\n")
        self.write(".dependency-cruiser.cjs", "module.exports = {}\n")
        self.write("src/index.ts", "")
        found = self.checks()
        self.assertEqual([(n, c.command) for n, c in found.items()],
                         [("tsc", "npx --no-install tsc --noEmit"), ("eslint", "npx --no-install eslint ."),
                          ("dependency-cruiser", "npx --no-install depcruise src")])

    def test_the_package_manager_the_project_uses_starts_the_tool(self):
        self.write("package.json", json.dumps({"devDependencies": {"typescript": "5"}, "packageManager": "pnpm@9"}))
        self.write("tsconfig.json", "{}")
        self.assertEqual(self.checks()["tsc"].command, "pnpm exec tsc --noEmit")
        self.write("package.json", json.dumps({"devDependencies": {"typescript": "5"}}))
        self.write("yarn.lock", "")
        self.assertEqual(self.checks()["tsc"].command, "yarn tsc --noEmit")

    def test_a_folder_below_the_project_runs_its_checks_in_that_folder(self):
        self.write("api/package.json", json.dumps({"devDependencies": {"typescript": "7"}}))
        self.write("api/tsconfig.json", "{}")
        self.write("api/pnpm-lock.yaml", "")
        (check,) = self.checks().values()
        self.assertEqual((check.name, check.cwd, check.command), ("tsc", "api", "pnpm exec tsc --noEmit"))

    def test_the_same_tool_in_two_folders_gets_the_folders_name(self):
        for folder in ("api", "web"):
            self.write(f"{folder}/package.json", json.dumps({"devDependencies": {"typescript": "7"}}))
            self.write(f"{folder}/tsconfig.json", "{}")
        self.assertEqual(list(self.checks()), ["tsc-api", "tsc-web"])

    def test_a_go_module_gets_the_toolchain_and_a_linter_only_when_it_has_its_config(self):
        self.write("go.mod", "module x\n\ngo 1.24\n")
        found = self.checks()
        self.assertEqual(list(found), ["gofmt", "go-vet"])
        self.assertTrue(found["gofmt"].fail_on_output and not found["go-vet"].fail_on_output)
        self.write(".golangci.yml", "version: 2\n")
        self.assertEqual(list(self.checks()), ["gofmt", "go-vet", "golangci-lint"])

    def test_kotlin_and_java_tools_need_the_build_that_runs_them(self):
        self.write("build.gradle.kts", 'plugins { id("org.jlleitschuh.gradle.ktlint"); id("io.gitlab.arturbosch.detekt") }\n')
        self.assertEqual(self.checks(), {}, "no gradlew, no way to run them")
        self.write("gradlew", "")
        self.assertEqual(list(self.checks()), ["ktlint", "detekt"])
        self.write("pom.xml", "<project><build><plugins><plugin><groupId>com.diffplug.spotless</groupId>"
                   "<artifactId>spotless-maven-plugin</artifactId></plugin></plugins></build></project>")
        self.assertIn("spotless", self.checks())

    def test_dart_rust_dotnet_and_ruby(self):
        self.write("pubspec.yaml", "name: a\ndependencies:\n  flutter:\n    sdk: flutter\n")
        self.write("Cargo.toml", '[package]\nname = "a"\n')
        self.write("App.csproj", "<Project />")
        self.write("Gemfile", "gem 'rubocop'\n")
        self.assertEqual(sorted(self.checks()), ["cargo-fmt", "clippy", "dart-format", "dotnet-format", "flutter-analyze", "rubocop"])

    def test_nothing_is_proposed_for_a_project_that_declares_nothing(self):
        self.write("package.json", json.dumps({"dependencies": {"express": "5"}}))
        self.assertEqual(self.checks(), {})

    def test_the_text_reads_back_as_quality_tables_of_the_last_adapter(self):
        self.write("go.mod", "module x\n")
        text = ('[[adapters]]\nname = "go-godog"\nfeatures = "tests/features"\n\n[lint]\nignore = []\n'
                + toolchain.quality_text(list(self.checks().values())))
        quality = tomllib.loads(text)["adapters"][0]["quality"]
        self.assertEqual(quality["gofmt"], {"command": "gofmt -l .", "fail_on_output": True})
        self.write(".bdd/config.toml", text)
        self.assertEqual([c.name for c in cfg.load(self.root).quality.checks], ["gofmt", "go-vet"])

    def test_a_command_with_both_kinds_of_quote_still_reads_back(self):
        check = toolchain.Check("odd", "tool 'a' \"b\"", "", False)
        self.assertEqual(tomllib.loads(toolchain.quality_text([check]).replace("[adapters.quality.odd]", "[odd]"))["odd"]["command"],
                         "tool 'a' \"b\"")


class DesignTest(ProjectCase):
    def test_a_design_folder_with_a_system_file_and_an_inventory(self):
        self.write("design/DESIGN.md")
        self.write("design/inventory.md")
        self.write("design/screens/home.html")
        design = toolchain.find_design(self.root)
        self.assertEqual(design, cfg.Design("design/DESIGN.md", "design/screens/*", "design/inventory.md"))
        self.assertEqual(toolchain.design_summary(design), "design/DESIGN.md, design/screens/*, design/inventory.md")
        self.assertEqual(tomllib.loads(toolchain.design_text(design))["design"]["screens"], "design/screens/*")

    def test_either_file_is_enough_and_screens_alone_are_not(self):
        self.write("design/Inventory.MD")
        self.assertEqual(toolchain.find_design(self.root), cfg.Design("", "", "design/Inventory.MD"))
        (self.root / "design" / "Inventory.MD").unlink()
        self.write("design/screens/home.html")
        self.assertIsNone(toolchain.find_design(self.root))

    def test_no_design_folder_records_nothing(self):
        self.assertIsNone(toolchain.find_design(self.root))
        self.assertEqual(toolchain.design_summary(None), "none found")


class SurfaceTest(ProjectCase):
    def surfaces(self) -> list[str]:
        found = sources.manifests(self.root)
        return toolchain.detect_surfaces(self.root, found, sources.detect(self.root, found))

    def test_frameworks_files_and_libraries_show_the_surfaces(self):
        self.write("package.json", json.dumps({"dependencies": {"expo": "52", "fastify": "5", "next": "15", "commander": "12"}}))
        self.assertEqual(self.surfaces(), ["web", "ios", "android", "api", "cli"])

    def test_an_android_gradle_app_and_an_xcode_project(self):
        self.write("build.gradle.kts", 'plugins { id("com.android.application") }\n')
        self.write("ios/App.xcodeproj/project.pbxproj")
        self.assertEqual(self.surfaces(), ["ios", "android"])

    def test_nothing_shown_is_nothing_claimed(self):
        self.write("go.mod", "module x\n")
        self.assertEqual(self.surfaces(), [])

    def test_a_surface_is_verified_by_a_configured_adapter_and_otherwise_unverified(self):
        assessed = toolchain.assess(["web", "ios", "api"], ["ts-cucumber-js"], ["ts-cucumber-js", "ts-playwright-bdd"])
        self.assertEqual([(s.name, s.verified_by, s.could_be) for s in assessed],
                         [("web", "unverified", ("ts-playwright-bdd",)), ("ios", "unverified", ()),
                          ("api", "ts-cucumber-js", ())])
        self.assertEqual(tomllib.loads(toolchain.surfaces_text(assessed))["surfaces"],
                         {"web": "unverified", "ios": "unverified", "api": "ts-cucumber-js"})

    def test_an_adapter_that_does_not_fit_the_project_is_not_offered(self):
        (surface,) = toolchain.assess(["android"], [], [])
        self.assertEqual(surface.could_be, ())

    def test_the_words_for_each_unverified_surface(self):
        assessed = toolchain.assess(["web", "ios", "android"], ["ts-cucumber-js"], ["ts-playwright-bdd"])
        lines = toolchain.unverified_lines(assessed, ["ts-cucumber-js"])
        self.assertEqual(lines[0], "mobile screens: no adapter, recorded as unverified")
        self.assertTrue(lines[1].startswith("web screens: not checked by ts-cucumber-js; ts-playwright-bdd covers web"))
        self.assertEqual(len(lines), 2)
        (only_ios,) = toolchain.unverified_lines(toolchain.assess(["ios"], [], []), [])
        self.assertEqual(only_ios, "ios screens: no adapter, recorded as unverified")

    def test_status_never_fails_for_an_adapter_greenlight_does_not_ship_or_one_without_a_name(self):
        self.write(".bdd/config.toml", '[surfaces]\nios = "unverified"\n\n[[adapters]]\nfeatures = "f"\n[adapters.run]\nby_tag = "x"\n'
                   'report = "y"\n\n[[adapters]]\nname = "our-own"\nfeatures = "g"\n[adapters.run]\nby_tag = "x"\nreport = "y"\n')
        self.assertEqual(toolchain.unverified(cfg.load(self.root)), ["ios"])
        self.assertEqual(toolchain.adapter_surfaces(""), ())

    def test_every_adapter_says_which_surfaces_it_covers(self):
        from bddlib import adapter
        for name in adapter.available():
            with self.subTest(adapter=name):
                self.assertTrue(set(toolchain.adapter_surfaces(name)) <= set(cfg.SURFACES))
        self.assertEqual(toolchain.adapter_surfaces("ts-playwright-bdd"), ("web",))

    def test_a_recorded_surface_stays_unverified_until_an_adapter_covers_it(self):
        self.write(".bdd/config.toml", '[surfaces]\nweb = "unverified"\nios = "unverified"\n')
        self.assertEqual(toolchain.unverified(cfg.load(self.root)), ["web", "ios"])
        self.write(".bdd/config.toml", '[surfaces]\nweb = "unverified"\nios = "unverified"\n\n[[adapters]]\nname = "ts-playwright-bdd"\n'
                   'features = "f"\n[adapters.run]\nby_tag = "x"\nreport = "y"\n')
        self.assertEqual(toolchain.unverified(cfg.load(self.root)), ["ios"])


class ConfigTablesTest(ProjectCase):
    def load(self, text: str) -> cfg.Config:
        self.write(".bdd/config.toml", text)
        return cfg.load(self.root)

    def test_design_and_surfaces_are_read(self):
        config = self.load('[design]\nsystem = "design/DESIGN.md"\nscreens = "design/screens/*"\n\n'
                           '[surfaces]\nweb = "ts-playwright-bdd"\nios = "unverified"\n')
        self.assertEqual(config.design, cfg.Design("design/DESIGN.md", "design/screens/*", ""))
        self.assertEqual(config.surfaces, (("web", "ts-playwright-bdd"), ("ios", "unverified")))
        self.assertEqual(config.warnings, ())

    def test_a_project_without_the_tables_has_neither_and_no_warning(self):
        config = self.load('autonomy = "guided"\n')
        self.assertEqual((config.design, config.surfaces, config.warnings), (None, (), ()))

    def test_a_malformed_design_table_is_ignored_with_a_warning_and_never_a_config_error(self):
        for text, kept in (('design = "x"\n', None),
                           ('[design]\nsystem = 3\n', None),
                           ('[design]\nsystem = "/etc/passwd"\n', None),
                           ('[design]\nsystem = "../x/DESIGN.md"\n', None),
                           ('[design]\nsystem = "C:/x/DESIGN.md"\n', None),
                           ('[design]\ncolour = "design/x.md"\n', None),
                           ('[design]\nsystem = "design/DESIGN.md"\ncolour = "x"\n', cfg.Design("design/DESIGN.md"))):
            with self.subTest(text=text):
                config = self.load(text)
                self.assertEqual(config.design, kept)
                self.assertTrue(config.warnings and "ignored" in config.warnings[0])

    def test_a_malformed_surfaces_table_is_ignored_with_a_warning(self):
        config = self.load('[surfaces]\nweb = 3\ntv = "unverified"\nios = "unverified"\n')
        self.assertEqual(config.surfaces, (("ios", "unverified"),))
        self.assertEqual(len(config.warnings), 2)
        self.assertEqual(self.load('surfaces = 3\n').surfaces, ())
