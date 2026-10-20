export type Currency = "USD" | "EUR" | "JPY";

/** Digits after the decimal point for each currency. */
export const MINOR_DIGITS: Record<Currency, number> = { USD: 2, EUR: 2, JPY: 0 };

/** An amount in the smallest unit of its currency (cents for USD, yen for JPY). */
export interface Money {
  readonly minor: number;
  readonly currency: Currency;
}

export class MoneyError extends Error {}

const DECIMAL = /^-?\d+(\.\d+)?$/;

export function isCurrency(code: string): code is Currency {
  return Object.prototype.hasOwnProperty.call(MINOR_DIGITS, code);
}

/** Read "12.50" as 1250 minor units of the currency; more digits than the currency has is an error. */
export function parse(text: string, currency: Currency): Money {
  if (!DECIMAL.test(text)) {
    throw new MoneyError(`not an amount: ${text}`);
  }
  const digits = MINOR_DIGITS[currency];
  const [whole, fraction = ""] = text.split(".");
  if (fraction.length > digits) {
    throw new MoneyError(`${currency} has ${digits} decimal digits: ${text}`);
  }
  const negative = whole.startsWith("-");
  const magnitude = Number(whole.replace("-", "") + fraction.padEnd(digits, "0"));
  return { minor: negative ? -magnitude : magnitude, currency };
}

export function add(a: Money, b: Money): Money {
  if (a.currency !== b.currency) {
    throw new MoneyError(`cannot add ${a.currency} to ${b.currency}`);
  }
  return { minor: a.minor + b.minor, currency: a.currency };
}

/** Show an amount with the decimal digits of its currency: 1250 USD is "12.50 USD". */
export function format(amount: Money): string {
  const digits = MINOR_DIGITS[amount.currency];
  const sign = amount.minor < 0 ? "-" : "";
  const text = String(Math.abs(amount.minor)).padStart(digits + 1, "0");
  const whole = text.slice(0, text.length - digits);
  const fraction = digits === 0 ? "" : `.${text.slice(text.length - digits)}`;
  return `${sign}${whole}${fraction} ${amount.currency}`;
}
