@FEAT-102
Feature: Approved specifications are locked by hash
  Once the examples are approved, the feature files are locked. A change to a locked file is detected, and the lock
  can only be released with a reason that is kept.

  @R-102.1
  Rule: A lock records the files, and a check passes while they are unchanged

    @EX-102.1.1
    Scenario: Locking and checking an untouched feature
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
        Feature: Discounts
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      When alice runs lock with:
        | key | value |
        | arg | FEAT-007 |
        | arg | --scope |
        | arg | spec |
      Then the command succeeds
      And the stdout output contains:
        """
        locked FEAT-007 spec
        """

  @R-102.2
  Rule: A locked file that changed afterwards is detected, and a feature that was never locked fails a required check

    @EX-102.2.1
    Scenario: A file that differs from its recorded hash fails the check
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
        Feature: Discounts
        """
      And the input file lock record contains:
        """
        {"schema": 1, "feature": "FEAT-007", "history": [],
         "scopes": {"spec": {"locked_at": "2026-01-01T00:00:00+00:00",
                             "files": {"features/discounts.feature": "0000000000000000000000000000000000000000000000000000000000000000"}}}}
        """
      When alice runs lock with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --check  |
      Then the command fails with violations found
      And the stdout output contains:
        """
        changed since it was locked
        """

    @EX-102.2.2
    Scenario: A feature that was never locked fails a required check
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
        Feature: Discounts
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      When alice runs lock with:
        | key | value     |
        | arg | FEAT-007  |
        | arg | --check   |
        | arg | --require |
      Then the command fails with violations found
      And the stdout output contains:
        """
        is not locked
        """

  @R-102.3
  Rule: A lock cannot be released without saying why

    @EX-102.3.1
    Scenario: Unlocking without a reason is refused
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
        Feature: Discounts
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      When alice runs unlock with:
        | key | value |
        | arg | FEAT-007 |
        | arg | --scope |
        | arg | spec |
      Then the command fails with usage error
      And the stderr output contains:
        """
        --reason
        """
