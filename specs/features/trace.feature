@FEAT-104
Feature: Trace shows how rules, examples and scenarios connect
  The traceability matrix is built from the rules file and the tagged scenarios alone, and it names every gap.

  @R-104.1
  Rule: A rule with examples and scenarios traces without gaps

    @EX-104.1.1
    Scenario: A complete feature has no gaps
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
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Big orders get a discount

            @EX-007.1.1
            Scenario: On the threshold
              Given alice is signed in as member
              Then the request succeeds
        """
      When alice runs trace with:
        | key | value    |
        | arg | FEAT-007 |
      Then the command succeeds
      And the stdout output contains:
        """
        No gaps.
        """

  @R-104.2
  Rule: A rule that has no example is reported, and the command fails so a gate can stop on it

    @EX-104.2.1
    Scenario: A rule without examples is a gap
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
        R-007.2 An order takes at most one coupon.
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Big orders get a discount

            @EX-007.1.1
            Scenario: On the threshold
              Given alice is signed in as member
              Then the request succeeds
        """
      When alice runs trace with:
        | key | value    |
        | arg | FEAT-007 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        R-007.2 has no example
        """
