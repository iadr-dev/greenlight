import contextlib
import io
import os

from bddlib import designreview, designsections, docsrecord, guard, reviewlog, sources, state
from bddlib.errors import UsageError

from tests.helpers import TECHNICAL_DESIGN, ProjectCase

INVENTORY = ("| ID | Screen | States | Feature | File | Fields |\n|---|---|---|---|---|---|\n"
             "| O-ST-01 | Company profile | loading, saved, error | FEAT-007 | screens/home.html | name, contact phone |\n")
RULES = "R-007.1 A company has a name.\nR-007.2 A company has a contact phone.\n"
COMPLETE = {
    "Design trace": ("| O-ST-01 Company profile | name | R-007.1 | company.name | TextField |\n"
                     "| O-ST-01 Company profile | contact phone | R-007.2 | company.phone | PhoneInput |\n"),
    "Building blocks": ("| name | text | plain text, 1 to 120 characters | none | - | https://developer.mozilla.org/x |\n"
                        "| contact phone | phone | E.164 | libphonenumber-js | npm:libphonenumber-js | https://gitlab.com/x |\n"),
    "External services": "| supabase | update the companies row | 500 a second | in the plan | keep the form, say not saved |\n",
    "Architecture": "| company profile service | service | src/company/service.ts |\n",
    "Patterns": "| form with server validation | src/orders/form.ts | the profile form |\n",
    "API contract": "| PATCH /company | name, phone | 200 with the company | v1 | unchanged |\n",
    "Data and performance": ("| migration | add companies.phone | varchar(16) | - | - | drop the column |\n"
                             "| query | company by owner | where owner_id = ? | companies_owner_idx | - | - |\n"
                             "| operation | PATCH /company | one row | - | p95 under 200 ms | - |\n"),
    "Security and privacy": ("| authorisation | PATCH /company | an owner of that company | the service |\n"
                             "| rate limit | PATCH /company | 30 a minute per user | the gateway |\n"),
    "Errors and resilience": "| the network is down | Not saved, try again | the PATCH is safe to repeat |\n",
    "State and offline": "| O-ST-01 | loading, saved, error | the form | Save waits for the network |\n",
    "Accessibility and language": "| O-ST-01 | every field labelled | the tokens | strings in the catalogue |\n",
    "Observability": "| company.updated | log | a save, without the phone |\n",
    "Configuration and delivery": "| SUPABASE_URL | one per environment | before the deploy |\n",
    "Test strategy": "| unit | the phone parsing | src/company/phone.test.ts |\n",
}


def design(**changed: str | None) -> str:
    """The complete design with some sections' rows replaced (None leaves the section out)."""
    parts = ["# Design\n\n```mermaid\nflowchart LR\n  a --> b\n```\n\n"]
    for section in designsections.SECTIONS:
        key = section.name.replace(" ", "_").casefold()
        rows = changed.get(key, COMPLETE[section.name])
        if rows is not None:
            parts.append(f"## {section.name}\n{section.header}\n|{'---|' * len(section.columns)}\n{rows}\n")
    return "".join(parts)


class SectionsCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.config(tail='\n[design]\ninventory = "design/inventory.md"\n')
        self.write("design/inventory.md", INVENTORY)
        self.rules.write_text(RULES, encoding="utf-8", newline="\n")
        self.write("src/orders/form.ts", "export const form = {};\n")
        docsrecord.add_evidence(self.root, self.feature_dir, "supabase", "https://supabase.com/docs/reference", None, None, None)

    def codes(self, text: str) -> list[str]:
        self.write_technical_design(text)
        return [i.code for i in designsections.check(self.root, self.feature_dir, "FEAT-007")]

    def messages(self, text: str) -> str:
        self.write_technical_design(text)
        return "\n".join(str(i) for i in designsections.check(self.root, self.feature_dir, "FEAT-007"))


