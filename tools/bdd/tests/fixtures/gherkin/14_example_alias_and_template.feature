Feature: Keyword aliases

  Example: Example is an alias for Scenario
    Given a thing

  Scenario Template: Template is an alias for Scenario Outline
    Given <x>

    Scenarios:
      | x |
      | 1 |
