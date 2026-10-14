import { revenueSummary } from "@/components/RevenueBars";

describe("revenueSummary", () => {
  it("describes the latest month against the one before", () => {
    const text = revenueSummary(
      [{ month: "Aug", current: 200, last: 180 }, { month: "Sep", current: 220, last: 200 }],
      "$",
    );
    expect(text).toContain("Aug to Sep");
    expect(text).toContain("up 10 percent");
  });
  it("handles no data", () => {
    expect(revenueSummary([], "$")).toMatch(/no data/);
  });
});
