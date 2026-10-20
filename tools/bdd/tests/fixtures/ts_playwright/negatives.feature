@FEAT-011
Feature: Failures of the Playwright adapter
  Each scenario is wrong on purpose, and must fail in the way the red gate expects.

  @R-011.1
  Rule: Every wrong expectation is reported as a failure

    @EX-011.1.1
    Scenario: A page that calls an unstubbed dependency
      When alice opens the shop page
      Then alice sees result showing:
        | text  |
        | error |

    @EX-011.1.2
    Scenario: A page that reaches outside
      When alice opens the leak page
      Then alice sees result showing:
        | text    |
        | blocked |

    @EX-011.1.3
    Scenario: Wrong text on the page
      When alice opens the sample page
      Then alice sees greeting showing:
        | text    |
        | Goodbye |

    @EX-011.1.4
    Scenario: Wrong application state
      When alice opens the sample page
      Then the application state includes:
        | key   | value |
        | count | 99    |

    @EX-011.1.5
    Scenario: Wrong records
      Given the following order exist:
        | id |
        | 1  |
      Then the order records are:
        | id |
        | 2  |

    @EX-011.1.6
    Scenario: A component nobody mapped
      When alice opens the sample page
      Then alice does not see unicorn

    @EX-011.1.7
    Scenario: Time passes before it was set
      When 3 hours passes

    @EX-011.1.8
    Scenario: Records that were never tracked
      Then no order records changed

    @EX-011.1.9
    Scenario: A page that needs an application nobody started
      When alice opens the orders page

    @EX-011.1.10
    Scenario: A dependency nobody knows
      Given mailer responds to send with:
        | ok   |
        | true |
