@FEAT-113
Feature: A person can read what they approve and approve it in one step
  The person is shown the rules or the examples in plain words before they approve, and after a change only what
  changed since their last approval. They approve with one command alone in a message, and a message that holds more
  than that is refused with the reason instead of being skipped. An approval that cannot be verified does not take away
  one that was verified for the same files.

  @R-113.1
  Rule: The summary lists what is asked of the person in the feature's own words

    @EX-113.1.1
    Scenario: The first summary of the rules lists every rule with its reason
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        # Rules: FEAT-007 Discounts

        R-007.1 Orders of 1000 or more get 10% off.
        - Why: big orders are rewarded

        R-007.2 A discount code cannot be combined with a bulk discount.
        - Why: the margin would be lost

        R-007.3 Codes expire after 30 days.
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "specify", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [], "approvals": []}
        """
      When alice runs approve with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | rules     |
        | arg | --summary |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007 rules, not approved before: 3 rules.
          R-007.1  Orders of 1000 or more get 10% off.
            Why: big orders are rewarded
          R-007.2  A discount code cannot be combined with a bulk discount.
            Why: the margin would be lost
          R-007.3  Codes expire after 30 days.
        """

    @EX-113.1.2
    Scenario: Rules written in Chinese stay in Chinese
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        # Rules: FEAT-007 折扣

        R-007.1 订单满1000元打九折。
        - Why: 鼓励大额订单
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "折扣", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "specify", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [], "approvals": []}
        """
      When alice runs approve with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | rules     |
        | arg | --summary |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007 rules, not approved before: 1 rule.
          R-007.1  订单满1000元打九折。
            Why: 鼓励大额订单
        """

  @R-113.2
  Rule: After a change the summary lists only what changed since the last approval

    @EX-113.2.1
    Scenario: Changed, added and removed rules are listed and the unchanged one is not
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        # Rules: FEAT-007 Discounts

        R-007.1 Orders of 1000 or more get 10% off.
        - Why: big orders are rewarded

        R-007.2 A discount code cannot be combined with a bulk discount.
        - Why: the margin would be lost

        R-007.4 Codes expire after 30 days.
        - Why: old codes pile up
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "specify", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [],
         "approvals": [{"id": 1, "gate": "rules", "decision": "approve", "grade": "hook", "origin": "human",
                        "at": "2026-11-08T10:30:00+00:00", "reason": "", "artifacts": {}, "members": {},
                        "items": {"R-007.1": {"text": "Orders of 1000 or more get 10% off.", "parts": {"why": "dd0a316e18d40564"}},
                                  "R-007.2": {"text": "A discount code can be combined with a bulk discount.", "parts": {"why": "cfb731472200b3af"}},
                                  "R-007.3": {"text": "Gift cards give no discount.", "parts": {}}},
                        "session": null, "prompt_id": "p1", "transcript_path": null, "source": null, "mode": "auto",
                        "hooks_seen": true, "autonomy": "standard"}]}
        """
      When alice runs approve with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | rules     |
        | arg | --summary |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007 rules, since the approval of 2026-11-08: 1 rule changed, 1 added, 1 removed.
        Changed:
          R-007.2  A discount code cannot be combined with a bulk discount.
            Why: the margin would be lost
            changed: statement
            was: A discount code can be combined with a bulk discount.
        Added:
          R-007.4  Codes expire after 30 days.
            Why: old codes pile up
        Removed:
          R-007.3  Gift cards give no discount.
        Unchanged: 1 rule (not shown).
        """

    @EX-113.2.2
    Scenario: Two changed scenarios and one added scenario are listed in plain words
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Order discounts

          @R-007.1
          Rule: Orders of 1000 or more get 10% off

            @EX-007.1.1
            Scenario: An order of 1000 gets the discount
              Given an order of 1000
              When the order is priced
              Then the discount is 10%

            @EX-007.1.2
            Scenario: An order below 1000 gets no discount
              Given an order of 900
              When the order is priced
              Then there is no discount

            @EX-007.1.3
            Scenario: A large order gets the discount
              Given an order of 5000
              When the order is priced
              Then the discount is 10%

          @R-007.2
          Rule: A discount code gives 5 off

            @EX-007.2.1
            Scenario: A valid code takes 5 off
              Given an order of 100
              And the code SAVE5
              When the order is priced
              Then the total is 95
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "examples", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [],
         "approvals": [{"id": 1, "gate": "examples", "decision": "approve", "grade": "hook", "origin": "human",
                        "at": "2026-11-08T10:30:00+00:00", "reason": "", "artifacts": {}, "members": {},
                        "items": {"EX-007.1.1": {"text": "An order of 1000 gets the discount", "parts": {"steps": "6b2ead113fac9d30"}, "rule": "R-007.1"},
                                  "EX-007.1.2": {"text": "An order below 1000 gets no discount", "parts": {"steps": "932adb482621a63e"}, "rule": "R-007.1"},
                                  "EX-007.1.3": {"text": "An order of 5000 gets the discount", "parts": {"steps": "f27ed820e3ecf3a9"}, "rule": "R-007.1"}},
                        "session": null, "prompt_id": "p1", "transcript_path": null, "source": null, "mode": "auto",
                        "hooks_seen": true, "autonomy": "standard"}]}
        """
      When alice runs approve with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | examples  |
        | arg | --summary |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007 examples, since the approval of 2026-11-08: 2 scenarios changed, 1 added.
        Changed:
          EX-007.1.2  An order below 1000 gets no discount  (R-007.1)
            Given an order of 900
            When the order is priced
            Then there is no discount
            changed: steps
          EX-007.1.3  A large order gets the discount  (R-007.1)
            Given an order of 5000
            When the order is priced
            Then the discount is 10%
            changed: title
            was: An order of 5000 gets the discount
        Added:
          EX-007.2.1  A valid code takes 5 off  (R-007.2)
            Given an order of 100
            And the code SAVE5
            When the order is priced
            Then the total is 95
        Unchanged: 1 scenario (not shown).
        """

    @EX-113.2.3
    Scenario: Scenarios written in Chinese keep their keywords and words
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file feature file contains:
        """
        # language: zh-CN
        @FEAT-007
        功能: 订单折扣

          @R-007.1
          规则: 满1000元打九折

            @EX-007.1.1
            场景: 订单满1000元享受折扣
              假如 订单金额为1000元
              当 系统计算订单价格
              那么 折扣为10%

            @EX-007.1.2
            场景: 订单不满1000元没有折扣
              假如 订单金额为999元
              当 系统计算订单价格
              那么 没有折扣
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "折扣", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "examples", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [],
         "approvals": [{"id": 1, "gate": "examples", "decision": "approve", "grade": "hook", "origin": "human",
                        "at": "2026-11-08T10:30:00+00:00", "reason": "", "artifacts": {}, "members": {},
                        "items": {"EX-007.1.1": {"text": "订单满1000元享受折扣", "parts": {"steps": "e87084caac8f896a"}, "rule": "R-007.1"}},
                        "session": null, "prompt_id": "p1", "transcript_path": null, "source": null, "mode": "auto",
                        "hooks_seen": true, "autonomy": "standard"}]}
        """
      When alice runs approve with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | examples  |
        | arg | --summary |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007 examples, since the approval of 2026-11-08: 1 added.
        Added:
          EX-007.1.2  订单不满1000元没有折扣  (R-007.1)
            假如 订单金额为999元
            当 系统计算订单价格
            那么 没有折扣
        Unchanged: 1 scenario (not shown).
        """

  @R-113.3
  Rule: The summary only reads and records nothing

    @EX-113.3.1
    Scenario: A summary that is asked to record an approval is refused and nothing is recorded
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "specify", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [], "approvals": []}
        """
      When alice runs approve with:
        | key | value           |
        | arg | FEAT-007        |
        | arg | rules           |
        | arg | --summary       |
        | arg | --self-reported |
      Then the command fails with usage error
      And the output file discounts state contains:
        """
        "approvals": []
        """

  @R-113.4
  Rule: A message that holds more than one approval command is refused with the reason

    @EX-113.4.1
    Scenario: An approval command followed by a sentence records nothing and says why
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs create feature with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | --title   |
        | arg | Discounts |
      And alice runs the approval hook with:
        | key   | value                                                                         |
        | stdin | {"prompt_id":"p","prompt":"/greenlight:approve FEAT-007 rules thanks, go on"} |
      Then the command succeeds
      And the stdout output contains:
        """
        NOT recorded: send one approval per message
        """
      And the output file discounts state contains:
        """
        "approvals": []
        """

    @EX-113.4.2
    Scenario: Two approval commands in one message record nothing and say why
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs create feature with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | --title   |
        | arg | Discounts |
      And alice runs the approval hook with:
        | key   | value                                                                                   |
        | stdin | {"prompt":"/greenlight:approve FEAT-007 rules /greenlight:approve FEAT-007 examples"} |
      Then the command succeeds
      And the stdout output contains:
        """
        NOT recorded: send one approval per message
        """
      And the output file discounts state contains:
        """
        "approvals": []
        """

  @R-113.5
  Rule: An approval that cannot be verified does not take away a verified one for the same files

    @EX-113.5.1
    Scenario: A later approval that cannot be verified leaves the verified one counting for the same file
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "test-design", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [],
         "approvals": [{"id": 1, "gate": "rules", "decision": "approve", "grade": "hook", "origin": "human",
                        "at": "2026-11-08T10:30:00+00:00", "reason": "", "members": {}, "items": null,
                        "artifacts": {".bdd/features/FEAT-007-discounts/rules.md": "e6f0fa037e75a9b5be245c3219001ce18c87928b2c0266b8d64496024c91f759"},
                        "session": null, "prompt_id": "p1", "transcript_path": null, "source": null, "mode": "auto",
                        "hooks_seen": true, "autonomy": "standard"},
                       {"id": 2, "gate": "rules", "decision": "approve", "grade": "hook", "origin": "unverifiable",
                        "at": "2026-11-08T11:00:00+00:00", "reason": "", "members": {}, "items": null,
                        "artifacts": {".bdd/features/FEAT-007-discounts/rules.md": "e6f0fa037e75a9b5be245c3219001ce18c87928b2c0266b8d64496024c91f759"},
                        "session": null, "prompt_id": "p2", "transcript_path": null, "source": null, "mode": "auto",
                        "hooks_seen": true, "autonomy": "standard"}]}
        """
      When alice runs approve with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --check  |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007: rules: valid (hook, origin human)
        """

    @EX-113.5.2
    Scenario: A file that changed after the verified approval is not covered by it
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 20% off.
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "test-design", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": true, "changes": [],
         "approvals": [{"id": 1, "gate": "rules", "decision": "approve", "grade": "hook", "origin": "human",
                        "at": "2026-11-08T10:30:00+00:00", "reason": "", "members": {}, "items": null,
                        "artifacts": {".bdd/features/FEAT-007-discounts/rules.md": "e6f0fa037e75a9b5be245c3219001ce18c87928b2c0266b8d64496024c91f759"},
                        "session": null, "prompt_id": "p1", "transcript_path": null, "source": null, "mode": "auto",
                        "hooks_seen": true, "autonomy": "standard"},
                       {"id": 2, "gate": "rules", "decision": "approve", "grade": "hook", "origin": "unverifiable",
                        "at": "2026-11-08T11:00:00+00:00", "reason": "", "members": {}, "items": null,
                        "artifacts": {".bdd/features/FEAT-007-discounts/rules.md": "0aedb602601a0180af5446412bdae94c60dadff9a94d0a36a051b0a8f85dd235"},
                        "session": null, "prompt_id": "p2", "transcript_path": null, "source": null, "mode": "auto",
                        "hooks_seen": true, "autonomy": "standard"}]}
        """
      When alice runs approve with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --check  |
      Then the command fails with violations found
      And the stdout output contains:
        """
        the rules approval could not be verified
        """
