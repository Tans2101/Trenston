/**
 * Pure helpers for the Decisions page — soft-refresh, open vs resolved,
 * and impact ranking. Kept out of the React page so behavior is unit-testable.
 */

const IMPACT_RANK = { High: 0, Medium: 1, Low: 2 };

/** Fatal page error only when there is no cached payload. */
export function isFatalDecisionsLoad({ error, data }) {
  return Boolean((error && !data) || !data);
}

/**
 * Terminal outcomes only. "delegated" is ownership hand-off, not resolution —
 * Decision Center must keep those actionable (My Day uses isOpenDecision for
 * "needs *my* call" and correctly hides delegated-to-others).
 */
export function isResolvedDecision(d) {
  if (!d) return false;
  const s = (d.status || "").toLowerCase();
  return s === "approved" || s === "rejected";
}

export function isActionableDecision(d) {
  return Boolean(d) && !isResolvedDecision(d);
}

/** Match Briefing / backend _IMPACT_RANK: High → Medium → Low, then due, then id. */
export function sortDecisionsByImpact(list) {
  return [...(list || [])].sort((a, b) => {
    const ia = IMPACT_RANK[a?.impact] ?? 9;
    const ib = IMPACT_RANK[b?.impact] ?? 9;
    if (ia !== ib) return ia - ib;
    const da = a?.due && a.due !== "—" ? a.due : "9999";
    const db = b?.due && b.due !== "—" ? b.due : "9999";
    if (da !== db) return da < db ? -1 : 1;
    return String(a?.id || "").localeCompare(String(b?.id || ""));
  });
}
