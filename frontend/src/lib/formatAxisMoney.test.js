import { formatAxisMoney } from "./formatAxisMoney";

describe("formatAxisMoney", () => {
  it("formats zero without a k suffix", () => {
    expect(formatAxisMoney(0, { symbol: "$" })).toBe("$0");
  });

  it("keeps sub-thousand ticks as dollars (fixes $0k bug)", () => {
    expect(formatAxisMoney(0, { symbol: "$" })).toBe("$0");
    expect(formatAxisMoney(10, { symbol: "$" })).toBe("$10");
    expect(formatAxisMoney(20, { symbol: "$" })).toBe("$20");
    expect(formatAxisMoney(40, { symbol: "$" })).toBe("$40");
    expect(formatAxisMoney(41, { symbol: "$" })).toBe("$41");
    expect(formatAxisMoney(500, { symbol: "$" })).toBe("$500");
    expect(formatAxisMoney(999, { symbol: "$" })).toBe("$999");
  });

  it("uses k for thousands", () => {
    expect(formatAxisMoney(1000, { symbol: "$" })).toBe("$1k");
    expect(formatAxisMoney(1500, { symbol: "$" })).toBe("$1.5k");
    expect(formatAxisMoney(20000, { symbol: "$" })).toBe("$20k");
    expect(formatAxisMoney(41000, { symbol: "$" })).toBe("$41k");
  });

  it("uses M for millions", () => {
    expect(formatAxisMoney(1_000_000, { symbol: "$" })).toBe("$1M");
    expect(formatAxisMoney(2_500_000, { symbol: "$" })).toBe("$2.5M");
    expect(formatAxisMoney(12_000_000, { symbol: "$" })).toBe("$12M");
  });

  it("preserves sign and custom symbol", () => {
    expect(formatAxisMoney(-40, { symbol: "$" })).toBe("-$40");
    expect(formatAxisMoney(2000, { symbol: "₱" })).toBe("₱2k");
  });

  it("returns empty for non-finite input", () => {
    expect(formatAxisMoney(NaN, { symbol: "$" })).toBe("");
    expect(formatAxisMoney(Infinity, { symbol: "$" })).toBe("");
  });
});
