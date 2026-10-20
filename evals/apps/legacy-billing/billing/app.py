"""The HTTP face of the billing code. Both routes only calculate: nothing is stored, so both are reads."""
from __future__ import annotations

import os
import secrets

from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFProtect

from . import fees, pricing


def create_app() -> Flask:
    app = Flask(__name__)
    # The key comes from the environment; without one a random key lives as long as the process (the app keeps no sessions).
    app.config["SECRET_KEY"] = os.environ.get("BILLING_SECRET_KEY") or secrets.token_hex(32)
    CSRFProtect(app)                                                  # any state-changing route added later is covered

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
