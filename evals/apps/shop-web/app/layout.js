export const metadata = { title: 'Shop' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <nav>
          <a href="/">Shop</a> <a href="/cart">Cart</a> <a href="/orders">Orders</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
