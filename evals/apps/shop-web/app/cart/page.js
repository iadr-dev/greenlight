import { requireUser } from '../../lib/session';
import { cartLines, cartTotal, money, shop } from '../../lib/store';

export const dynamic = 'force-dynamic';

export default async function Cart() {
  const user = await requireUser();
  const lines = cartLines(shop(), user);
  return (
    <main>
      <h1>Your cart</h1>
      {lines.length === 0 ? (
        <p data-testid="cart-empty">Your cart is empty</p>
      ) : (
        <>
          <table>
            <tbody>
              {lines.map((line) => (
                <tr key={line.sku} data-testid={`line-${line.sku}`}>
                  <td>{line.name}</td>
                  <td>{line.quantity}</td>
                  <td>{money(line.cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Total <strong data-testid="cart-total">{money(cartTotal(shop(), user))}</strong>
          </p>
          <a href="/checkout">Check out</a>
        </>
      )}
    </main>
  );
}
