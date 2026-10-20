"""The HTTP face of the billing code. Both routes only calculate: nothing is stored, so both are reads."""
from __future__ import annotations

from flask import Flask, jsonify, request

from . import fees, pricing


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/invoice")
    def quote_invoice():
        try:
            args = request.args
            body = pricing.invoice(int(args["quantity"]), int(args["unit_price_cents"]), int(args.get("tax_percent", 0)))
        except (KeyError, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(body)

    @app.get("/late-fee")
    def late_fee():
        try:
            fee = fees.late_fee(int(request.args["balance_cents"]), int(request.args["days_overdue"]))
        except (KeyError, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"fee": fee})

    return app
