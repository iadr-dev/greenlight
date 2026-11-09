"""What the person is asked to approve, and what changed since they last approved it."""
import html
import unittest
from unittest import mock

from bddlib import approvals, approvalsummary, state
from bddlib.errors import UsageError

from tests.helpers import ProjectCase, headless, typed

RULES = """# Rules: FEAT-007 Discounts

## Business rules

R-007.1 Orders of 1000 or more get 10% off.
- Why: big orders are rewarded
- Source: the shop owner

R-007.2 A discount code cannot be combined with a bulk discount.
- Why: the margin would be lost

N-007.1 Pricing answers within 300 ms.

## Out of scope

- Gift cards
"""
FEATURE = """@FEAT-007
Feature: Order discounts
  Background:
    Given a shop

  @R-007.1
  Rule: Orders of 1000 or more get 10% off

    @EX-007.1.1
    Scenario: An order of 1000 gets the discount
      Given an order of 1000
      When the order is priced
      Then the discount is 10%

    @EX-007.1.2
    Scenario Outline: Orders get a discount by size
      Given an order of <amount>
      Then the discount is <discount>
      Examples:
        | amount | discount |
        | 999    | 0        |
        | 5000   | 10       |
"""
CHINESE = """# language: zh-CN
@FEAT-007
功能: 订单折扣

  @R-007.1
  规则: 满1000元打九折

    @EX-007.1.1
    场景: 订单满1000元享受折扣
      假如 订单金额为1000元
      当 系统计算订单价格
      那么 折扣为10%
"""


class SummaryCase(ProjectCase):
    def put_rules(self, text: str = RULES) -> None:
        self.rules.write_text(text, encoding="utf-8", newline="\n")

    def put_feature(self, text: str = FEATURE) -> None:
        self.write("features/discounts.feature", text)

    def reading(self, gate: str) -> dict:
        return approvalsummary.read(self.root, self.feature_dir, "FEAT-007", gate)

    def items(self, gate: str) -> dict:
        return self.reading(gate)["items"]

    def summary(self, gate: str = "rules") -> dict:
        return approvals.summary_for(self.root, self.feature_dir, gate)

    def text(self, gate: str = "rules") -> str:
        return approvalsummary.render(self.summary(gate), "FEAT-007")

    def approved_human(self, gate: str, prompt_id: str = "p-1", args: str | None = None) -> dict:
        path = self.transcript(typed(prompt_id, args or f"FEAT-007 {gate}"), name=f"{prompt_id}.jsonl")
        entry = self.approve(gate, grade="hook", session="s", prompt_id=prompt_id, transcript_path=str(path))
        approvals.verify_origins(self.feature_dir)
        return entry


