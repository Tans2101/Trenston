import {
  baselineReady, changeTone, cleanEffect, rippleProjection, runwayChangeLabel, runwayText,
} from "./ripple";

const baseline = { cash: 120000, revenue: 25000, expenses: 40000, start_month: "2026-10" };

describe("decision ripple", () => {
  test("no effect leaves the path unchanged (8 months of runway)", () => {
    const p = rippleProjection(baseline, { amount: 0 });
    expect(p.base.runway.months).toBeCloseTo(8, 5);
    expect(p.after.runway.months).toBeCloseTo(8, 5);
    expect(runwayChangeLabel(p.base.runway, p.after.runway)).toBe("No change to runway");
  });

  test("a monthly cost from month 1 matches the runway guide example", () => {
    // Spending rises 10,000 a month: net burn 25,000, 120,000 / 25,000 = 4.8 months.
    const p = rippleProjection(baseline, { direction: "cost", cadence: "monthly", amount: 10000, start_offset: 1 });
    expect(p.after.runway.months).toBeCloseTo(4.8, 5);
    expect(runwayChangeLabel(p.base.runway, p.after.runway)).toBe("-3.2 mo runway");
    expect(changeTone(p.base.runway, p.after.runway)).toBe("worse");
  });

  test("starting later costs less runway", () => {
    const now = rippleProjection(baseline, { amount: 10000, start_offset: 1 });
    const later = rippleProjection(baseline, { amount: 10000, start_offset: 4 });
    expect(later.after.runway.months).toBeGreaterThan(now.after.runway.months);
    expect(later.startMonth).toBe("2027-02");
  });

  test("income that beats the burn keeps cash growing", () => {
    const p = rippleProjection(baseline, { direction: "income", amount: 20000, start_offset: 1 });
    expect(p.after.runway.status).toBe("cash_growing");
    expect(runwayText(p.after.runway)).toBe("Cash keeps growing");
    expect(changeTone(p.base.runway, p.after.runway)).toBe("better");
  });

  test("a one-off payment only hits one month", () => {
    const p = rippleProjection(baseline, { cadence: "once", amount: 30000, start_offset: 2 });
    expect(p.after.points[1].net - p.base.points[1].net).toBe(-30000);
    expect(p.after.points[2].net).toBe(p.base.points[2].net);
  });

  test("inputs are cleaned and missing data is reported", () => {
    expect(cleanEffect({ amount: "-5", start_offset: 99, direction: "x" })).toEqual({
      direction: "cost", cadence: "monthly", amount: 0, start_offset: 12,
    });
    expect(baselineReady({ revenue: 1, expenses: 1, cash: null }).missing).toEqual(["cash"]);
    expect(baselineReady(null).ok).toBe(false);
  });
});
