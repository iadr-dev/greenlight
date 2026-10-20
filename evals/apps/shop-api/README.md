# shop-api

A tiny FastAPI shop (products and orders, no discounts) used to evaluate greenlight end to end. It has no BDD
setup on purpose: the evaluation adds it.

```sh
python -m pip install fastapi httpx
python -m unittest discover -s unit -t .
```

Feature requests to try on it are in `evals/requests/`.
