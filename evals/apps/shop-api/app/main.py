"""A tiny shop API used to evaluate greenlight. It has no BDD setup and no discounts yet."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="shop-api")

PRODUCTS: dict[str, float] = {"tea": 250.0, "kettle": 1200.0, "mug": 40.0}
ORDERS: dict[int, dict] = {}


class Item(BaseModel):
    sku: str
    qty: int = Field(gt=0)


class OrderIn(BaseModel):
    items: list[Item] = Field(min_length=1)


@app.get("/products")
def list_products() -> list[dict]:
    return [{"sku": sku, "price": price} for sku, price in PRODUCTS.items()]


@app.post("/orders", status_code=201, responses={422: {"description": "an item names an unknown product"}})
def place_order(order: OrderIn) -> dict:
    unknown = [item.sku for item in order.items if item.sku not in PRODUCTS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown product: {', '.join(unknown)}")
    total = sum(PRODUCTS[item.sku] * item.qty for item in order.items)
    order_id = len(ORDERS) + 1
    ORDERS[order_id] = {"id": order_id, "items": [item.model_dump() for item in order.items], "total": total}
    return ORDERS[order_id]


@app.get("/orders/{order_id}", responses={404: {"description": "no such order"}})
def get_order(order_id: int) -> dict:
    if order_id not in ORDERS:
        raise HTTPException(status_code=404, detail="no such order")
    return ORDERS[order_id]


def reset() -> None:
    """Forget every order (used by tests between scenarios)."""
    ORDERS.clear()
