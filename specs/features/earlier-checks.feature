@FEAT-112
Feature: Checks a rule can make are made before the auditor
  A check that needs no judgment belongs to a command, not to the auditor at the end. A mixed column set for one
  entity, an @existing tag on a scenario that failed its red run, and a boundary rule with no edge recorded are
  refused where they are written, with a message that names the example and what to do. Each check has a way to say
  that the case does not apply, so no one is stopped by a gate they cannot pass.

  @R-112.1
  Rule: The exact record tables of one entity use one column set, unless the driver reads the listed ones

    @EX-112.1.1
    Scenario: Two exact tables of one entity with different columns are refused
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
        Feature: Companies

          @R-007.1
          Rule: A company keeps its name and phone

            @EX-007.1.1
            Scenario: A new company
              Given alice is signed in as owner
              Then the company records are:
                | name |
                | Anju |

            @EX-007.1.2
            Scenario: A company with a phone
              Given alice is signed in as owner
              Then the company records are:
                | name | phone     |
                | Anju | 02-2365-8 |
        """
      When alice runs lint with:
        | key | value    |
        | arg | features |
      Then the command fails with violations found
      And the stdout output contains:
        """
        EX-007.1.2: company table has columns name, phone; EX-007.1.1 has name; check one column set per entity
        """

    @EX-112.1.2
    Scenario: One column set, an empty table and a partial check pass
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
        Feature: Companies

          @R-007.1
          Rule: A company keeps its name and phone

            @EX-007.1.1
            Scenario: A new company
              Given alice is signed in as owner
              Then the company records are:
                | name | phone |
                | Anju |       |

            @EX-007.1.2
            Scenario: A company with a phone
              Given alice is signed in as owner
              Then the company records are:
                | name | phone     |
                | Anju | 02-2365-8 |

            @EX-007.1.3
            Scenario: Nothing was created
              Given alice is signed in as owner
              Then the company records are:
                | name |

            @EX-007.1.4
            Scenario: Only the phone is checked
              Given alice is signed in as owner
              Then the company records include:
                | phone     |
                | 02-2365-8 |
        """
      When alice runs lint with:
        | key | value    |
        | arg | features |
      Then the command succeeds

    @EX-112.1.3
    Scenario: A project whose driver reads only the listed columns says so and passes
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"

        [lint]
        projected_records = ["company"]
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Companies

          @R-007.1
          Rule: A company keeps its name and phone

            @EX-007.1.1
            Scenario: A new company
              Given alice is signed in as owner
              Then the company records are:
                | name |
                | Anju |

            @EX-007.1.2
            Scenario: A company with a phone
              Given alice is signed in as owner
              Then the company records are:
                | name | phone     |
                | Anju | 02-2365-8 |
        """
      When alice runs lint with:
        | key | value    |
        | arg | features |
      Then the command succeeds

  @R-112.2
  Rule: A scenario tagged @existing that failed in the red run makes the red invalid

    @EX-112.2.1
    Scenario: An @existing scenario that failed is named
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"

        [adapters.run]
        by_tag = 'python runner.py --tag {marker}'
        report = '--out {out}'

        [adapters.classify]
        test_defect = ['ImportError']
        expected_fail = ['AssertionError']
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Big orders get 10% off

            @existing @EX-007.1.1
            Scenario: Order of exactly 1000
              Then the request succeeds
        """
      And the input file recorded run contains:
        """
        {"schema": 1, "feature": "FEAT-007", "mode": "plain", "seed": null, "at": "2026-11-09T10:00:00+00:00",
         "cases": [{"name": "test_order_of_exactly_1000", "classname": "t", "outcome": "failed",
                    "text": "AssertionError: 404 != 200"}]}
        """
      When alice runs classify with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --expect |
        | arg | red      |
      Then the command fails with violations found
      And the stdout output contains:
        """
        "Order of exactly 1000" is tagged @existing but failed in the red run
        """

    @EX-112.2.2
    Scenario: An @existing scenario that passed is accepted
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"

        [adapters.run]
        by_tag = 'python runner.py --tag {marker}'
        report = '--out {out}'

        [adapters.classify]
        test_defect = ['ImportError']
        expected_fail = ['AssertionError']
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Big orders get 10% off

            @existing @EX-007.1.1
            Scenario: Order of exactly 1000
              Then the request succeeds
        """
      And the input file recorded run contains:
        """
        {"schema": 1, "feature": "FEAT-007", "mode": "plain", "seed": null, "at": "2026-11-09T10:00:00+00:00",
         "cases": [{"name": "test_order_of_exactly_1000", "classname": "t", "outcome": "passed", "text": ""}]}
        """
      When alice runs classify with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --expect |
        | arg | red      |
      Then the command succeeds

  @R-112.3
  Rule: A rule that uses the boundary card records the edges of what it limits, or says there is no such boundary

    @EX-112.3.1
    Scenario: A date rule with no leap day is refused at the test-design gate
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        R-007.1 A delivery date is a calendar date no earlier than today.
        """
      And the input file test design contains:
        """
        ## R-007.1 A delivery date is a calendar date no earlier than today

        Techniques: boundary-value

        - EX-007.1.1 Delivery today is accepted (boundary-value: on the edge)
        - EX-007.1.2 Delivery yesterday is refused (boundary-value: just outside)
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-09T10:00:00+00:00",
         "phase": "test-design", "autonomy": {"level": "standard", "switches": []},
         "gates": {"discover": {"result": "pass", "at": "2026-11-09T10:00:00+00:00", "detail": {}, "session": null}},
         "approvals": [{"id": 1, "gate": "rules", "decision": "approve", "reason": "", "grade": "self-reported",
                        "origin": "self-reported", "mode": "auto", "autonomy": "standard", "hooks_seen": false,
                        "at": "2026-11-09T10:00:00+00:00", "session": null, "prompt_id": null, "source": null,
                        "transcript_path": null, "members": {},
                        "artifacts": {".bdd/features/FEAT-007-discounts/rules.md": "8eeb56d1a09167a84512d9e01cb25b9157d2b4177c409fb75b84a76c0cf72732"}}],
         "assumptions": [], "cost": {}, "red": null, "hooks_seen": false, "changes": []}
        """
      When alice runs gate with:
        | key | value       |
        | arg | FEAT-007    |
        | arg | test-design |
        | arg | --result    |
        | arg | pass        |
      Then the command fails with refused
      And the stderr output contains:
        """
        R-007.1 uses the boundary-value card for a date but records no leap day
        """

    @EX-112.3.2
    Scenario: The same rule with the leap day as an example passes the gate
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        R-007.1 A delivery date is a calendar date no earlier than today.
        """
      And the input file test design contains:
        """
        ## R-007.1 A delivery date is a calendar date no earlier than today

        Techniques: boundary-value

        - EX-007.1.1 Delivery today is accepted (boundary-value: on the edge)
        - EX-007.1.2 Delivery yesterday is refused (boundary-value: just outside)
        - EX-007.1.3 Delivery on 29 February 2028 is accepted (boundary-value: the leap day)
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-09T10:00:00+00:00",
         "phase": "test-design", "autonomy": {"level": "standard", "switches": []},
         "gates": {"discover": {"result": "pass", "at": "2026-11-09T10:00:00+00:00", "detail": {}, "session": null}},
         "approvals": [{"id": 1, "gate": "rules", "decision": "approve", "reason": "", "grade": "self-reported",
                        "origin": "self-reported", "mode": "auto", "autonomy": "standard", "hooks_seen": false,
                        "at": "2026-11-09T10:00:00+00:00", "session": null, "prompt_id": null, "source": null,
                        "transcript_path": null, "members": {},
                        "artifacts": {".bdd/features/FEAT-007-discounts/rules.md": "8eeb56d1a09167a84512d9e01cb25b9157d2b4177c409fb75b84a76c0cf72732"}}],
         "assumptions": [], "cost": {}, "red": null, "hooks_seen": false, "changes": []}
        """
      When alice runs gate with:
        | key | value       |
        | arg | FEAT-007    |
        | arg | test-design |
        | arg | --result    |
        | arg | pass        |
      Then the command succeeds

    @EX-112.3.3
    Scenario: A rule that says why it has no leap day passes the gate
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        R-007.1 A delivery date is a calendar date no earlier than today.
        """
      And the input file test design contains:
        """
        ## R-007.1 A delivery date is a calendar date no earlier than today

        Techniques: boundary-value

        - EX-007.1.1 Delivery today is accepted (boundary-value: on the edge)
        - EX-007.1.2 Delivery yesterday is refused (boundary-value: just outside)
        - No leap day boundary: the date is only compared with today, never added to or counted from
        """
      And the input file discounts state contains:
        """
        {"schema": 1, "feature": "FEAT-007", "kind": "feature", "title": "Discounts", "created_at": "2026-11-09T10:00:00+00:00",
         "phase": "test-design", "autonomy": {"level": "standard", "switches": []},
         "gates": {"discover": {"result": "pass", "at": "2026-11-09T10:00:00+00:00", "detail": {}, "session": null}},
         "approvals": [{"id": 1, "gate": "rules", "decision": "approve", "reason": "", "grade": "self-reported",
                        "origin": "self-reported", "mode": "auto", "autonomy": "standard", "hooks_seen": false,
                        "at": "2026-11-09T10:00:00+00:00", "session": null, "prompt_id": null, "source": null,
                        "transcript_path": null, "members": {},
                        "artifacts": {".bdd/features/FEAT-007-discounts/rules.md": "8eeb56d1a09167a84512d9e01cb25b9157d2b4177c409fb75b84a76c0cf72732"}}],
         "assumptions": [], "cost": {}, "red": null, "hooks_seen": false, "changes": []}
        """
      When alice runs gate with:
        | key | value       |
        | arg | FEAT-007    |
        | arg | test-design |
        | arg | --result    |
        | arg | pass        |
      Then the command succeeds
