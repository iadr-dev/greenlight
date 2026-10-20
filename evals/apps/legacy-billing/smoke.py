"""Starts the app and makes two requests. This is a check that the app runs, not a test suite: the app has no tests on
purpose, so that an adoption has something to describe."""
from __future__ import annotations

import sys

from billing.app import create_app


def main() -> int:
    client = create_app().test_client()
    created = client.post("/invoices", json={"quantity": 2, "unit_price_cents": 1000, "tax_percent": 10})
    fee = client.get("/late-fee", query_string={"balance_cents": 10000, "days_overdue": 20})
    if created.status_code != 201 or created.get_json() != {"subtotal": 2000, "tax": 200, "total": 2200}:
        print("invoice request failed:", created.status_code, created.get_json())
        return 1
    if fee.status_code != 200 or fee.get_json() != {"fee": 200}:
        print("late fee request failed:", fee.status_code, fee.get_json())
        return 1
    print("legacy-billing runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
