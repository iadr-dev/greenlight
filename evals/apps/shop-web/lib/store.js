// The shop's state and rules, in memory. Pure functions over a plain object, so the unit tests need no server.
export const PRODUCTS = [
  { sku: 'tea', name: 'Tea', cents: 450 },
  { sku: 'mug', name: 'Mug', cents: 800 },
];

export const USERS = { alice: 'secret', bob: 'secret' };
export const DECLINED_CARD = '4000000000000002';

export const MESSAGES = {
  empty: 'Your cart is empty',
  declined: 'Your card was declined',
  unknown: 'That product does not exist',
  credentials: 'Wrong name or password',
};

export function newState() {
  return { carts: {}, orders: [] };
}

// One state per server process, shared by the pages and the route handlers.
export function shop() {
  globalThis.__shop ??= newState();
  return globalThis.__shop;
}

export function money(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}

export function product(sku) {
  return PRODUCTS.find((p) => p.sku === sku);
}

export function login(name, password) {
  return Object.hasOwn(USERS, name) && USERS[name] === password;
}

export function addToCart(state, user, sku, quantity = 1) {
  if (!product(sku)) {
    return { error: 'unknown' };
  }
  const cart = (state.carts[user] ??= {});
  cart[sku] = (cart[sku] ?? 0) + quantity;
  return { ok: true };
}

export function cartLines(state, user) {
  return Object.entries(state.carts[user] ?? {}).map(([sku, quantity]) => {
    const item = product(sku);
    return { sku, name: item.name, quantity, cents: item.cents * quantity };
  });
}

export function cartTotal(state, user) {
  return cartLines(state, user).reduce((sum, line) => sum + line.cents, 0);
}

export function checkout(state, user, card) {
  const lines = cartLines(state, user);
  if (lines.length === 0) {
    return { error: 'empty' };
  }
  if (card === DECLINED_CARD) {
    return { error: 'declined' };
  }
  const order = { id: state.orders.length + 1, user, total: cartTotal(state, user), lines };
  state.orders.push(order);
  delete state.carts[user];
  return { ok: true, order };
}
