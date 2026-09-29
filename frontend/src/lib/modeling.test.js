/**
 * Parity: the browser model must produce the same numbers as the Python
 * reference (backend/modeling.py) for every case in shared/modeling-parity.json.
 */
const fs = require("fs");
const path = require("path");
const { projectCash, sanitizeInputs, addMonths, baselineInputs } = require("./modeling");

const fixture = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "..", "..", "shared", "modeling-parity.json"), "utf8"),
);

function close(a, b) {
  if (a === null || b === null) return a === b;
  if (typeof a === "number" && typeof b === "number") {
    return Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
  }
  return a === b;
}

function expectSame(actual, expected, where) {
  if (Array.isArray(expected)) {
    expect(Array.isArray(actual)).toBe(true);
    expect(actual.length).toBe(expected.length);
    expected.forEach((e, i) => expectSame(actual[i], e, `${where}[${i}]`));
    return;
  }
  if (expected && typeof expected === "object") {
    expect(Object.keys(actual).sort()).toEqual(Object.keys(expected).sort());
    Object.keys(expected).forEach((k) => expectSame(actual[k], expected[k], `${where}.${k}`));
    return;
  }
  if (!close(actual, expected)) {
    throw new Error(`${where}: JS ${actual} !== Python ${expected}`);
  }
}

describe("modeling parity with backend/modeling.py", () => {
  it("has cases", () => {
    expect(fixture.cases.length).toBeGreaterThan(5);
  });
  it.each(fixture.cases.map((c) => [c.name, c]))("%s", (_name, c) => {
    expectSame(sanitizeInputs(c.inputs), c.sanitized, "sanitized");
    expectSame(projectCash(c.inputs, c.baseline), c.expected, "result");
  });
});

describe("modeling helpers", () => {
  it("adds months across year boundaries", () => {
    expect(addMonths("2026-11", 3)).toBe("2027-02");
    expect(addMonths("2026-01", 0)).toBe("2026-01");
    expect(addMonths("bad", 1)).toBe("");
    expect(addMonths("2026-13", 1)).toBe("");
  });
  it("baseline keeps reserve and horizon but drops drivers", () => {
    const b = baselineInputs({ revenue_growth_pct: 9, hires: [{ monthly_cost: 1 }], horizon: 36, min_cash_reserve: 5 });
    expect(b).toEqual({ revenue_growth_pct: 0, expense_growth_pct: 0, hires: [], events: [], min_cash_reserve: 5, horizon: 36 });
  });
  it("projects 36 months fast enough for live sliders", () => {
    const inputs = { horizon: 36, revenue_growth_pct: 5, hires: Array.from({ length: 20 }, (_, i) => ({ monthly_cost: 1000, start_month: i + 1 })), events: Array.from({ length: 20 }, (_, i) => ({ amount: -500, month: i + 1 })) };
    const base = { cash: 1e6, revenue: 20000, expenses: 30000, start_month: "2026-09" };
    const t0 = Date.now();
    for (let i = 0; i < 1000; i += 1) projectCash(inputs, base);
    expect(Date.now() - t0).toBeLessThan(500);
  });
});