class ItemsTest(SummaryCase):
    def test_rules_are_read_with_their_reason_and_the_other_lines_are_left_out(self):
        self.put_rules()
        items = self.items("rules")
        self.assertEqual(list(items), ["R-007.1", "R-007.2", "N-007.1"])
        self.assertEqual(items["R-007.1"]["text"], "Orders of 1000 or more get 10% off.")
        self.assertEqual(items["R-007.1"]["detail"], ["Why: big orders are rewarded", "Source: the shop owner"])
        self.assertEqual(set(items["R-007.1"]["parts"]), {"why", "source", "all"})
        self.assertEqual(items["N-007.1"]["detail"], [])

    def test_a_bullet_under_another_heading_belongs_to_no_rule_and_is_outside_text(self):
        self.put_rules()
        reading = self.reading("rules")
        self.assertNotIn("Gift cards", str(reading["items"]))
        self.assertEqual(reading["outside"]["lines"], ["# Rules: FEAT-007 Discounts", "## Business rules", "## Out of scope", "- Gift cards"])

    def test_scenarios_are_read_by_their_example_tag_with_their_rule_and_steps(self):
        self.put_feature()
        items = self.items("examples")
        self.assertEqual(list(items), ["Background (discounts.feature)", "EX-007.1.1", "EX-007.1.2"])
        first = items["EX-007.1.1"]
        self.assertEqual((first["text"], first["rule"]), ("An order of 1000 gets the discount", "R-007.1"))
        self.assertEqual(first["detail"], ["Given an order of 1000", "When the order is priced", "Then the discount is 10%"])
        self.assertEqual(set(items["EX-007.1.2"]["parts"]), {"steps", "tags", "examples", "all"})
        self.assertIn("| amount | discount |", items["EX-007.1.2"]["detail"])

    def test_a_scenario_without_a_tag_is_named_by_its_title(self):
        self.put_feature("@FEAT-007\nFeature: F\n  Scenario: Plain\n    Then ok\n")
        self.assertEqual(list(self.items("examples")), ["Plain"])

    def test_two_scenarios_with_one_tag_are_both_kept(self):
        self.put_feature("@FEAT-007\nFeature: F\n  @EX-7.1.1\n  Scenario: A\n    Then ok\n  @EX-7.1.1\n  Scenario: B\n    Then ok\n")
        self.assertEqual(list(self.items("examples")),
                         ["EX-7.1.1", "EX-7.1.1 (2)"])

    def test_nothing_to_summarise_is_said_in_words(self):
        with self.assertRaises(UsageError) as cm:
            self.summary("rules")
        self.assertIn("there is nothing to summarise", str(cm.exception))
        (self.root / "features" / "discounts.feature").unlink()
        with self.assertRaises(UsageError) as cm:
            self.summary("examples")
        self.assertIn("no .feature file is tagged @FEAT-007", str(cm.exception))

    def test_a_feature_file_that_does_not_parse_is_named(self):
        self.put_feature("@FEAT-007\nFeature: F\n  Scenario: S\n    Then ok\n  this line is nothing\n")
        with self.assertRaises(UsageError) as cm:
            self.summary("examples")
        self.assertIn("cannot summarise the examples", str(cm.exception))

    def test_the_kept_record_holds_no_lines_that_are_only_for_showing(self):
        self.put_rules()
        kept, outside = approvalsummary.snapshot(self.reading("rules"))
        self.assertTrue(all(set(item) <= {"text", "parts", "rule"} for item in kept.values()))
        self.assertRegex(outside, r"^[0-9a-f]{16}$")


class CompareTest(unittest.TestCase):
    def item(self, text: str, **parts: str) -> dict:
        return {"text": text, "parts": parts}

    def test_added_removed_changed_and_unchanged(self):
        old = {"R-1.1": self.item("a", why="1"), "R-1.2": self.item("b"), "R-1.3": self.item("c")}
        new = {"R-1.1": self.item("a", why="1"), "R-1.2": self.item("b2"), "R-1.4": self.item("d")}
        diff = approvalsummary.compare("rules", old, new)
        self.assertEqual((diff["added"], diff["removed"], diff["changed"], diff["unchanged"]),
                         (["R-1.4"], ["R-1.3"], {"R-1.2": ["statement"]}, 1))

    def test_a_changed_part_and_a_changed_rule_are_named(self):
        old = {"EX-1.1.1": {"text": "t", "rule": "R-1.1", "parts": {"steps": "a"}}}
        new = {"EX-1.1.1": {"text": "t", "rule": "R-1.2", "parts": {"steps": "b", "examples": "c"}}}
        self.assertEqual(approvalsummary.compare("examples", old, new)["changed"], {"EX-1.1.1": ["rule", "steps", "examples"]})

    def test_a_moved_item_is_not_a_change(self):
        old = {"R-1.1": self.item("a"), "R-1.2": self.item("b")}
        new = {"R-1.2": self.item("b"), "R-1.1": self.item("a")}
        diff = approvalsummary.compare("rules", old, new)
        self.assertEqual((diff["added"], diff["removed"], diff["changed"], diff["unchanged"]), ([], [], {}, 2))

    def test_the_digest_ignores_spacing_but_not_words(self):
        self.assertEqual(approvalsummary.digest(["a  b", "c"]), approvalsummary.digest([" a b ", "c "]))
        self.assertNotEqual(approvalsummary.digest(["a b"]), approvalsummary.digest(["a c"]))
        self.assertNotEqual(approvalsummary.digest(["a", "b"]), approvalsummary.digest(["ab"]))


