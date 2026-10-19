import unittest

from bddlib.denylist import implementation_details


def categories(text: str) -> list[str]:
    return [category for category, _ in implementation_details(text)]


class DetectsImplementationDetailsTest(unittest.TestCase):
    def test_each_category(self):
        cases = {
            "URL": ["Alice opens https://shop.test/cart", "Alice visits www.example.com"],
            "HTTP verb with a path": ["Alice sends GET /orders", "the client does POST /api/orders"],
            "URL path": ["Alice opens /api/orders/12", "Alice requests /orders/{id}/items"],
            "HTTP status code": ["the response is HTTP 404", "it returns status 500", "it returns status code 201"],
            "SQL": ["the table is read with SELECT * FROM orders", "it runs INSERT INTO orders",
                    "it runs DELETE FROM carts", "the team runs DROP TABLE users"],
            "CSS or DOM selector": ["Alice clicks #submit-btn", "the page has a data-testid", "it uses querySelector",
                                    "found by xpath", 'it matches css=.btn', 'the element has className=big'],
            "HTML markup": ['Alice sees <div class="x"> on screen', "the text ends with </div>"],
            "code call": ["Alice calls cart.add(item)", "the test invokes .click()"],
            "class name": ["the OrderController handles it", "OrderService is called", "the UserRepository saves it"],
        }
        for category, texts in cases.items():
            for text in texts:
                with self.subTest(category=category, text=text):
                    self.assertIn(category, categories(text))

    def test_the_match_is_reported(self):
        ((category, snippet),) = implementation_details("Alice sends GET /orders")
        self.assertEqual((category, snippet), ("HTTP verb with a path", "GET /"))

    def test_several_categories_at_once(self):
        found = categories("Alice sends GET /api/orders and expects HTTP 200")
        self.assertEqual(found, ["HTTP verb with a path", "URL path", "HTTP status code"])


class LeavesBusinessLanguageAloneTest(unittest.TestCase):
    def test_business_wording_is_not_flagged(self):
        for text in [
            "Alice has a cart worth 999",
            "the request is rejected",
            "Alice calls quote.create",                     # a logical operation name, not a code call
            "the order ships on 2026/01/01 and/or later",   # dates and 'and/or' are not paths
            "issue #5 is closed",                           # '#5' is not an element id
            "we update the cart and select a payment method",   # SQL words in lowercase prose
            "the status is 7",                              # not an HTTP status
            "the shopper approx. pays 5",
            "the Order is confirmed",                       # capitalised noun, no layer suffix
        ]:
            with self.subTest(text=text):
                self.assertEqual(implementation_details(text), [])

    def test_quoted_values_are_data_not_details(self):
        for text in ['Alice sees "https://example.com" in the footer',
                     'the message is "POST /orders failed"',
                     'the code is "SELECT * FROM x"']:
            with self.subTest(text=text):
                self.assertEqual(implementation_details(text), [])

    def test_outline_parameters_and_placeholders_are_not_markup(self):
        for text in ["a parcel of <kg> kg", "Alice has a cart worth <amount>", "{actor} has a cart worth {amount:int}",
                     "Alice opens the <page> page"]:
            with self.subTest(text=text):
                self.assertEqual(implementation_details(text), [])


if __name__ == "__main__":
    unittest.main()