class SectionTest(SectionsCase):
    """One passing and one failing case per section."""

    def test_the_complete_design_passes(self):
        self.assertEqual(self.codes(design()), [])

    def test_a_design_where_nothing_applies_passes_with_a_reason_per_section(self):
        self.write("design/inventory.md", INVENTORY.replace("FEAT-007", "FEAT-008"))
        self.assertEqual(self.codes(TECHNICAL_DESIGN), [])

    def test_design_trace(self):
        self.assertIn("TD10", self.codes(design(design_trace="| - | contact phone | R-007.2 | company.phone | - |\n")))
        self.assertIn("TD11", self.codes(design(design_trace=COMPLETE["Design trace"].splitlines()[0] + "\n")))
        self.assertIn("TD12", self.codes(design(design_trace=COMPLETE["Design trace"].replace("R-007.2", "R-007.9"))))
        self.assertIn("TD13", self.codes(design(design_trace=COMPLETE["Design trace"] + "| O-ST-01 | Save | R-007.1 | - | - |\n")))

    def test_building_blocks(self):
        message = self.messages(design(building_blocks=COMPLETE["Building blocks"].splitlines()[0] + "\n"))
        self.assertIn('field "contact phone" has no building block', message)
        free_text = COMPLETE["Building blocks"].replace("| phone | E.164 |", "| text | free text, 40 characters |")
        self.assertIn('"contact phone" is a phone number: its standard is E.164', self.messages(design(building_blocks=free_text)))
        self.assertIn("a version file is not documentation",
                      self.messages(design(building_blocks=COMPLETE["Building blocks"].replace("https://gitlab.com/x", "package.json"))))
        self.assertIn("TD23", self.codes(design(building_blocks=COMPLETE["Building blocks"].replace("npm:", "node "))))

    def test_a_standard_is_asked_for_by_kind_and_by_name(self):
        for kind, name, standard in (("money", "price", "ISO 4217"), ("text", "country", "ISO 3166"),
                                     ("time zone", "zone", "IANA"), ("text", "start date", "ISO 8601"),
                                     ("locale", "language", "BCP 47")):
            with self.subTest(kind=kind, name=name):
                found = designsections.standard_of(kind, name)
                self.assertEqual(found.token if found else None, standard)
        self.assertIsNone(designsections.standard_of("url", "website"))
        self.assertIsNone(designsections.standard_of("text", "company name"))

    def test_external_services(self):
        self.assertEqual(self.codes(design()), [])
        message = self.messages(design(external_services=COMPLETE["External services"].replace("supabase", "stripe")))
        self.assertIn("the call to stripe has no evidence on record", message)

    def test_architecture(self):
        self.write(".bdd/architecture.md", "# Architecture\n\n## Layers\nscreen, service, data\n")
        self.assertEqual(self.codes(design()), [])
        self.assertIn("TD40", self.codes(design(architecture="| profile | domain | src/x.ts |\n")))

    def test_patterns(self):
        self.assertIn("TD50", self.codes(design(patterns="| form | src/orders/missing.ts | the form |\n")))
        self.assertIn("TD50", self.codes(design(patterns="| form | ../outside.ts | the form |\n")))

    def test_api_contract(self):
        endpoint = COMPLETE["API contract"] + "| GET /company | - | the company | v1 | unchanged |\n"
        codes = self.codes(design(api_contract=endpoint))
        self.assertIn("TD64", codes)
        self.assertIn("TD70", codes)

    def test_data_and_performance(self):
        rows = COMPLETE["Data and performance"]
        self.assertIn('query "company by owner" has no index',
                      self.messages(design(data_and_performance=rows.replace("companies_owner_idx", "-"))))
        self.assertIn("TD62", self.codes(design(data_and_performance=rows.replace("p95 under 200 ms", "none"))))
        self.assertIn("TD63", self.codes(design(data_and_performance=rows.replace("drop the column", "-"))))
        self.assertIn("TD60", self.codes(design(data_and_performance=rows + "| view | x | y | - | - | - |\n")))

    def test_security_and_privacy(self):
        rows = COMPLETE["Security and privacy"]
        self.assertIn("endpoint PATCH /company has no authorisation row",
                      self.messages(design(security_and_privacy=rows.splitlines()[1] + "\n")))
        self.assertIn("TD71", self.codes(design(security_and_privacy=rows.splitlines()[0] + "\n")))
        self.assertIn("TD72", self.codes(design(security_and_privacy=rows + "| vibes | x | y | z |\n")))

    def test_errors_and_resilience(self):
        self.assertIn("TD4", self.codes(design(errors_and_resilience="| the network is down | - | the PATCH is safe |\n")))

    def test_state_and_offline(self):
        message = self.messages(design(state_and_offline="| O-ST-01 | loading, saved | the form | waits |\n"))
        self.assertIn('screen O-ST-01 (Company profile) does not list its state "error"', message)
        self.assertIn("TD80", self.codes(design(state_and_offline="| n/a | no state is kept anywhere | | |\n")))

    def test_accessibility_and_language(self):
        self.assertIn("TD82", self.codes(design(accessibility_and_language="| O-ST-99 | a | b | c |\n")))

    def test_observability(self):
        self.assertIn("Observability: the section holds no row",
                      self.messages(design(observability="| n/a | | |\n")))

    def test_configuration_and_delivery(self):
        self.assertIn("TD1", self.codes(design(configuration_and_delivery=None)))

    def test_test_strategy(self):
        self.write_technical_design(design().replace("| Level | What it tests | Where |", "| Level | What |"))
        self.assertIn("TD2", [i.code for i in designsections.check(self.root, self.feature_dir, "FEAT-007")])

    def test_the_messages_name_the_section_and_the_row(self):
        self.assertIn("design.md:", self.messages(design(errors_and_resilience="| down | - | safe |\n")))
        self.assertIn('Errors and resilience: row "down" has nothing under "The user sees"',
                      self.messages(design(errors_and_resilience="| down | - | safe |\n")))


