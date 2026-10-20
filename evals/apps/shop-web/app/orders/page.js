import { requireUser } from '../../lib/session';
import { money, shop } from '../../lib/store';

export const dynamic = 'force-dynamic';

export default async function Orders() {
  const user = await requireUser();
  const orders = shop().orders.filter((order) => order.user === user);
  return (
    <main>
      <h1>Orders</h1>
      {orders.length === 0 ? (
        <p data-testid="orders-empty">No orders yet</p>
      ) : (
        <ul>
          {orders.map((order) => (
            <li key={order.id} data-testid={`order-${order.id}`}>
              Order {order.id}: {money(order.total)}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
