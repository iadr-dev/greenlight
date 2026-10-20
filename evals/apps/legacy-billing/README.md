# legacy-billing

A small Flask billing service with **no tests, on purpose**. It is the reference app for `/greenlight:adopt`: the
evaluation asks greenlight to describe what the code does today, lock that description and leave the code alone.

```sh
uv pip install --require-hashes -r requirements.txt
python smoke.py        # starts the app and makes two requests
```

What it does: `billing/pricing.py` prices a one-line invoice (volume discount, tax rounded half up), `billing/fees.py`
computes late fees, `billing/app.py` exposes both over HTTP. Money is whole cents.

Two behaviours look wrong and are left as they are, because adoption describes and never fixes. An evaluation
checks that they are reported as questions, not turned into rules that endorse them silently, and never "fixed":

- the volume discount applies from the **eleventh** unit although its docstring says ten;
- a balance more than 90 days overdue pays **no** fee, after a growing fee up to day 90.

The scripted answers for the evaluation are in `evals/requests/adopt-billing.answers.txt`.
