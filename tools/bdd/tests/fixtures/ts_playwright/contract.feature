@FEAT-010
Feature: Core steps of the Playwright adapter
  Every core instruction of the base and ui profiles, once, against small pages and an in-memory system.

  @R-010.1
  Rule: A dependency is answered by what the scenario gave

    @EX-010.1.1
    Scenario: A stubbed dependency answers and is asked
      Given payments responds to charge with:
        | status |
        | paid   |
      When alice opens the shop page
      Then alice sees result showing:
        | text |
        | paid |
      And payments received charge with:
        | amount |
        | 5      |

  @R-010.2
  Rule: Time stands still until the scenario moves it

    @EX-010.2.1
    Scenario: The page shows the time the scenario set and the time that passed
      Given the current time is 2026-03-01 09:30
      When alice opens the clock page
      Then alice sees now showing:
        | text             |
        | 2026-03-01T09:30 |
      When 2 days passes
      Then alice sees now showing:
        | text             |
        | 2026-03-03T09:30 |

  @R-010.3
  Rule: A user can fill in, choose, tick and upload

    @EX-010.3.1
    Scenario: A form is filled in and saved
      When alice opens the form page
      And alice fills name field with:
        | value |
        | Ada   |
      And alice selects plan field with:
        | value |
        | pro   |
      And alice toggles agree box
      And alice uploads attachment field with:
        | file                   |
        | tests/sample/index.html |
      And alice clicks save button
      Then alice sees saved note showing:
        | text                                |
        | Ada \| pro \| agreed \| index.html |
      And alice sees remove button showing:
        | enabled |
        | false   |
      And alice does not see secret
      And alice sees steps showing:
        | item |
        | one  |
        | two  |

  @R-010.4
  Rule: The system behind the page is seeded, signed in and read through its seams

    @EX-010.4.1
    Scenario: Records, flags, jobs and events
      Given the following order exist:
        | id | status |
        | 1  | placed |
      And bob is signed in as admin
      And the beta feature flag is on
      When the order placed event is received with:
        | id |
        | 2  |
      And the nightly job runs
      Then the order records are:
        | id | status   |
        | 1  | archived |
        | 2  | archived |
      And the order records include:
        | id |
        | 2  |
      And the orders archived event is published with:
        | count |
        | 2     |
      And the flag records include:
        | flag | enabled |
        | beta | true    |
      And the login records include:
        | actor | role  |
        | bob   | admin |

    @EX-010.4.2
    Scenario: Nothing changes without an action
      Given the following order exist:
        | id | status |
        | 1  | placed |
      When the reporting job runs
      Then no order records changed

  @R-010.5
  Rule: A user can scroll, swipe and go back

    @EX-010.5.1
    Scenario: A list is scrolled down
      When alice opens the gestures page
      And alice scrolls feed with:
        | direction |
        | down      |
      Then alice sees scroll state showing:
        | text     |
        | scrolled |

    @EX-010.5.2
    Scenario: A card is swiped to the left
      When alice opens the gestures page
      And alice swipes deck with:
        | direction |
        | left      |
      Then alice sees swipe state showing:
        | text |
        | left |

    @EX-010.5.3
    Scenario: Going back returns to the page that was left
      When alice opens the gestures page
      And alice clicks next link
      And alice goes back
      Then alice sees page title showing:
        | text     |
        | Gestures |
