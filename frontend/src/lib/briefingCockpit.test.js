/**
 * @jest-environment node
 */
import {
  allFinanceKpisMissing,
  financialsPanelState,
  isFatalBriefingLoad,
  shouldShowFinanceEmptyCta,
} from "./briefingCockpit";

describe("shouldShowFinanceEmptyCta", () => {
  const missing = [
    { label: "MRR", missing: true },
    { label: "Burn", missing: true },
    { label: "Runway", missing: true },
  ];

  test("hides CTA when viewer lacks Financials access", () => {
    expect(shouldShowFinanceEmptyCta({ canFin: false, metrics: missing })).toBe(false);
  });

  test("shows CTA when canFin and all finance KPIs missing", () => {
    expect(shouldShowFinanceEmptyCta({ canFin: true, metrics: missing })).toBe(true);
  });

  test("hides CTA when parent suppressFinanceEmpty is set", () => {
    expect(shouldShowFinanceEmptyCta({
      canFin: true,
      metrics: missing,
      suppressFinanceEmpty: true,
    })).toBe(false);
  });

  test("hides CTA when any finance KPI has data", () => {
    expect(shouldShowFinanceEmptyCta({
      canFin: true,
      metrics: [
        { label: "MRR", missing: false, value: "$10k" },
        { label: "Burn", missing: true },
        { label: "Runway", missing: true },
      ],
    })).toBe(false);
  });

  test("synthesizes missing when finance metrics omitted from payload", () => {
    expect(allFinanceKpisMissing([])).toBe(true);
    expect(shouldShowFinanceEmptyCta({ canFin: true, metrics: [] })).toBe(true);
    expect(shouldShowFinanceEmptyCta({ canFin: false, metrics: [] })).toBe(false);
  });
});

describe("financialsPanelState", () => {
  test("no_access when !canFin", () => {
    expect(financialsPanelState({ canFin: false, loading: true, error: null, hasRows: false })).toBe("no_access");
  });

  test("loading before empty", () => {
    expect(financialsPanelState({ canFin: true, loading: true, error: null, hasRows: false })).toBe("loading");
  });

  test("error distinct from empty", () => {
    expect(financialsPanelState({ canFin: true, loading: false, error: new Error("x"), hasRows: false })).toBe("error");
  });

  test("empty only when settled with no rows", () => {
    expect(financialsPanelState({ canFin: true, loading: false, error: null, hasRows: false })).toBe("empty");
  });

  test("ready when rows present", () => {
    expect(financialsPanelState({ canFin: true, loading: false, error: null, hasRows: true })).toBe("ready");
  });
});

describe("isFatalBriefingLoad", () => {
  test("refetch error with cached data is not fatal", () => {
    expect(isFatalBriefingLoad({
      briefingError: new Error("network"),
      companyError: null,
      data: { headline: "ok" },
      company: { name: "Acme" },
    })).toBe(false);
  });

  test("error without data is fatal", () => {
    expect(isFatalBriefingLoad({
      briefingError: new Error("network"),
      companyError: null,
      data: null,
      company: { name: "Acme" },
    })).toBe(true);
  });

  test("missing company is fatal", () => {
    expect(isFatalBriefingLoad({
      briefingError: null,
      companyError: null,
      data: { headline: "ok" },
      company: null,
    })).toBe(true);
  });
});
