@FEAT-000
Feature: Sample (delete me)
  A feature that passes on a fresh scaffold, to prove the setup works before the first real one.

  @R-000.1
  Rule: The sample page greets the visitor and counts clicks

    @EX-000.1.1
    Scenario: The greeting is shown
      When alice opens the sample page
      Then alice sees greeting showing:
        | text  |
        | Hello |

    @EX-000.1.2
    Scenario: A click is counted
      Given the application state is:
        | key   | value |
        | count | 5     |
      When alice opens the sample page
      And alice clicks add one button
      Then alice sees counter showing:
        | text |
        | 6    |
      And the application state includes:
        | key   | value |
        | count | 6     |
