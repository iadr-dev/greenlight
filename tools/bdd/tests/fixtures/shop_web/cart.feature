@FEAT-020
Feature: The shop's cart and checkout
  A visitor signs in to use the cart; the cart shows what it holds; checkout says why it cannot place an order.

  @R-020.1
  Rule: Only a signed-in customer reaches the cart

    @EX-020.1.1
    Scenario: A visitor is sent to the sign-in page
      When alice opens the cart page
      Then alice sees page heading showing:
        | text    |
        | Sign in |

    @EX-020.1.2
    Scenario: A signed-in customer sees an empty cart
      Given alice is signed in as customer
      When alice opens the cart page
      Then alice sees empty cart message showing:
        | text               |
        | Your cart is empty |

  @R-020.2
  Rule: The cart shows the total of its lines

    @EX-020.2.1
    Scenario: Two teas and a mug
      Given alice is signed in as customer
      And the following cart item exist:
        | user  | sku | quantity |
        | alice | tea | 2        |
        | alice | mug | 1        |
      When alice opens the cart page
      Then alice sees cart total showing:
        | text   |
        | $17.00 |

  @R-020.3
  Rule: Checkout says why it cannot place an order

    @EX-020.3.1
    Scenario: An empty cart cannot be checked out
      Given alice is signed in as customer
      And the following order exist:
        | user  | total |
        | alice | 100   |
      When alice opens the checkout page
      And alice clicks place order button
      Then alice sees checkout error showing:
        | text               |
        | Your cart is empty |
      And no order records changed

    @EX-020.3.2
    Scenario: A declined card keeps the cart and places nothing
      Given alice is signed in as customer
      And the following order exist:
        | user  | total |
        | alice | 100   |
      And the following cart item exist:
        | user  | sku | quantity |
        | alice | tea | 1        |
      When alice opens the checkout page
      And alice fills card number with:
        | value            |
        | 4000000000000002 |
      And alice clicks place order button
      Then alice sees checkout error showing:
        | text                    |
        | Your card was declined |
      And no order records changed

    @EX-020.3.3
    Scenario: A valid card places the order
      Given alice is signed in as customer
      And the following cart item exist:
        | user  | sku | quantity |
        | alice | tea | 1        |
      When alice opens the checkout page
      And alice fills card number with:
        | value            |
        | 4242424242424242 |
      And alice clicks place order button
      Then the order records are:
        | id | user  | total |
        | 1  | alice | 450   |
