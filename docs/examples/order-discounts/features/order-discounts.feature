@FEAT-007
Feature: Order discounts
  Big orders and coupon holders pay less.

  @R-007.1
  Rule: An order whose total is 1000 or more gets 10% off the total

    @EX-007.1.1
    Scenario: Just below the threshold
      Given alice is signed in as member
      When alice calls place order with:
        | total  |
        | 999.99 |
      Then the response contains:
        | discount |
        | 0        |

    @EX-007.1.2
    Scenario: Exactly on the threshold
      Given alice is signed in as member
      When alice calls place order with:
        | total   |
        | 1000.00 |
      Then the response contains:
        | total | discount |
        | 900   | 100      |

    @EX-007.1.3
    Scenario: A negative total is refused
      Given alice is signed in as member
      And the following order exist:
        | status |
        | placed |
      When alice calls place order with:
        | total |
        | -5    |
      Then the request is rejected with validation error
      And no order records changed

  @R-007.2
  Rule: An order takes at most one coupon

    @EX-007.2.1
    Scenario: A second coupon is refused
      Given alice is signed in as member
      And the following order exist:
        | status |
        | placed |
      When alice calls apply coupon with:
        | code   |
        | SAVE10 |
      And alice calls apply coupon with:
        | code   |
        | SAVE20 |
      Then the request is rejected with second coupon
      And no order records changed