class FirstSummaryTest(SummaryCase):
    def test_everything_is_listed_when_nothing_was_approved_before(self):
        self.put_rules()
        self.assertEqual(self.text(), "\n".join([
            "FEAT-007 rules, not approved before: 3 rules.",
            "  R-007.1  Orders of 1000 or more get 10% off.", "    Why: big orders are rewarded", "    Source: the shop owner",
            "  R-007.2  A discount code cannot be combined with a bulk discount.", "    Why: the margin would be lost",
            "  N-007.1  Pricing answers within 300 ms."]))

    def test_scenarios_are_listed_by_title_with_their_rule_and_no_steps(self):
        self.put_feature()
        lines = self.text("examples").splitlines()
        self.assertEqual(lines[0], "FEAT-007 examples, not approved before: 3 scenarios.")
        self.assertIn("  EX-007.1.1  An order of 1000 gets the discount  (R-007.1)", lines)
        self.assertFalse(any("Given" in line for line in lines))

    def test_one_item_is_counted_in_the_singular(self):
        self.put_rules("R-007.1 Only rule.\n")
        self.assertIn("not approved before: 1 rule.", self.text())

    def test_chinese_stays_chinese(self):
        self.put_rules("R-007.1 订单满1000元打九折。\n- Why: 鼓励大额订单\n")
        self.assertIn("  R-007.1  订单满1000元打九折。\n    Why: 鼓励大额订单", self.text())
        self.put_feature(CHINESE)
        self.assertIn("  EX-007.1.1  订单满1000元享受折扣  (R-007.1)", self.text("examples"))

    def test_a_rejection_is_named_with_its_reason(self):
        self.gate("discover")
        self.put_rules()
        self.approve("rules", decision="reject", reason="rule 2 is vague")
        self.assertEqual(self.text().splitlines()[1], f"Rejected on {self.data()['approvals'][0]['at'][:10]}: rule 2 is vague")


