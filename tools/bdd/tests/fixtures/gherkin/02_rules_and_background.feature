@FEAT-007
Feature: Order discounts
  As a shopper I want discounts
  so that I pay less.

  Background:
    Given the following products exist:
      | sku | price |
      | A1  | 100   |

  @R-007.1
  Rule: Bulk orders get ten percent off

    Background:
      Given a registered shopper

    @EX-007.1.1
    Scenario: Exactly at the threshold
      Given a cart worth 1000
      When the shopper checks out
      Then the total is 900

    @EX-007.1.2
    Scenario: Just below the threshold
      Given a cart worth 999
      When the shopper checks out
      Then the total is 999

  @R-007.2
  Rule: Coupons cannot be stacked

    @EX-007.2.1
    Scenario: Two coupons
      Given a cart worth 100
      When the shopper applies coupons "A" and "B"
      Then the request is rejected with "stacking-not-allowed"
