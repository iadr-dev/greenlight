# shop-web

A tiny Next.js shop used to evaluate greenlight on a web front end: a catalogue, a cart, sign-in and checkout. It has no
BDD setup on purpose; the evaluation adds it (`bdd init --adapter ts-playwright-bdd`).

```sh
npm ci
npm test            # the shop's rules, without a server
npm run build
npm start           # http://localhost:3000
```

| Page | What it does |
|---|---|
| `/` | two products, each with an "Add ... to cart" button |
| `/login` | name and password (`alice` or `bob`, password `secret`); a wrong pair shows an alert |
| `/cart` | the signed-in user's lines and total; a visitor is sent to `/login` |
| `/checkout` | card number and "Place order"; an empty cart or the card `4000000000000002` shows an alert |
| `/orders` | the signed-in user's orders |

Everything is in memory and deterministic, and nothing calls the network.

## Test endpoints

Start the server with `SHOP_TEST_ENDPOINTS=1` and a test can use, without going through the pages:

| Request | Does |
|---|---|
| `POST /api/test/session` `{"actor": "alice"}` | returns the cookie that signs `alice` in |
| `POST /api/test/seed` `{"entity": "cart item" \| "order", "rows": [...]}` | puts records in place (`user`, `sku`, `quantity` / `user`, `total`) |
| `GET /api/test/records?entity=order` (or `cart-item`) | reads them back |
| `POST /api/test/reset` | forgets everything |

Without the variable these answer 404. Feature requests to try on the app are in `evals/requests/`
(`minimum-order`, `login-return`), with the answers a person would give in `evals/answers/`.
