// Test endpoints, off unless the server was started with SHOP_TEST_ENDPOINTS=1. They let a test sign someone in,
// put records in place and read them back without going through the pages.
import { COOKIE } from '../../../../lib/session';
import { USERS, addToCart, newState, shop } from '../../../../lib/store';

const enabled = () => process.env.SHOP_TEST_ENDPOINTS === '1';
const off = () => Response.json({ error: 'test endpoints are off' }, { status: 404 });

export async function POST(request, { params }) {
  if (!enabled()) {
    return off();
  }
  const { action } = await params;
  const body = await request.json().catch(() => ({}));
  if (action === 'reset') {
    globalThis.__shop = newState();
    return Response.json({ ok: true });
  }
  if (action === 'session') {
    if (!Object.hasOwn(USERS, body.actor)) {
      return Response.json({ error: `no user ${body.actor}` }, { status: 400 });
    }
    return Response.json({ name: COOKIE, value: body.actor });
  }
  if (action === 'seed' && body.entity === 'cart item') {
    for (const row of body.rows ?? []) {
      addToCart(shop(), row.user, row.sku, Number(row.quantity ?? 1));
    }
    return Response.json({ ok: true });
  }
  if (action === 'seed' && body.entity === 'order') {
    const { orders } = shop();
    for (const row of body.rows ?? []) {
      orders.push({ id: orders.length + 1, user: row.user, total: Number(row.total), lines: [] });
    }
    return Response.json({ ok: true });
  }
  return Response.json({ error: `unknown action ${action}` }, { status: 400 });
}

export async function GET(request, { params }) {
  if (!enabled()) {
    return off();
  }
  const { action } = await params;
  const entity = new URL(request.url).searchParams.get('entity');
  if (action === 'records' && entity === 'cart-item') {
    return Response.json(
      Object.entries(shop().carts).flatMap(([user, cart]) => Object.entries(cart).map(([sku, quantity]) => ({ user, sku, quantity }))),
    );
  }
  if (action === 'records' && entity === 'order') {
    return Response.json(shop().orders.map(({ id, user, total }) => ({ id, user, total })));
  }
  return Response.json({ error: `unknown action ${action}` }, { status: 400 });
}
