import assert from "node:assert/strict";
import { test } from "node:test";

import { add, format, MoneyError, parse } from "../src/money.js";

test("an amount is read in minor units", () => {
  assert.deepEqual(parse("12.50", "USD"), { minor: 1250, currency: "USD" });
  assert.deepEqual(parse("-0.05", "EUR"), { minor: -5, currency: "EUR" });
  assert.deepEqual(parse("300", "JPY"), { minor: 300, currency: "JPY" });
});

test("more decimal digits than the currency has is refused", () => {
  assert.throws(() => parse("1.005", "USD"), MoneyError);
  assert.throws(() => parse("1.5", "JPY"), MoneyError);
  assert.throws(() => parse("twelve", "USD"), MoneyError);
});

test("amounts of one currency are added, mixed currencies are refused", () => {
  assert.equal(add(parse("1.10", "USD"), parse("2.25", "USD")).minor, 335);
  assert.throws(() => add(parse("1", "USD"), parse("1", "EUR")), MoneyError);
});

test("an amount is shown with the digits of its currency", () => {
  assert.equal(format(parse("12.50", "USD")), "12.50 USD");
  assert.equal(format(parse("0.05", "EUR")), "0.05 EUR");
  assert.equal(format(parse("-300", "JPY")), "-300 JPY");
});
