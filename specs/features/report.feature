@FEAT-104
Feature: A feature can be read as a web page
  A person who does not use a terminal can open one page that shows what a feature promises and what the records say
  about it.

  @R-104.1
  Rule: The report names the feature and says what it does not know yet

    @EX-104.1.1
    Scenario: A feature that has just been created
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
      And alice runs report with:
        | key | value    |
        | arg | FEAT-007 |
      Then the command succeeds
      And the stdout output contains:
        """
        <h1>FEAT-007: Discounts</h1>
        """
      And the stdout output contains:
        """
        No audit report yet
        """

  @R-104.2
  Rule: A feature that does not exist is refused

    @EX-104.2.1
    Scenario: An unknown feature
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs report with:
        | key | value    |
        | arg | FEAT-099 |
      Then the command fails with usage error
