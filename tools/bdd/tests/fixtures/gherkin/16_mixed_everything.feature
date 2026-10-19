# language: en
@FEAT-099
Feature: Everything together
  Prose.

  Background:
    Given the clock is frozen at "2026-01-01"

  @R-099.1
  Rule: Expiry

    @EX-099.1.1
    Scenario Outline: Coupon expiry
      Given a coupon expiring on <date>
      When the shopper applies it
      Then the result is <result>
        | key | value |
        | a   | b     |

      Examples:
        | date       | result   |
        | 2025-12-31 | rejected |
        | 2026-01-01 | accepted |

    @EX-099.1.2
    Scenario: Doc string payload
      Given the request body:
        """
        {"coupon": "X"}
        """
      Then it is accepted
