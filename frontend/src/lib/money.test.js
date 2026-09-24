import { currencySymbol, formatMoney, normalizeCurrency } from "./money";

describe("money", () => {
  it("formats with the given symbol", () => {
    expect(formatMoney(1234, "₱")).toBe("₱1,234");
    expect(formatMoney(12.5, "$", { decimals: 2 })).toBe("$12.50");
    expect(formatMoney(-50, "€")).toBe("-€50");
  });

  it("compact uses k and M", () => {
    expect(formatMoney(950, "₱", { compact: true })).toBe("₱950");
    expect(formatMoney(1200, "₱", { compact: true })).toBe("₱1.2k");
    expect(formatMoney(34000, "₱", { compact: true })).toBe("₱34k");
    expect(formatMoney(3_400_000, "₱", { compact: true })).toBe("₱3.4M");
  });

  it("maps currency codes to symbols", () => {
    expect(currencySymbol("php")).toBe("₱");
    expect(currencySymbol("PHP")).toBe("₱");
    expect(normalizeCurrency("xyz")).toBe("usd");
  });
});
