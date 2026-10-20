"""The app's own small unit tests (not BDD). They prove the reference app works before greenlight touches it."""
import unittest

from fastapi.testclient import TestClient

from app.main import app, reset

client = TestClient(app)


class ShopApiTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_products(self):
        names = [p["sku"] for p in client.get("/products").json()]
        self.assertEqual(names, ["tea", "kettle", "mug"])

    def test_an_order_is_priced_from_the_products(self):
        response = client.post("/orders", json={"items": [{"sku": "tea", "qty": 2}, {"sku": "mug", "qty": 1}]})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["total"], 540.0)

    def test_an_unknown_product_is_refused(self):
        self.assertEqual(client.post("/orders", json={"items": [{"sku": "ghost", "qty": 1}]}).status_code, 422)

    def test_an_order_can_be_read_back(self):
        order_id = client.post("/orders", json={"items": [{"sku": "kettle", "qty": 1}]}).json()["id"]
        self.assertEqual(client.get(f"/orders/{order_id}").json()["total"], 1200.0)
        self.assertEqual(client.get("/orders/99").status_code, 404)


if __name__ == "__main__":
    unittest.main()
