import { PRODUCTS, money } from '../lib/store';

export const dynamic = 'force-dynamic';

export default function Catalogue() {
  return (
    <main>
      <h1>Shop</h1>
      <ul>
        {PRODUCTS.map((item) => (
          <li key={item.sku} data-testid={`product-${item.sku}`}>
            {item.name} {money(item.cents)}
            <form method="post" action="/api/cart">
              <input type="hidden" name="sku" value={item.sku} />
              <button type="submit">Add {item.name} to cart</button>
            </form>
          </li>
        ))}
      </ul>
    </main>
  );
}
