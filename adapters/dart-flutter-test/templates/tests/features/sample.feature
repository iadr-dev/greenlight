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
  Rule: The counter shows how many times the button was pressed

    @EX-000.2.1
    Scenario: Pressing the button adds one
      Given the application state is:
        | key   | value |
        | start | 4     |
      When alice opens the counter page
      And alice clicks add button
      Then alice sees count showing:
        | text |
        | 5    |
