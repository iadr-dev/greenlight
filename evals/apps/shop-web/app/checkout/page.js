import { requireUser } from '../../lib/session';
import { MESSAGES } from '../../lib/store';

export const dynamic = 'force-dynamic';

export default async function Checkout({ searchParams }) {
  await requireUser();
  const { error } = await searchParams;
  return (
    <main>
      <h1>Checkout</h1>
      {error && MESSAGES[error] ? (
        <p role="alert" data-testid="checkout-error">
          {MESSAGES[error]}
        </p>
      ) : null}
      <form method="post" action="/api/checkout">
        <label>
          Card number <input name="card" />
        </label>
        <button type="submit">Place order</button>
      </form>
    </main>
  );
}