class ScreensTest(SectionsCase):
    def test_the_rows_of_the_feature_with_their_fields(self):
        rows = designsections.screens_of(self.root, "FEAT-007")
        self.assertEqual([(r.id, r.fields) for r in rows], [("O-ST-01", ("name", "contact phone"))])
        self.assertEqual(designsections.screens_of(self.root, "FEAT-008"), [])


class InstallTest(SectionsCase):
    def test_a_package_the_project_does_not_declare_is_one_line_for_the_person(self):
        self.write_technical_design(design())
        self.write("package.json", '{"packageManager": "pnpm@9.0.0", "dependencies": {"next": "16.4.5"}}')
        self.assertEqual(designsections.install_problems(self.root, self.feature_dir),
                         ["libphonenumber-js (npm) is not a dependency of the project: the person types ! pnpm add "
                          "libphonenumber-js (an agent may not install packages)"])
        self.write("package.json", '{"dependencies": {"libphonenumber-js": "^1.11.0"}}')
        self.assertEqual(designsections.install_problems(self.root, self.feature_dir), [])

    def test_the_line_follows_the_tools_of_the_manifest(self):
        def line(ecosystem: str, files: set[str] = frozenset(), flags: set[str] = frozenset(), folder: str = "",
                 deps: dict | None = None) -> str:
            found = sources.Manifest("x", folder, ecosystem, deps or {}, frozenset(flags), frozenset(files))
            return designsections.install_line(found, ecosystem, "lib")
        self.assertEqual(line("npm"), "npm install lib")
        self.assertEqual(line("npm", files={"yarn.lock"}), "yarn add lib")
        self.assertEqual(line("npm", folder="apps/web", flags={"pm:pnpm"}), "cd apps/web && pnpm add lib")
        self.assertEqual(line("pypi", files={"uv.lock"}), "uv add lib")
        self.assertEqual(line("pypi"), "python -m pip install lib")
        self.assertEqual(line("pub", deps={"flutter": ""}), "flutter pub add lib")
        self.assertEqual(line("cargo"), "cargo add lib")
        self.assertIn("has no add command", line("maven"))
        self.assertEqual(designsections.install_line(None, "go", "lib"), "go get lib")

    def test_the_gates_before_and_at_implement_name_it(self):
        self.write_technical_design(design())
        from bddlib import gates
        for gate in ("tasks", "implement"):
            with self.subTest(gate=gate):
                problems = gates.gate_problems(self.root, self.feature_dir, state.load(self.feature_dir), gate)
                self.assertTrue(any("npm install libphonenumber-js" in p for p in problems), problems)
        self.make_old_feature()
        problems = gates.gate_problems(self.root, self.feature_dir, state.load(self.feature_dir), "implement")
        self.assertFalse(any("npm install" in p for p in problems), "a feature from before has no new gate")

    HOSTILE = ("npm:left pad", "npm:x;rm -rf ~", "npm:x&&curl evil", "npm:$(curl evil)", "npm:`id`", "npm:x\ny",
               "npm:--registry=https://evil.example", "npm:git+https://evil.example/x.git", "npm:../x", "npm:x@1.2.3",
               "pypi:-e .", "go:../../x", "cargo:x y", "pub:X", "maven:group", "npm:https://evil.example/x.tgz")

    def test_a_package_name_that_is_not_a_plain_name_is_refused_and_never_printed(self):
        for cell in self.HOSTILE:
            with self.subTest(cell=cell):
                with self.assertRaises(ValueError):
                    designsections.parse_package(cell)
                one_line = cell.replace("\n", " ")
                rows = COMPLETE["Building blocks"].replace("npm:libphonenumber-js", one_line)
                self.write_technical_design(design(building_blocks=rows))
                self.assertIn("TD23", [i.code for i in designsections.check(self.root, self.feature_dir, "FEAT-007")])
                problems = designsections.install_problems(self.root, self.feature_dir)
                self.assertTrue(problems, "an unreadable package cell is a problem at the gate, not a pass")
                self.assertFalse(any(one_line.split(":", 1)[1] in p for p in problems), problems)
        for cell, parsed in (("npm:@scope/pkg", ("npm", "@scope/pkg")), ("pypi:phone_numbers", ("pypi", "phone_numbers")),
                             ("go:github.com/nyaruka/phonenumbers", ("go", "github.com/nyaruka/phonenumbers")),
                             ("maven:com.googlecode.libphonenumber:libphonenumber", ("maven", "com.googlecode.libphonenumber:libphonenumber")),
                             ("pub:phone_numbers_parser", ("pub", "phone_numbers_parser")), ("-", None)):
            with self.subTest(cell=cell):
                self.assertEqual(designsections.parse_package(cell), parsed)

    def test_the_printed_line_quotes_what_it_names(self):
        found = sources.Manifest("x", "apps/my web", "npm", {}, frozenset({"pm:pnpm"}), frozenset())
        self.assertEqual(designsections.install_line(found, "npm", "@scope/pkg"), "cd 'apps/my web' && pnpm add @scope/pkg")

    def test_an_agent_may_not_install_it(self):
        refused = guard.evaluate({"tool_name": "Bash", "cwd": str(self.root), "agent_type": "greenlight:implementer",
                                  "tool_input": {"command": "pnpm add libphonenumber-js"}})
        self.assertIn("may not install packages", refused or "")


