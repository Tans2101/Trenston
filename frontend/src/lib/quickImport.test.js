import {
  applyLineTypes, buildConfirmPayload, countsSentence, initialChoices, monthName,
  recordsLabel, sheetRecords, totalSelected,
} from "./quickImport";

const pnl = {
  index: 0,
  name: "P&L",
  kind: "financial_wide",
  confidence: "high",
  line_types: [
    { label: "Product sales", type: "revenue" },
    { label: "Rent", type: "expense" },
    { label: "Misc", type: "expense" },
  ],
  records: [
    { type: "revenue", amount: 100, month: "2026-01", name: "Product sales", source_row: 4 },
    { type: "expense", amount: 5, month: "2026-01", name: "Product sales", source_row: 4 }, // refund
    { type: "expense", amount: 30, month: "2026-01", name: "Rent", source_row: 5 },
    { type: "expense", amount: 7, month: "2026-01", name: "Misc", source_row: 6 },
  ],
};
const deals = {
  index: 1, name: "Clients", kind: "deals", confidence: "low",
  records: [{ name: "Jollibee", value: 10, stage: "lead", source_row: 2 }],
};
const lookup = { index: 2, name: "Lists", kind: "skip", records: [] };
const preview = { filename: "acme.xlsx", sheets: [pnl, deals, lookup] };

describe("quick import helpers", () => {
  test("low-confidence and empty sheets start unticked", () => {
    const c = initialChoices(preview);
    expect(c[0].include).toBe(true);
    expect(c[1].include).toBe(false);
    expect(c[2].include).toBe(false);
  });

  test("switching a P&L line flips its rows, leaving it out drops them", () => {
    const original = { "Product sales": "revenue", Rent: "expense", Misc: "expense" };
    const out = applyLineTypes(pnl.records, original, { "Product sales": "expense", Misc: "skip" });
    expect(out.map((r) => [r.name, r.type])).toEqual([
      ["Product sales", "expense"],
      ["Product sales", "revenue"], // the refund flips the other way, so it stays consistent
      ["Rent", "expense"],
    ]);
  });

  test("confirm payload only carries ticked sheets and drops row numbers", () => {
    const c = initialChoices(preview);
    c[0].lineTypes = { Misc: "skip" };
    const body = buildConfirmPayload(preview, c);
    expect(body.filename).toBe("acme.xlsx");
    expect(body.sheets).toHaveLength(1);
    expect(body.sheets[0].records).toHaveLength(3);
    expect(body.sheets[0].records[0].source_row).toBeUndefined();
    expect(totalSelected(preview, c)).toBe(3);
    expect(sheetRecords(deals, { include: false })).toEqual([]);
  });

  test("labels read naturally", () => {
    expect(recordsLabel("deals", 1)).toBe("1 deal");
    expect(recordsLabel("financial_wide", 48)).toBe("48 money entries");
    expect(monthName("2026-03")).toBe("Mar 2026");
    expect(countsSentence({ financial: 12, deal: 3, task: 0, work_order: 1 })).toBe(
      "12 money entries, 3 deals and 1 production order",
    );
    expect(countsSentence({ deal: 1 })).toBe("1 deal");
  });
});
