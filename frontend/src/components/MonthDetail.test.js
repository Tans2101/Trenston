import { lineNote, monthTitle, shiftMonth } from "./MonthDetail";

describe("MonthDetail helpers", () => {
  test("monthTitle names the month and year", () => {
    expect(monthTitle("2026-07")).toBe("July 2026");
    expect(monthTitle("")).toBe("");
  });
  test("shiftMonth crosses year edges", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
  });
  test("lineNote says how a line got into the month", () => {
    expect(lineNote({ recurring: false })).toBe("One-time");
    expect(lineNote({ recurring: true, cadence: "monthly", month: "2026-07" })).toBe("Every month since Jul 2026");
    expect(lineNote({ recurring: true, cadence: "annual", month: "2026-07" })).toMatch(/Annual plan from Jul 2026/);
  });
});