class ChangedSummaryTest(SummaryCase):
    def approved_rules(self) -> None:
        self.gate("discover")
        self.put_rules()
        self.approved_human("rules")

    def test_an_approval_keeps_the_record_of_its_items(self):
        self.approved_rules()
        kept = self.data()["approvals"][0]["items"]
        self.assertEqual(set(kept), {"R-007.1", "R-007.2", "N-007.1"})
        self.assertEqual(kept["R-007.2"]["text"], "A discount code cannot be combined with a bulk discount.")

    def test_only_the_newest_approvals_of_a_gate_keep_their_items_so_the_state_stays_small(self):
        self.gate("discover")
        self.put_rules()
        for number in range(1, 6):
            self.approve("rules")
        kept = [a["id"] for a in self.data()["approvals"] if a["items"]]
        self.assertEqual(kept, [3, 4, 5])
        self.approve("rules", decision="reject", reason="no")
        self.assertEqual([a["id"] for a in self.data()["approvals"] if a["items"]], [3, 4, 5])

    def test_the_newest_approval_that_is_settled_keeps_its_items_whatever_followed_it(self):
        self.gate("discover")
        self.put_rules()
        self.approved_human("rules")
        for number in range(2, 6):
            self.approve("rules", grade="hook", session="s", prompt_id=f"q-{number}", transcript_path=str(self.transcripts / "none.jsonl"))
        kept = [a["id"] for a in self.data()["approvals"] if a["items"]]
        self.assertEqual(kept, [1, 3, 4, 5])
        self.assertEqual(self.summary()["state"], "unchanged")

    def test_items_that_changed_while_they_were_read_are_not_kept(self):
        self.gate("discover")
        self.put_rules()
        real = approvalsummary.snapshot

        def snapshot_then_edit(reading):
            kept = real(reading)
            self.put_rules(RULES + "\nR-007.9 Written while the approval was being recorded.\n")
            return kept

        with mock.patch.object(approvalsummary, "snapshot", snapshot_then_edit):
            entry = self.approve("rules")
        self.assertEqual((entry["items"], entry["outside"]), (None, None))

    def test_a_rejection_keeps_no_record_of_items(self):
        self.gate("discover")
        self.put_rules()
        self.approve("rules", decision="reject", reason="no")
        self.assertIsNone(self.data()["approvals"][0]["items"])

    def test_nothing_changed_is_said_so_and_lists_nothing(self):
        self.approved_rules()
        self.assertEqual(self.summary()["state"], "unchanged")
        self.assertRegex(self.text(), r"^FEAT-007 rules: no change since the approval of \d{4}-\d\d-\d\d \(3 rules\)\.$")

    def test_a_file_that_differs_only_in_spacing_is_said_to_need_a_new_approval(self):
        self.approved_rules()
        self.put_rules(RULES.replace("R-007.2 A discount", "R-007.2   A  discount") + "\n\n")
        self.assertEqual(self.summary()["state"], "unchanged")
        self.assertIn("no rule and no other text changed", self.text())
        self.assertIn("has to be approved again", self.text())

    def test_only_what_changed_is_listed(self):
        self.approved_rules()
        self.put_rules(RULES.replace("cannot be combined", "can be combined once").replace("N-007.1 Pricing answers within 300 ms.\n", "")
                       + "\nR-007.3 Codes expire after 30 days.\n- Why: old codes pile up\n")
        lines = self.text().splitlines()
        self.assertRegex(lines[0], r"^FEAT-007 rules, since the approval of \d{4}-\d\d-\d\d: 1 rule changed, 1 added, 1 removed\.$")
        self.assertEqual(lines[1:], [
            "Changed:", "  R-007.2  A discount code can be combined once with a bulk discount.", "    Why: the margin would be lost",
            "    changed: statement", "    was: A discount code cannot be combined with a bulk discount.",
            "Added:", "  R-007.3  Codes expire after 30 days.", "    Why: old codes pile up",
            "Removed:", "  N-007.1  Pricing answers within 300 ms.", "Unchanged: 1 rule (not shown)."])

    def test_a_changed_reason_is_named(self):
        self.approved_rules()
        self.put_rules(RULES.replace("big orders are rewarded", "big orders cost more to ship"))
        text = self.text()
        self.assertIn("changed: why", text)
        self.assertNotIn("was:", text)

    def test_scenarios_changed_in_steps_title_and_examples_are_named_with_their_new_steps(self):
        self.gate("discover")
        self.put_rules()
        self.approved_human("rules")
        self.gate("test-design")
        self.put_feature()
        self.approved_human("examples", "p-2")
        self.put_feature(FEATURE.replace("an order of 1000", "an order of 1001").replace("Orders get a discount by size", "Size sets the discount")
                         .replace("| 999    | 0        |", "| 998    | 0        |"))
        self.assertRegex(self.text("examples").splitlines()[0], r": 2 scenarios changed\.$")
        text = self.text("examples")
        self.assertIn("    Given an order of 1001\n    When the order is priced\n    Then the discount is 10%\n    changed: steps", text)
        self.assertIn("    changed: title, examples\n    was: Orders get a discount by size", text)
        self.assertIn("Unchanged: 1 scenario (not shown).", text)

    def test_the_last_approval_is_the_baseline_also_after_a_change_revoked_it(self):
        self.approved_rules()
        state.update(self.feature_dir, lambda d: d["approvals"][0].__setitem__("revoked", "the rule changed"))
        self.put_rules(RULES.replace("10%", "15%"))
        self.assertIn("1 rule changed", self.text())

    def test_an_approval_that_was_not_typed_by_a_person_is_not_the_baseline(self):
        self.approved_rules()
        self.put_rules(RULES.replace("10%", "15%"))
        path = self.transcript(headless("p-2"), name="p-2.jsonl")
        self.approve("rules", grade="hook", session="s", prompt_id="p-2", transcript_path=str(path))
        approvals.verify_origins(self.feature_dir)
        self.assertEqual(self.data()["approvals"][1]["origin"], "headless")
        self.assertIn("1 rule changed", self.text())

    def test_an_approval_from_before_the_record_existed_says_so_and_lists_everything(self):
        self.approved_rules()
        state.update(self.feature_dir, lambda d: d["approvals"][0].pop("items"))
        lines = self.text().splitlines()
        self.assertIn("kept no list of its items", lines[0])
        self.assertEqual(len(lines), 7)

    def test_an_approval_is_never_refused_for_want_of_a_summary(self):
        self.gate("discover")
        self.gate("test-design", "fail")
        self.put_rules()
        self.approved_human("rules")
        self.put_feature("@FEAT-007\nFeature: F\n  Scenario: S\n    Then ok\n  not gherkin at all\n")
        self.gate("test-design")
        entry = self.approve("examples")
        self.assertIsNone(entry["items"])

    def test_the_summary_reads_and_writes_nothing(self):
        self.approved_rules()
        before = (self.feature_dir / "state.json").read_bytes()
        self.summary()
        self.assertEqual((self.feature_dir / "state.json").read_bytes(), before)


