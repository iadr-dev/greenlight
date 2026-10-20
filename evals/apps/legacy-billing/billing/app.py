"""The HTTP face of the billing code."""
from __future__ import annotations

from flask import Flask, jsonify, request

from . import fees, pricing


def create_app() -> Flask:
    app = Flask(__name__)

    @app.post("/invoices")
    def create_invoice():
        data = request.get_json(silent=True) or {}
        try:
            body = pricing.invoice(int(data["quantity"]), int(data["unit_price_cents"]), int(data.get("tax_percent", 0)))
        except (KeyError, TypeError, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(body), 201

    @app.get("/late-fee")
    def late_fee():
        try:
            fee = fees.late_fee(int(request.args["balance_cents"]), int(request.args["days_overdue"]))
        except (KeyError, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"fee": fee})

    return app
