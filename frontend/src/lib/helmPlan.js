/** User-facing plan labels and entitlement helpers. */

const PAID = new Set(["starter", "growth", "business", "pro"]);

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

export function helmIsPaidPlan(plan, billingEnforced = true) {
  if (!billingEnforced) return true;
  return PAID.has(normalizePlan(plan));
}
