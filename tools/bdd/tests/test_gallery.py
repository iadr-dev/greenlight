import contextlib
import io
import re
import time
import unittest
from html.parser import HTMLParser

from bddlib import designfolder, gallery, productmap

from tests.design_fixture import ARCHITECTURE, INVENTORY, MAP, SECTIONS, DesignCase, screen


class Page(HTMLParser):
    """What a browser would see of the gallery: its tags, the documents of its frames, and every address it names."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.frames, self.addresses, self.cards, self.headings = [], [], [], [], []
        self._heading = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.tags.append(tag)
        if tag == "iframe":
            self.frames.append(values)
        if "data-row" in values:
            self.cards.append(values["data-row"])
        for name in ("src", "href"):
            if values.get(name):
                self.addresses.append((tag, values[name]))
        if tag == "h2":
            self._heading = ""

    def handle_data(self, data):
        if self._heading is not None:
            self._heading += data

    def handle_endtag(self, tag):
        if tag == "h2" and self._heading is not None:
            self.headings.append(self._heading)
            self._heading = None


def parse(text: str) -> Page:
    page = Page()
    page.feed(text)
    return page


class GalleryTest(DesignCase):
    def run_gallery(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gallery.run(list(args))
        return code, out.getvalue(), err.getvalue()

    def page(self) -> Page:
        return parse((self.root / "design" / "gallery.html").read_text(encoding="utf-8"))

    def test_every_row_is_a_card_under_its_feature_and_every_screen_is_shown_at_two_widths(self):
        code, out, _ = self.run_gallery()
        self.assertEqual(code, 0, out)
        self.assertIn("design/gallery.html: 2 screens, 7 states, 2 features", out)
        page = self.page()
        self.assertEqual(page.cards, ["S-IN-01", "S-OR-01"])
        self.assertIn("FEAT-001 Sign in", page.headings)
        self.assertIn("FEAT-002 Orders", page.headings)
        widths = sorted(f["width"] for f in page.frames if "home.html" in f["title"])
        self.assertEqual(widths, ["1280", "375"])
        shown = next(f["srcdoc"] for f in page.frames if "home.html" in f["title"])
        self.assertEqual(len(re.findall(r'data-state="', shown)), 7, "every state of every row is in the frame")
        self.assertIn("--primary: #137547", shown, "the tokens stylesheet is inlined")
        self.assertFalse([a for a in page.addresses if a[0] == "a" and not a[1].startswith("#")], "links stay inside the page")

    def test_the_page_needs_no_network_and_runs_no_script(self):
        self.write("design/screens/home.html", screen(head=(
            '<link rel="stylesheet" href="https://fonts.example.com/css"><link rel="stylesheet" href="../tokens.css">'
            '<script src="https://cdn.example.com/x.js"></script><script>alert(1)</script>'
            '<img src="https://example.com/logo.png" onerror="alert(2)">')))
        self.run_gallery()
        text = (self.root / "design" / "gallery.html").read_text(encoding="utf-8")
        page = self.page()
        self.assertNotIn("script", page.tags)
        self.assertTrue(all("sandbox" in f and not f["sandbox"] for f in page.frames), "every frame is sandboxed without scripts")
        for frame in page.frames:
            inner = parse(frame["srcdoc"])
            self.assertNotIn("script", inner.tags)
            self.assertFalse([a for a in inner.addresses if re.match(r"(?i)https?:|//", a[1])], inner.addresses)
            self.assertNotIn("onerror", frame["srcdoc"])
            self.assertIn("Content-Security-Policy", frame["srcdoc"])
        self.assertIn("default-src 'none'", text)
        self.assertFalse([a for a in page.addresses if re.match(r"(?i)https?:|//", a[1])])

    def test_a_file_outside_the_design_folder_is_never_inlined(self):
        self.write("secret.css", "body { --secret: 42; }\n")
        self.write("design/screens/home.html", screen(head='<link rel="stylesheet" href="../../secret.css">'
                                                           '<link rel="stylesheet" href="../tokens.css">'))
        code, out, _ = self.run_gallery()
        self.assertEqual(code, 1)
        self.assertIn("SC3", out)
        self.assertNotIn("--secret", (self.root / "design" / "gallery.html").read_text(encoding="utf-8"))

    def test_a_hidden_or_generated_file_of_the_design_folder_is_never_shown(self):
        self.write("design/.x/look.css", "body { --hidden: 1; }\n")
        self.write("design/screens/home.html", screen(head='<link rel="stylesheet" href="../.x/look.css">'
                                                           '<link rel="stylesheet" href="../tokens.css">'))
        self.run_gallery()
        self.assertNotIn("--hidden", (self.root / "design" / "gallery.html").read_text(encoding="utf-8"))

    def test_a_screen_outside_what_the_approval_covers_is_an_error_and_never_shown(self):
        self.write("outside.html", screen())
        self.write("design/.hidden/board.html", screen())
        cases = {"a path with ..": "../outside.html", "an absolute path": str(self.root / "outside.html").replace("\\", "/"),
                 "a hidden folder": ".hidden/board.html"}
        link = self.root / "design" / "screens" / "link.html"
        try:
            link.symlink_to(self.root / "outside.html")
            cases["a link out of the folder"] = "screens/link.html"
        except OSError:
            pass                                           # Windows without the right to make links
        for what, named in cases.items():
            with self.subTest(what=what):
                self.write("design/inventory.md", INVENTORY.replace("FEAT-002 | screens/home.html", f"FEAT-002 | {named}"))
                code, out, _ = self.run_gallery()
                self.assertEqual(code, 1)
                self.assertIn("IN6", out)
                frames = [f["title"] for f in self.page().frames]
                self.assertFalse([t for t in frames if "outside" in t or "link.html" in t or "board" in t], frames)

    def test_the_gallery_lists_the_gaps_and_still_shows_the_design(self):
        self.write("design/screens/home.html", screen({"S-IN-01": ("loading", "error", "success"),
                                                       "S-OR-01": ("loading", "error", "success")}))
        code, out, _ = self.run_gallery()
        self.assertEqual(code, 1)
        self.assertIn('S-OR-01 lists the state empty, but screens/home.html shows no data-state="empty" for it', out)
        text = (self.root / "design" / "gallery.html").read_text(encoding="utf-8")
        self.assertIn('<li class="gap">empty</li>', text)
        self.assertIn("S-OR-01 lists the state empty", text)

    def test_check_prints_the_digest_and_writes_nothing(self):
        code, out, _ = self.run_gallery("--check")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"design digest: [0-9a-f]{64}")
        self.assertFalse((self.root / "design" / "gallery.html").exists())

    def test_the_gallery_is_not_written_into_the_design_or_bdd_under_another_name(self):
        for out in ("design/other.html", ".bdd/gallery.html"):
            with self.subTest(out=out):
                self.assertEqual(self.run_gallery("--out", out)[0], 2)
        self.assertEqual(self.run_gallery("--out", "review/gallery.html")[0], 0)
        text = (self.root / "review" / "gallery.html").read_text(encoding="utf-8")
        self.assertIn("data-row=\"S-OR-01\"", text)

    def test_the_same_design_gives_the_same_page(self):
        self.run_gallery()
        first = (self.root / "design" / "gallery.html").read_bytes()
        self.run_gallery()
        self.assertEqual(first, (self.root / "design" / "gallery.html").read_bytes())

    def test_a_project_without_a_design_folder_is_told_so(self):
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\n')
        import shutil
        shutil.rmtree(self.root / "design")
        code, _, err = self.run_gallery()
        self.assertEqual(code, 2)
        self.assertIn("there is no design folder (design/)", err)

    def test_148_rows_are_built_in_under_three_seconds(self):
        rows = "".join(f"| S-{n:03d} | Screen {n} | loading, empty, error, success | FEAT-00{1 + n % 2} | screens/board-{n % 5}.html |\n"
                       for n in range(148))
        self.write("design/inventory.md", "| ID | Screen | States | Feature | File |\n|---|---|---|---|---|\n" + rows)
        for board in range(5):
            states = {f"S-{n:03d}": ("loading", "empty", "error", "success") for n in range(148) if n % 5 == board}
            self.write(f"design/screens/board-{board}.html", screen(states))
        started = time.perf_counter()
        code, out, _ = self.run_gallery()
        elapsed = time.perf_counter() - started
        self.assertEqual(code, 0, out)
        self.assertIn("148 screens, 592 states", out)
        self.assertLess(elapsed, 3.0)


class FolderTest(DesignCase):
    def codes(self) -> list[str]:
        return [issue.code for issue in designfolder.load(self.root).issues]

    def test_the_complete_design_has_no_findings(self):
        self.assertEqual(designfolder.load(self.root).issues, [])

    def test_each_gap_has_its_code(self):
        cases = {
            "IN2": ("design/inventory.md", INVENTORY.replace("| loading, error, success | FEAT-001 |", "|  | FEAT-001 |")),
            "IN3": ("design/inventory.md", INVENTORY.replace("S-OR-01", "S-IN-01")),
            "IN4": ("design/inventory.md", INVENTORY.replace("FEAT-002", "FEAT-009")),
            "IN5": ("design/inventory.md", INVENTORY.replace("| FEAT-002 | screens/home.html |", "| FEAT-002 | - |")),
            "IN6": ("design/inventory.md", INVENTORY.replace("FEAT-002 | screens/home.html", "FEAT-002 | screens/x.html")),
            "IN1": ("design/inventory.md", "# Screen inventory\n\nNothing yet.\n"),
            "SC2": ("design/screens/home.html", screen(head="")),
            "SC4": ("design/tokens.json", "{not json"),
            "DS2": ("design/PRODUCT.md", "# Shop\n\n## Users\nShoppers.\n"),
            "PM2": (".bdd/product.md", MAP.replace("FEAT-002", "F-2")),
            "PM3": (".bdd/product.md", MAP.replace("| A shopper signs in. |", "|  |")),
            "PM4": (".bdd/product.md", MAP.replace("| FEAT-001 | 2 |", "| FEAT-007 | 2 |")),
            "PM6": (".bdd/product.md", MAP.replace("| FEAT-001 | 2 |", "| FEAT-001 | 1 |")),
            "AR1": (".bdd/architecture.md", ARCHITECTURE.replace("## Observability\n", "## Notes\n")),
            "AR2": (".bdd/architecture.md", ARCHITECTURE.replace("Postgres.", "<!-- to decide -->")),
        }
        for code, (rel, text) in cases.items():
            with self.subTest(code=code):
                original = (self.root / rel).read_text(encoding="utf-8")
                self.write(rel, text)
                self.assertIn(code, self.codes())
                self.write(rel, original)

    def test_a_dependency_circle_is_found(self):
        self.write(".bdd/product.md", MAP.replace("| - | 1 |", "| FEAT-002 | 1 |"))
        issues = productmap.read(self.root / ".bdd" / "product.md")[1]
        self.assertIn("PM5", [i.code for i in issues])

    def test_the_architecture_template_is_not_a_finished_architecture(self):
        template = (designfolder.Path(gallery.__file__).resolve().parents[3] / "templates" / "architecture.md").read_text(encoding="utf-8")
        self.write(".bdd/architecture.md", template)
        codes = self.codes()
        self.assertEqual(codes.count("AR2"), len(SECTIONS))

    def test_a_surface_of_the_product_needs_a_row_in_the_stack_table(self):
        self.write(".bdd/config.toml", (self.root / ".bdd" / "config.toml").read_text(encoding="utf-8") + '\n[surfaces]\nios = "unverified"\n')
        found = [str(i) for i in designfolder.load(self.root).issues]
        self.assertTrue(any("ships the ios surface" in f for f in found), found)

    def test_an_inventory_written_before_greenlight_is_read_as_it_is(self):
        self.write("design/inventory.md", (
            "## Owner console\n\n| Section | What lives under it |\n|---|---|\n| Today | O-DB-01 |\n\n"
            "| ID | Screen | Purpose | Key states | Phase | BDD | Comp |\n|---|---|---|---|---|---|---|\n"
            "| O-DB-01 | Today dashboard | Staff rows | Loading, Empty | 1 | FEAT-001, FEAT-002 | "
            "[owner-console](screens/home.html) (empty state) |\n| O-DB-02 | Search | Find a job | No results | 1 | FEAT-002 | — |\n"))
        design = designfolder.load(self.root)
        first, second = design.rows
        self.assertEqual((first.id, first.states, first.features, first.file, first.section),
                         ("O-DB-01", ("Loading", "Empty"), ("FEAT-001", "FEAT-002"), "screens/home.html", "Owner console"))
        self.assertEqual(second.file, "")
        self.assertIn("IN5", [i.code for i in design.issues])

    def test_the_design_folder_is_a_folder_of_its_own(self):
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "f"\n\n[design]\nsystem = "DESIGN.md"\n')
        with self.assertRaises(designfolder.UsageError):
            designfolder.load(self.root)

    def test_the_approval_covers_the_design_but_not_its_hidden_files_or_the_gallery(self):
        self.write("design/gallery.html", "x")
        self.write("design/.impeccable/design.json", "{}")
        covered = designfolder.artifacts(self.root, "design")
        self.assertIn(".bdd/product.md", covered)
        self.assertIn("design/screens/home.html", covered)
        self.assertNotIn("design/gallery.html", covered)
        self.assertFalse([rel for rel in covered if ".impeccable" in rel])


if __name__ == "__main__":
    unittest.main()
