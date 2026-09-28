/** Ledger category options for the Financials entry form. Free text server-side. */

export const REVENUE_CATEGORIES = ["Subscriptions", "Product sales", "Services", "Enterprise", "Other"];
export const EXPENSE_CATEGORIES = [
  "Payroll", "Cost of goods", "Cloud/Infra", "Sales & Mktg", "G&A", "R&D Tools", "Other",
];

// CompanySetup INDUSTRIES whose revenue is mostly selling physical goods.
export const GOODS_INDUSTRIES = new Set([
  "Manufacturing",
  "Retail",
  "Food & Beverage",
  "Agriculture",
  "E-commerce",
  "Hardware / Robotics",
]);

// Service-led industries whose revenue is mostly client work.
export const SERVICES_INDUSTRIES = new Set([
  "Professional Services",
  "Construction",
  "Logistics",
  "Healthcare",
  "Education",
]);

export function defaultRevenueCategory(industry) {
  if (GOODS_INDUSTRIES.has(industry)) return "Product sales";
  if (SERVICES_INDUSTRIES.has(industry)) return "Services";
  return "Subscriptions";
}
