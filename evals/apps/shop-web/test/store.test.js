import assert from 'node:assert/strict';
import test from 'node:test';

import { DECLINED_CARD, addToCart, cartLines, cartTotal, checkout, login, money, newState } from '../lib/store.js';

test('prices are shown in dollars and cents', () => {
  assert.equal(money(450), '$4.50');
  assert.equal(money(0), '$0.00');
});

test('only known users with the right password sign in', () => {
  assert.equal(login('alice', 'secret'), true);
  assert.equal(login('alice', 'wrong'), false);
  assert.equal(login('mallory', 'secret'), false);
  assert.equal(login('toString', 'secret'), false);
});

test('a cart adds up its lines and keeps one cart per user', () => {
  const state = newState();
  addToCart(state, 'alice', 'tea', 2);
  addToCart(state, 'alice', 'mug');
  addToCart(state, 'bob', 'tea');
  assert.equal(cartTotal(state, 'alice'), 2 * 450 + 800);
  assert.deepEqual(cartLines(state, 'bob').map((line) => line.sku), ['tea']);
});

test('an unknown product is refused', () => {
  assert.deepEqual(addToCart(newState(), 'alice', 'yacht'), { error: 'unknown' });
});

test('checkout refuses an empty cart and a declined card, and keeps the cart in both cases', () => {
  const state = newState();
  assert.deepEqual(checkout(state, 'alice', '4242'), { error: 'empty' });
  addToCart(state, 'alice', 'tea');
  assert.deepEqual(checkout(state, 'alice', DECLINED_CARD), { error: 'declined' });
  assert.equal(cartTotal(state, 'alice'), 450);
  assert.equal(state.orders.length, 0);
});

test('checkout places an order and empties the cart', () => {
  const state = newState();
  addToCart(state, 'alice', 'mug', 2);
  const result = checkout(state, 'alice', '4242');
  assert.equal(result.order.total, 1600);
  assert.equal(state.orders.length, 1);
  assert.deepEqual(cartLines(state, 'alice'), []);
});