class EvidenceTest(SectionsCase):
    def setUp(self):
        super().setUp()
        self.write(".bdd/sources.toml", '[supabase]\nname = "Supabase"\ndocs = "https://supabase.com/docs"\ncli = "supabase"\n'
                                        'plugin = "supabase@claude-plugins-official"\n')

    def add(self, **how) -> dict:
        args = {"source": None, "mcp": None, "query": None, "cli": None, **how}
        return docsrecord.add_evidence(self.root, self.feature_dir, "Supabase", **args)

    def test_a_page_of_the_official_site_a_lookup_or_a_run_of_its_tool(self):
        self.assertEqual(self.add(source="https://supabase.com/docs/guides/api")["kind"], "page")
        self.assertEqual(self.add(mcp="supabase", query="update a row")["service"], "supabase")
        self.assertEqual(self.add(mcp="context7", query="supabase-js update")["kind"], "mcp")
        self.assertEqual(self.add(cli="npx supabase gen types")["kind"], "cli")

    def test_evidence_that_is_not_the_services_own_is_refused(self):
        for how, message in (({"source": "https://stackoverflow.com/q/1"}, "is not on the official site of supabase"),
                             ({"source": "package.json"}, "a version file is not documentation"),
                             ({"mcp": "some-server", "query": "x"}, "is not one .bdd/sources.toml names"),
                             ({"mcp": "supabase"}, "--mcp needs --query"),
                             ({"cli": "curl https://x"}, "names supabase as the tool"),
                             ({}, "evidence is one of")):
            with self.subTest(how=how), self.assertRaises(UsageError) as cm:
                self.add(**how)
            self.assertIn(message, str(cm.exception))

    def test_the_official_site_is_the_host_a_browser_opens(self):
        self.write(".bdd/sources.toml", '[stripe]\nname = "Stripe"\ndocs = "https://docs.stripe.com"\n')

        def page(url: str) -> dict:
            return docsrecord.add_evidence(self.root, self.feature_dir, "stripe", url, None, None, None)
        for url in ("https://docs.stripe.com@evil.example/x", "https://evil.example/docs.stripe.com",
                    "https://docs.stripe.com.evil.example/", "https://docs.stripe.com\\@evil.example/",
                    "https://docs%2estripe.com/", "https://user@docs.stripe.com/", "https://docs.stripe.com:8443/x",
                    "https://notstripe.com/docs", "https:///docs.stripe.com"):
            with self.subTest(url=url), self.assertRaises(UsageError):
                page(url)
        for url in ("https://docs.stripe.com/api", "https://stripe.com/docs", "https://DOCS.Stripe.COM/api",
                    "https://docs.stripe.com./api"):
            with self.subTest(url=url):
                self.assertEqual(page(url)["kind"], "page")

    def test_the_command_line_records_and_lists_it(self):
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(docsrecord.run(["FEAT-007", "--service", "supabase", "--source", "https://supabase.com/docs/x"]), 0)
                self.assertEqual(docsrecord.run(["FEAT-007", "--list"]), 0)
        finally:
            os.chdir(here)
        self.assertIn("recorded: design evidence for supabase", out.getvalue())
        self.assertIn("design  supabase  https://supabase.com/docs/x", out.getvalue())