PROSE = """# Rules: FEAT-007 Discounts

R-007.1 Orders of 1000 or more get 10% off.
Orders in euros count at the rate of the order day.
- Why: big orders are rewarded
- Why: they cost less to ship per item
- Orders under 10 are refused

## Out of scope

- Gift cards
"""
BACKGROUNDS = """# language: en
@FEAT-007
Feature: Order discounts
  Orders are priced in the shop's currency.

  @R-007.1
  Rule: Orders of 1000 or more get 10% off
    A rule description.

    Background:
      Given the currency is EUR

    @EX-007.1.1 @smoke
    Scenario: An order of 1000 gets the discount
      # keep this one small
      Given an order with:
        \"\"\"
        {"amount": 1000}
        \"\"\"
      When the order is priced
      Then the discount is 10%

    @EX-007.1.2
    Scenario Outline: Orders get a discount by size
      Given an order of <amount>
      Examples:
        | amount |
        | 999    |
"""


class NothingHidesTest(SummaryCase):
    """No word of an approved file can change without the summary naming it, for the rules, the scenarios and the report."""

    def approved(self, gate: str, text: str) -> None:
        self.gate("discover")
        if gate == "rules":
            self.put_rules(text)
            self.approved_human("rules")
        else:
            self.put_rules()
            self.approved_human("rules")
            self.gate("test-design")
            self.put_feature(text)
            self.approved_human("examples", "p-2")

    def after(self, gate: str, old: str, new: str, replacement: str) -> str:
        self.approved(gate, old)
        (self.put_rules if gate == "rules" else self.put_feature)(old.replace(new, replacement))
        text = self.text(gate)
        from bddlib import htmlreport
        report = htmlreport.approval_section({"approval_summaries": htmlreport.approval_summaries(self.root, self.feature_dir)})
        shown = html.unescape("\n".join(report))
        for line in text.splitlines():
            self.assertIn(line.strip(), shown, "the report shows what the command shows")
        return text

    def test_a_sentence_of_a_rule_that_is_not_a_bullet_is_named(self):
        text = self.after("rules", PROSE, "rate of the order day", "rate of the payment day")
        self.assertIn("changed: free text under the rule", text)
        self.assertIn("Orders in euros count at the rate of the payment day.", text)

    def test_a_bullet_without_a_label_is_named(self):
        text = self.after("rules", PROSE, "Orders under 10 are refused", "Orders under 50 are refused")
        self.assertIn("changed: free text under the rule", text)

    def test_a_repeated_label_keeps_every_value(self):
        self.approved("rules", PROSE)
        shown = self.items("rules")["R-007.1"]["detail"]
        self.assertEqual([line for line in shown if line.startswith("Why")], ["Why: big orders are rewarded", "Why: they cost less to ship per item"])
        text = self.after("rules", PROSE, "they cost less to ship per item", "they weigh more")
        self.assertIn("changed: why", text)
        self.assertIn("Why: they weigh more", text)

    def test_a_repeated_rule_id_is_an_item_of_its_own(self):
        twice = PROSE + "\nR-007.1 A second rule with the same id.\n"
        self.approved("rules", PROSE)
        self.put_rules(twice)
        text = self.text()
        self.assertIn("1 added", text)
        self.assertIn("  R-007.1 (2)  A second rule with the same id.", text)
        self.assertEqual(list(self.items("rules")), ["R-007.1", "R-007.1 (2)"])

    def test_a_line_outside_every_rule_is_named_and_shown(self):
        text = self.after("rules", PROSE, "- Gift cards", "- Gift cards\n- Coupons")
        self.assertIn("Also changed: text outside the rules", text)
        self.assertIn("  - Coupons", text)
        self.assertIn("text outside the rules changed", text.splitlines()[0])

    def test_a_heading_changed_is_named(self):
        self.assertIn("Also changed: text outside the rules", self.after("rules", PROSE, "## Out of scope", "## Left out"))

    def test_a_tag_added_to_a_scenario_is_named(self):
        text = self.after("examples", BACKGROUNDS, "@EX-007.1.1 @smoke", "@EX-007.1.1 @smoke @slow")
        self.assertIn("changed: tags", text)

    def test_a_comment_inside_a_scenario_is_named(self):
        text = self.after("examples", BACKGROUNDS, "# keep this one small", "# keep this one tiny")
        self.assertIn("changed: other text of the item", text)

    def test_a_doc_string_and_an_examples_table_are_named(self):
        self.assertIn("changed: steps", self.after("examples", BACKGROUNDS, '{"amount": 1000}', '{"amount": 1001}'))
        self.assertIn("changed: examples", self.after("examples", BACKGROUNDS, "| 999    |", "| 998    |"))

    def test_a_background_inside_a_rule_is_named(self):
        text = self.after("examples", BACKGROUNDS, "the currency is EUR", "the currency is USD")
        self.assertIn("Background (discounts.feature, R-007.1)", text)
        self.assertIn("Given the currency is USD", text)

    def test_the_names_and_descriptions_around_the_scenarios_are_named(self):
        for old, new in (("Rule: Orders of 1000 or more get 10% off", "Rule: Orders of 500 or more get 10% off"),
                         ("A rule description.", "Another rule description."),
                         ("Orders are priced in the shop's currency.", "Orders are priced in euros."),
                         ("Feature: Order discounts", "Feature: Discounts for orders")):
            with self.subTest(old=old):
                self.setUp()
                text = self.after("examples", BACKGROUNDS, old, new)
                self.assertIn("Also changed: text outside the scenarios", text)
                self.assertIn(new, text)

    def test_an_added_file_and_a_removed_scenario_are_named(self):
        self.approved("examples", BACKGROUNDS)
        self.write("features/more.feature", "@FEAT-007\nFeature: More\n  @EX-007.2.1\n  Scenario: Extra\n    Then ok\n")
        self.assertIn("EX-007.2.1  Extra", self.text("examples"))
        self.put_feature(BACKGROUNDS.split("    @EX-007.1.2")[0])
        self.assertIn("Removed:\n  EX-007.1.2", self.text("examples"))


