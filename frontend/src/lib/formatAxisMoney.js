/**
 * Compact currency labels for chart axes.
 * Avoids the "$0k" trap: values under $1000 stay as dollars, not rounded /1000.
 *
 * @param {number} value
 * @param {{ symbol?: string }} [opts]
 * @returns {string}
 */
export function formatAxisMoney(value, { symbol = "$" } = {}) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "";

  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";

  if (abs === 0) return `${symbol}0`;

  if (abs >= 1_000_000) {
    const n = abs / 1_000_000;
    const text = (n >= 10 ? n.toFixed(0) : n.toFixed(1)).replace(/\.0$/, "");
    return `${sign}${symbol}${text}M`;
  }

  if (abs >= 1000) {
    const n = abs / 1000;
    // Prefer whole k when the tick is already a clean thousand
    const text =
      abs % 1000 === 0 || n >= 10
        ? String(Math.round(n))
        : n.toFixed(1).replace(/\.0$/, "");
    return `${sign}${symbol}${text}k`;
  }

  // Sub-$1k range: show real intermediate ticks ($0, $20, $40), never "$0k"
  if (abs >= 1) return `${sign}${symbol}${Math.round(abs)}`;
  return `${sign}${symbol}${abs.toFixed(2)}`;
}
