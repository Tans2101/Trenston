import { formatAxisMoney } from "./formatAxisMoney";

describe("formatAxisMoney", () => {
  it("formats zero without a k suffix", () => {
    expect(formatAxisMoney(0)).toBe("$0");
  });

  it("keeps sub-thousand ticks as dollars (fixes $0k bug)", () => {
    expect(formatAxisMoney(0)).toBe("$0");
    expect(formatAxisMoney(10)).toBe("$10");
    expect(formatAxisMoney(20)).toBe("$20");
    expect(formatAxisMoney(40)).toBe("$40");
    expect(formatAxisMoney(41)).toBe("$41");
    expect(formatAxisMoney(500)).toBe("$500");
    expect(formatAxisMoney(999)).toBe("$999");
  });

  it("uses k for thousands", () => {
    expect(formatAxisMoney(1000)).toBe("$1k");
    expect(formatAxisMoney(1500)).toBe("$1.5k");
    expect(formatAxisMoney(20000)).toBe("$20k");
    expect(formatAxisMoney(41000)).toBe("$41k");
  });

  it("uses M for millions", () => {
    expect(formatAxisMoney(1_000_000)).toBe("$1M");
    expect(formatAxisMoney(2_500_000)).toBe("$2.5M");
    expect(formatAxisMoney(12_000_000)).toBe("$12M");
  });

  it("preserves sign and custom symbol", () => {
    expect(formatAxisMoney(-40)).toBe("-$40");
    expect(formatAxisMoney(2000, { symbol: "₱" })).toBe("₱2k");
  });

  it("returns empty for non-finite input", () => {
    expect(formatAxisMoney(NaN)).toBe("");
    expect(formatAxisMoney(Infinity)).toBe("");
  });
});
