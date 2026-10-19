Feature: Prose that looks like steps
  Given that customers differ, we model three kinds.
  When a customer is unknown we treat them as a guest.
  Then everything below is real.

  Rule: Guests pay full price
    Then this is rule description, not a step.

    Scenario: Guest checkout
      Given a guest
      When they buy
      Then they pay full price
