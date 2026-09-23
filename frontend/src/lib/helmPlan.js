/** User-facing plan labels and entitlement helpers. */

const PAID = new Set(["starter", "growth", "business", "pro"]);
const BLOCKED_SUB_STATUS = new Set(["past_due", "paused", "canceled", "cancelled"]);

export function normalizePlan(plan) {
  if (!plan) return "free";
  const p = String(plan).toLowerCase();
  // Legacy "pro" maps to Starter on the backend (see plans.py / README.md)
  if (p === "pro") return "starter";
  return p;
}

export function helmPlanLabel(plan, isPro, billingEnforced = true) {
  if (!billingEnforced) return "Active";
  const id = normalizePlan(plan);
  if (id === "free") return "Free";
  if (id === "starter") return "Starter";
  if (id === "growth") return "Growth";
  if (id === "business" || isPro) return "Business";
  return "Free";
}

export function helmWorkspacePlanLabel(plan, billingEnforced = true) {
  return helmPlanLabel(plan, PAID.has(normalizePlan(plan)), billingEnforced);
}

/** Cockpit access — Free and all paid tiers can enter the app. */
export function helmHasFullAccess(plan, billingEnforced = true) {
  if (!billingEnforced) return true;
  return true; // Free tier is a real plan; feature gates handle upgrades
}

/**
 * True when the workspace should show paid-tier UI.
 * Aligns with backend workspace_allows / workspace_is_pro: past_due and similar
 * statuses block paid entitlements even when plan id is still Starter+.
 */
export function helmIsPaidPlan(plan, billingEnforced = true, subscriptionStatus = null) {
  if (!billingEnforced) return true;
  if (!PAID.has(normalizePlan(plan))) return false;
  const status = String(subscriptionStatus || "").toLowerCase();
  if (status && BLOCKED_SUB_STATUS.has(status)) return false;
  return true;
}
