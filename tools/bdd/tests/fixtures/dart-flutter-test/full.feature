@FEAT-002
Feature: Every core step

  @R-002.1
  Rule: Orders can be placed and listed

    @EX-002.1.1
    Scenario: An order is placed through a stub and listed
      Given alice is signed in as member
      And the following order exist:
        | id | status |
        | 7  | placed |
      And payments responds to charge with:
        """
        {"ok": true}
        """
      And the express feature flag is on
      When alice opens the orders page
      And alice clicks place order button
      Then alice sees order list showing:
        | item     |
        | 7 placed |
        | 8 placed |
      And payments received charge with:
        | amount |
        | 900    |
      And the order records include:
        | id | status |
        | 8  | placed |

    @EX-002.1.2
    Scenario: The clock moves on
      Given the current time is 2026-03-01T09:00:00Z
      When 2 days passes
      And alice opens the clock page
      Then alice sees time showing:
        | text                 |
        | 2026-03-03T09:00:00Z |

    @EX-002.1.3
    Scenario: Events come in and are published again by a job
      When the payment event is received with:
        | amount |
        | 900    |
      And the receipts job runs
      Then the receipt event is published with:
        | amount |
        | 900    |

    @EX-002.1.4
    Scenario: A job leaves other records alone
      Given the following invoice exist:
        | id | total |
        | 1  | 10    |
      When the receipts job runs
      Then no invoice records changed
      And the invoice records are:
        | id | total |
        | 1  | 10    |

  @R-002.2
  Rule: A form can be filled in

    @EX-002.2.1
    Scenario: A person fills in and agrees
      When alice opens the form page
      Then alice sees error message showing:
        | text        |
        | Agree first |
      When alice fills name field with:
        | value |
        | Ada   |
      And alice toggles agree box
      Then alice sees name field showing:
        | value |
        | Ada   |
      And alice sees agree box showing:
        | checked |
        | true    |
      And alice sees submit button showing:
        | enabled |
        | true    |
      And alice does not see error message

    @EX-002.2.2
    Scenario: A choice is selected from a menu
      When alice opens the form page
      And alice selects size menu with:
        | value |
        | Large |
      Then alice sees size menu showing:
        | text  |
        | Large |

  @R-002.3
  Rule: The application state is read and checked

    @EX-002.3.1
    Scenario: A setting starts from the state the scenario gave
      Given the application state is:
        | key   | value |
        | theme | dark  |
      When alice opens the settings page
      Then alice sees theme label showing:
        | text |
        | dark |
      And the application state includes:
        | key   | value |
        | theme | dark  |

  @R-002.4
  Rule: A library call returns a result or an error

    @EX-002.4.1
    Scenario: A library call returns a result and an error
      When describe is called with:
        | name |
        | tea  |
      Then the result includes:
        | name |
        | tea  |
      When add is called with:
        | a | b |
        | 2 | 3 |
      Then the result is:
        """
        5
        """
      When refuse is called with:
        | name |
        | tea  |
      Then the call fails with refusal
