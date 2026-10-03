/**
 * @jest-environment node
 */
import {
  isFatalDecisionsLoad,
  isResolvedDecision,
  isActionableDecision,
  sortDecisionsByImpact,
} from "./decisionsUi";

describe("isFatalDecisionsLoad", () => {
  test("refetch error with cached data is not fatal", () => {
    expect(isFatalDecisionsLoad({
      error: new Error("network"),
      data: { decisions: [], can_act: true },
    })).toBe(false);
  });

  test("error without data is fatal", () => {
    expect(isFatalDecisionsLoad({
      error: new Error("network"),
      data: null,
    })).toBe(true);
  });

  test("missing data is fatal", () => {
    expect(isFatalDecisionsLoad({ error: null, data: null })).toBe(true);
  });
});

describe("isResolvedDecision / isActionableDecision", () => {
  test("pending and delegated stay actionable", () => {
    expect(isActionableDecision({ status: "pending" })).toBe(true);
    expect(isActionableDecision({ status: "delegated", owner: "Bob" })).toBe(true);
    expect(isResolvedDecision({ status: "delegated", owner: "Bob" })).toBe(false);
  });

  test("approved and rejected are resolved", () => {
    expect(isResolvedDecision({ status: "approved" })).toBe(true);
    expect(isResolvedDecision({ status: "rejected" })).toBe(true);
    expect(isActionableDecision({ status: "approved" })).toBe(false);
  });
});

describe("sortDecisionsByImpact", () => {
  test("orders High before Medium before Low, then due", () => {
    const sorted = sortDecisionsByImpact([
      { id: "c", impact: "Low", due: "2026-01-01" },
      { id: "a", impact: "High", due: "2026-06-01" },
      { id: "b", impact: "High", due: "2026-01-01" },
      { id: "d", impact: "Medium", due: "—" },
    ]);
    expect(sorted.map((x) => x.id)).toEqual(["b", "a", "d", "c"]);
  });
});