class DesignReviewTest(SectionsCase):
    def setUp(self):
        super().setUp()
        self.write_technical_design(design())

    def review(self, reviewer: str, verdict: str = "PASS", digest: str | None = None) -> None:
        path = designreview.review_path(self.feature_dir, reviewer)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Design: {digest or designreview.digest(self.feature_dir)}\nVerdict: {verdict}\n", encoding="utf-8")

    def problems(self, hooks_seen: bool = False) -> list[str]:
        return designreview.problems(self.root, self.feature_dir, "FEAT-007", hooks_seen)

    def test_every_reviewer_passes_this_very_design(self):
        self.assertEqual(len(self.problems()), 3)
        for reviewer in designreview.REVIEWERS:
            self.review(reviewer)
        self.assertEqual(self.problems(), [])
        self.write_technical_design(design() + "\n")
        self.assertTrue(all("reviewed another version of design.md" in p for p in self.problems()))

    def test_must_fix_items_go_back_to_the_system_analyst(self):
        for reviewer in designreview.REVIEWERS:
            self.review(reviewer, "FINDINGS" if reviewer == "security-reviewer" else "PASS")
        self.assertEqual(len(self.problems()), 1)
        self.assertIn("the system-analyst changes design.md", self.problems()[0])

    def test_a_design_without_screens_needs_no_ui_review(self):
        self.write("design/inventory.md", INVENTORY.replace("FEAT-007", "FEAT-008"))
        self.write_technical_design(TECHNICAL_DESIGN)
        self.assertEqual(designreview.needed(self.root, self.feature_dir, "FEAT-007"), ["code-reviewer", "security-reviewer"])

    def written(self, reviewer: str, agent: str | None, agent_id: str = "r1") -> str | None:
        path = designreview.review_path(self.feature_dir, reviewer)
        text = f"Design: {designreview.digest(self.feature_dir)}\nVerdict: PASS\n"
        payload = {"tool_name": "Write", "cwd": str(self.root), "agent_id": agent_id,
                   "tool_input": {"file_path": str(path), "content": text}}
        if agent:
            payload["agent_type"] = agent
        refused = guard.evaluate(payload)
        if refused is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        return refused

    def test_where_the_hooks_run_a_review_counts_only_as_its_reviewer_wrote_it(self):
        from bddlib import agentcost
        state.update(self.feature_dir, lambda current: current.update(phase="tasks"))
        self.assertIn("only the code-reviewer agent writes it", self.written("code-reviewer", None) or "")
        self.assertIn("only the code-reviewer agent writes it", self.written("code-reviewer", "greenlight:system-analyst") or "")
        for number, reviewer in enumerate(designreview.REVIEWERS):
            self.assertIsNone(self.written(reviewer, f"greenlight:{reviewer}", f"r{number}"))
        self.assertTrue(all("is not what the" in p for p in self.problems(hooks_seen=True)), "no agent finished yet")
        for number, reviewer in enumerate(designreview.REVIEWERS):
            agentcost.note_agent({"agent_id": f"r{number}", "agent_type": f"greenlight:{reviewer}", "cwd": str(self.root)})
        self.assertEqual(self.problems(hooks_seen=True), [])
        path = designreview.review_path(self.feature_dir, "code-reviewer")
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertEqual(len(self.problems(hooks_seen=True)), 1)

    def test_a_review_written_before_the_system_map_does_not_count(self):
        state.update(self.feature_dir, lambda current: current.update(phase="examples"))
        self.assertIsNone(self.written("code-reviewer", "greenlight:code-reviewer"))
        log = reviewlog.recorded(self.root)
        path = designreview.review_path(self.feature_dir, "code-reviewer")
        self.assertFalse(reviewlog.written_by(self.root, path, "code-reviewer", log, None, phases=designreview.PHASES))

    def test_a_shell_command_may_not_write_one(self):
        for command in ("echo Verdict: PASS > .bdd/features/x/reviews/design-code-reviewer.md",
                        "cp a .bdd/design-reviews/design-ui-reviewer.md", "cp -r a .bdd/design-reviews/"):
            with self.subTest(command=command):
                refused = guard.evaluate({"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": command}})
                self.assertIn("review reports are written only by each reviewer", refused or "")