class FallbackTest(SummaryCase):
    def problems(self, gate: str = "rules") -> list[str]:
        return approvals.effective_problems(self.root, self.data(), gate)

    def second(self, prompt_id: str = "p-2", entries=(), age: bool = False) -> dict:
        path = self.transcript(*entries, name=f"{prompt_id}.jsonl")
        entry = self.approve("rules", grade="hook", session="s", prompt_id=prompt_id, transcript_path=str(path))
        if age:
            state.update(self.feature_dir, lambda d: d["approvals"][-1].__setitem__("at", "2000-01-01T00:00:00+00:00"))
        approvals.verify_origins(self.feature_dir)
        return entry

    def setUp(self):
        super().setUp()
        self.gate("discover")
        self.put_rules()
        self.approved_human("rules")

    def test_a_later_approval_still_waiting_leaves_the_verified_one_counting(self):
        self.second()
        self.assertEqual(self.data()["approvals"][1]["origin"], "pending")
        self.assertEqual(self.problems(), [])
        self.assertEqual(self.gate("test-design")["phase"], "examples")

    def test_a_later_approval_that_cannot_be_verified_leaves_the_verified_one_counting(self):
        self.second(age=True)
        self.assertEqual(self.data()["approvals"][1]["origin"], "unverifiable")
        self.assertEqual(self.problems(), [])
        self.assertEqual(approvals.counted(self.root, self.data(), "rules")["id"], 1)

    def test_a_later_approval_the_person_did_not_type_leaves_the_verified_one_counting(self):
        self.second(entries=[{**typed("p-2"), "message": {"role": "user", "content": "thanks, that looks good"}}])
        self.assertEqual(self.data()["approvals"][1]["origin"], "invalid")
        self.assertEqual(self.problems(), [])

    def test_a_changed_file_never_falls_back(self):
        self.put_rules(RULES.replace("10%", "15%"))
        self.second(age=True)
        self.assertIn("could not be verified", self.problems()[0])
        self.assertIsNone(approvals.counted(self.root, self.data(), "rules").get("revoked"))
        self.assertEqual(approvals.counted(self.root, self.data(), "rules")["id"], 2)

    def test_a_file_changed_after_the_verified_approval_is_still_caught_through_the_fallback(self):
        self.second(age=True)
        self.put_rules(RULES.replace("10%", "15%"))
        self.assertIn("changed after the rules approval", self.problems()[0])

    def test_a_rejection_in_between_stops_the_fallback(self):
        self.approve("rules", decision="reject", reason="no")
        self.second(age=True)
        self.assertIn("could not be verified", self.problems()[0])

    def test_a_revoked_approval_is_not_a_fallback(self):
        state.update(self.feature_dir, lambda d: d["approvals"][0].__setitem__("revoked", "a change"))
        self.second(age=True)
        self.assertIn("could not be verified", self.problems()[0])

    def test_a_revoked_latest_approval_stays_revoked(self):
        self.second(age=True)
        state.update(self.feature_dir, lambda d: d["approvals"][1].__setitem__("revoked", "a change"))
        self.assertIn("revoked by a change", self.problems()[0])

    def test_a_self_reported_approval_is_never_a_fallback(self):
        self.config('enforcement = "soft"\n')
        state.update(self.feature_dir, lambda d: d["approvals"][0].__setitem__("grade", "self-reported"))
        self.second(age=True)
        self.assertIn("could not be verified", self.problems()[0])

    def test_a_verified_later_approval_counts_itself(self):
        self.second(entries=[typed("p-2")])
        self.assertEqual(self.data()["approvals"][1]["origin"], "human")
        self.assertEqual(approvals.counted(self.root, self.data(), "rules")["id"], 2)

    def test_the_check_names_the_approval_that_stands(self):
        import contextlib
        import io
        import os

        from bddlib import approvecmd
        self.second(age=True)
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                code = approvecmd.run(["FEAT-007", "--check"])
        finally:
            os.chdir(here)
        self.assertEqual(code, 0)
        self.assertIn("rules: valid (hook, origin human)", out.getvalue())
        self.assertIn("the latest approval (#2, origin unverifiable) could not be verified; the verified approval #1 of the same file is "
                      "the one that counts", out.getvalue())

    def test_the_check_names_the_unverified_approval_also_when_the_verified_one_no_longer_matches_the_file(self):
        import contextlib
        import io
        import os

        from bddlib import approvecmd
        self.second(age=True)
        self.put_rules(RULES.replace("10%", "15%"))
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                code = approvecmd.run(["FEAT-007", "--check"])
        finally:
            os.chdir(here)
        self.assertEqual(code, 1)
        self.assertIn("the latest approval (#2, origin unverifiable) could not be verified", out.getvalue())

    def test_the_report_and_the_pull_request_say_that_a_later_approval_is_not_counted(self):
        from bddlib import htmlreport, pr
        self.second(age=True)
        (row,) = pr.approvals_of(self.root, self.data())
        self.assertEqual((row["origin"], row["valid"]), ("human", True))
        self.assertIn("a later approval (unverifiable) could not be verified and is not counted", row["note"])
        self.assertIn("not counted", pr.approval_line(row))
        self.assertIn("not counted", "".join(htmlreport.approval_row(row)))


if __name__ == "__main__":
    unittest.main()
