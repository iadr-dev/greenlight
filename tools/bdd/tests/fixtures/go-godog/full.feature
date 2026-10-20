@FEAT-002
Feature: Every core step

  @R-002.1
  Rule: Orders can be placed and listed

    @EX-002.1.1
    Scenario: An order is placed and paid through a stub
      Given alice is signed in as member
      And the following order exist:
        | id | status |
        | 7  | placed |
      And payments responds to charge with:
        """
        {"ok": true}
        """
      And the express feature flag is on
      When alice calls place order with:
        | item | qty |
        | tea  | 2   |
      Then the request succeeds
      And the response contains:
        | status |
        | placed |
      And payments received charge with:
        | amount |
        | 900    |
      And the order records include:
        | id | status |
        | 7  | placed |

    @EX-002.1.2
    Scenario: A request without a sign-in is rejected
      When alice calls place order with:
        | item |
        | tea  |
      Then the request is rejected with unauthorised

    @EX-002.1.3
    Scenario: The clock moves on
      Given the current time is 2026-03-01T09:00:00Z
      When 2 days passes
      And alice calls look up time
      Then the response contains:
        | now                  |
        | 2026-03-03T09:00:00Z |

    @EX-002.1.4
    Scenario: Events come in and are published again by a job
      When the payment event is received with:
        | amount |
        | 900    |
      And the receipts job runs
      Then the receipt event is published with:
        | amount |
        | 900    |

    @EX-002.1.5
    Scenario: A job leaves other records alone
      Given the following invoice exist:
        | id | total |
        | 1  | 10    |
      When the receipts job runs
      Then no invoice records changed
      And the invoice records are:
        | id | total |
        | 1  | 10    |

    @EX-002.1.6
    Scenario: Listing orders runs a bounded number of queries
      Given alice is signed in as member
      And the following order exist:
        | id |
        | 1  |
        | 2  |
        | 3  |
      When alice calls list orders
      Then list orders ran at most 2 queries

    @EX-002.1.7
    Scenario: A command reads a file the scenario made
      Given the input file report contains:
        """
        hello
        """
      When alice runs show version
      Then the command succeeds
      And the stdout output contains:
        """
        go version
        """
      And the output file report contains:
        """
        hello
        """

    @EX-002.1.8
    Scenario: A misused command fails in the expected way
      When alice runs misuse the tool
      Then the command fails with unknown command

    @EX-002.1.9
    Scenario: A library call returns a result and an error
      When describe is called with:
        | name |
        | tea  |
      Then the result includes:
        | name |
        | tea  |
      When refuse is called with:
        | name |
        | tea  |
      Then the call fails with refusal

  @R-002.2
  Rule: A query per record is caught

    @EX-002.2.1
    Scenario: A query per order is an N+1 problem
      Given the n-plus-one feature flag is on
      And alice is signed in as member
      And the following order exist:
        | id |
        | 1  |
        | 2  |
        | 3  |
      When alice calls list orders
      Then list orders ran at most 2 queries
