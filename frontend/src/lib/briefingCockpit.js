/**
 * Pure helpers for Briefing cockpit empty / loading states.
 * Kept separate so P1 behavior is unit-testable without mounting React.
 */

const FINANCE_MATCHERS = [
  { id: "mrr", match: /mrr|revenue/i },
  { id: "burn", match: /^burn/i },
  { id: "runway", match: /runway/i },
];

/** True when every Revenue/Burn/Runway tile is missing (or absent). */
export function allFinanceKpisMissing(metrics = []) {
  return FINANCE_MATCHERS.every((def) => {
    const match = (metrics || []).find((m) => def.match.test(m.label || ""));
    return match?.missing ?? !match;
  });
}

/**
 * Show the "Add your numbers" Get started CTA only when the viewer can use
 * Financials and every finance KPI is still missing (and parent is not
 * already showing the Ready-when-you-are prompt).
 */
export function shouldShowFinanceEmptyCta({
  canFin,
  metrics = [],
  suppressFinanceEmpty = false,
}) {
  if (!canFin || suppressFinanceEmpty) return false;
  return allFinanceKpisMissing(metrics);
}

/** Chart / spend panel body when nested /financials fetch is involved. */
export function financialsPanelState({ canFin, loading, error, hasRows }) {
  if (!canFin) return "no_access";
  if (loading) return "loading";
  if (error) return "error";
  if (!hasRows) return "empty";
  return "ready";
}

/** Fatal page error only when there is no cached payload. */
export function isFatalBriefingLoad({ briefingError, companyError, data, company }) {
  return Boolean((briefingError && !data) || (companyError && !company) || !data || !company);
}
