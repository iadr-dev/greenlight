// Logical names -> the shop-web application's pages and components.
export type Target =
  | { role: Parameters<import('@playwright/test').Page['getByRole']>[0]; name?: string }
  | { label: string }
  | { text: string }
  | { testId: string };

export const PAGES: Record<string, string> = {
  catalogue: '/',
  login: '/login',
  cart: '/cart',
  checkout: '/checkout',
  orders: '/orders',
};

export const TARGETS: Record<string, Target> = {
  'page heading': { role: 'heading' },
  'cart total': { testId: 'cart-total' },
  'empty cart message': { testId: 'cart-empty' },
  'checkout error': { testId: 'checkout-error' },
  'login error': { testId: 'login-error' },
  'card number': { label: 'Card number' },
  'place order button': { role: 'button', name: 'Place order' },
  'name field': { label: 'Name' },
  'password field': { label: 'Password' },
  'sign in button': { role: 'button', name: 'Sign in' },
  'add tea button': { role: 'button', name: 'Add Tea to cart' },
  'first order': { testId: 'order-1' },
};

export interface Endpoint {
  method: string;
  url: RegExp;
}

export const DEPENDENCIES: Record<string, Record<string, Endpoint>> = {};
