@FEAT-000
Feature: Sample (delete me)
  A feature that passes on a fresh scaffold, to prove the setup works before the first real one.

  @R-000.1
  Rule: Adding two non-negative numbers gives their sum

    @EX-000.1.1
    Scenario: Two numbers are added
      When add is called with:
        | a | b |
        | 2 | 3 |
      Then the result is:
        """
        5
        """

    @EX-000.1.2
    Scenario: A negative number is refused
      When add is called with:
        | a  | b |
        | -1 | 3 |
      Then the call fails with negative input

  @R-000.2
  Rule: Seeded records can be read back

    @EX-000.2.1
    Scenario: A product is stored and read back
      Given the following product exist:
        | id | name |
        | 1  | tea  |
      Then the product records are:
        | id | name |
        | 1  | tea  |
