/** Workspace money formatting. Symbols mirror backend money_fmt.CURRENCY_SYMBOLS. */

export const CURRENCY_SYMBOLS = {
  usd: "$",
  php: "₱",
  eur: "€",
  gbp: "£",
  sgd: "S$",
  inr: "₹",
};

/** Backend default for legacy workspaces that never stored a currency. */
export const LEGACY_DEFAULT_CURRENCY = "usd";

export function normalizeCurrency(code) {
  const c = String(code || "").trim().toLowerCase();
  return CURRENCY_SYMBOLS[c] ? c : LEGACY_DEFAULT_CURRENCY;
}

export function currencySymbol(code) {
  return CURRENCY_SYMBOLS[normalizeCurrency(code)];
}

/**
 * Format a money value with an explicit symbol.
 * compact → 950, 1.2k, 34k, 3.4M (one decimal below 10k / 10M).
 */
export function formatMoney(value, symbol, { compact = false, decimals = 0 } = {}) {
  const sym = symbol ?? "";
  const v = Number(value);
  if (!Number.isFinite(v)) return `${sym}0`;
  const sign = v < 0 ? "-" : "";
  const abs = Math.abs(v);
  if (compact) {
    if (abs >= 1_000_000) {
      const n = abs / 1_000_000;
      return `${sign}${sym}${(n >= 10 ? n.toFixed(0) : n.toFixed(1)).replace(/\.0$/, "")}M`;
    }
    if (abs >= 1000) {
      const n = abs / 1000;
      return `${sign}${sym}${(n >= 10 ? n.toFixed(0) : n.toFixed(1)).replace(/\.0$/, "")}k`;
    }
  }
  const text = abs.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${sign}${sym}${text}`;
}
