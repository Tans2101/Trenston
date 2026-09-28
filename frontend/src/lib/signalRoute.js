/**
 * One place that knows where each part of Trenston lives, so any screen can
 * send the user straight to the record behind a signal, decision, task or
 * department item — instead of a generic page they have to search.
 *
 * Deep-link conventions (each target page reads these on mount):
 *   /app/decisions?focus=<decisionId>          scroll + highlight a decision
 *   /app/tasks?task=<taskId>                   scroll + highlight a task
 *   /app/sales?deal=<dealId>                   scroll + highlight a deal
 *   /app/financials#entry-<entryId>            scroll + highlight a ledger row
 *   /app/financials#log-entry | #log-mrr | #cash   open the matching form
 *   /app/departments/<type>?item=<id>          open that department item
 *   /app/departments/hr?tab=leave&request=<id> open a leave request
 *   /app/departments/hr?employee=<id>          open an employee record
 *   /app/departments/engineering_maintenance#spares|#schedule|#contracts
 */
import { departmentPath } from "@/lib/departmentRoutes";

const q = (v) => encodeURIComponent(String(v));

export const decisionHref = (id) => (id ? `/app/decisions?focus=${q(id)}` : "/app/decisions");
export const taskHref = (id) => (id ? `/app/tasks?task=${q(id)}` : "/app/tasks");
export const dealHref = (id) => (id ? `/app/sales?deal=${q(id)}` : "/app/sales");
export const entryHref = (id) => (id ? `/app/financials#entry-${id}` : "/app/financials");

/** Department item deep link. HR leave requests use their own tab. */
export function departmentItemHref(type, id, { leaveRequest = false } = {}) {
  if (!type) return null;
  const base = departmentPath(type);
  if (!id) return base;
  if (type === "hr" && leaveRequest) return `${base}?tab=leave&request=${q(id)}`;
  // Sales and finance lanes have their own pages with their own params.
  if (type === "sales") return dealHref(id);
  if (type === "accounting_finance") return entryHref(id);
  return `${base}?item=${q(id)}`;
}

const DEPT_LABELS = {
  sales: "Sales",
  accounting_finance: "Financials",
  production: "Production",
  procurement: "Procurement",
  legal: "Legal",
  engineering_maintenance: "Maintenance",
  hr: "HR",
};

/**
 * Where a decision-engine signal points. Accepts either a full signal object
 * ({type, related_id, department_type, employee_id}) or the flattened fields
 * the Briefing payload carries ({signal_type, related_id, department_type}).
 * Returns { to, label } or null when there is nothing specific to open.
 */
export function signalRoute(sig) {
  if (!sig) return null;
  const type = sig.type || sig.signal_type;
  const id = sig.related_id;
  const dept = sig.department_type;

  switch (type) {
    case "overdue_task":
      return { to: taskHref(id), label: "Open task" };
    case "stalled_deal":
    case "missed_followup":
    case "upcoming_followup":
      return { to: dealHref(id), label: "Open deal" };
    case "runway_risk":
      return { to: "/app/financials#cash", label: "Review cash & runway" };
    case "burn_increase":
    case "expense_spike":
    case "new_expense_category":
      return { to: "/app/financials", label: "Open Financials" };
    case "recurring_blocker":
      return { to: "/app/people", label: "Open team" };
    case "pending_leave_request":
      return { to: departmentItemHref("hr", id, { leaveRequest: true }), label: "Open leave request" };
    case "stalled_onboarding":
      // related_id is the onboarding instance, which HR opens via ?item=.
      if (id) return { to: departmentItemHref("hr", id), label: "Open in HR" };
      return sig.employee_id
        ? { to: `/app/departments/hr?employee=${q(sig.employee_id)}`, label: "Open in HR" }
        : { to: "/app/departments/hr", label: "Open HR" };
    default:
      break;
  }

  if (dept) {
    return { to: departmentItemHref(dept, id), label: `Open in ${DEPT_LABELS[dept] || "department"}` };
  }
  return null;
}

/** Activity / "what changed" module name → page. */
const MODULE_ROUTES = {
  decisions: "/app/decisions",
  decision: "/app/decisions",
  tasks: "/app/tasks",
  task: "/app/tasks",
  deals: "/app/sales",
  deal: "/app/sales",
  sales: "/app/sales",
  pipeline: "/app/sales",
  financials: "/app/financials",
  finance: "/app/financials",
  people: "/app/people",
  team: "/app/people",
  updates: "/app/people",
  reports: "/app/reports",
  calendar: "/app/calendar",
  production: "/app/departments/production",
  procurement: "/app/departments/procurement",
  legal: "/app/departments/legal",
  hr: "/app/departments/hr",
  engineering_maintenance: "/app/departments/engineering_maintenance",
  maintenance: "/app/departments/engineering_maintenance",
};

export function moduleRoute(module) {
  if (!module) return null;
  return MODULE_ROUTES[String(module).toLowerCase()] || null;
}

/**
 * Shared "scroll to and briefly highlight" for deep-linked records.
 * Looks up `[data-deeplink="<id>"]` first, then `#<id>`.
 */
export function highlightRecord(id, { attempts = 12, delay = 150 } = {}) {
  if (!id || typeof document === "undefined") return;
  let n = 0;
  const tryFind = () => {
    const safe = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(String(id)) : String(id);
    const el = document.querySelector(`[data-deeplink="${safe}"]`) || document.getElementById(String(id));
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("deeplink-flash");
      window.setTimeout(() => el.classList.remove("deeplink-flash"), 2400);
      return;
    }
    n += 1;
    if (n < attempts) window.setTimeout(tryFind, delay);
  };
  tryFind();
}
