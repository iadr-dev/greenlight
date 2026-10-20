@FEAT-000
Feature: Sample (delete me)
  A feature that passes on a fresh scaffold, to prove the setup works before the first real one.

  @R-000.1
  Rule: Seeded records can be read back

    @EX-000.1.1
    Scenario: A product is stored and read back
      Given the following product exist:
        | id | name |
        | 1  | tea  |
      Then the product records are:
        | id | name |
        | 1  | tea  |

  @R-000.2
  Rule: A call to a stubbed dependency is recorded

    @EX-000.2.1
    Scenario: The nightly job charges the payment provider
      Given payments responds to charge with:
        """
        {"ok": true}
        """
      When the nightly job runs
      Then payments received charge with:
        | amount |
        | 5      |
