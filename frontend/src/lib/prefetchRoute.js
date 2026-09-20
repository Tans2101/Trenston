/**
 * Lazy route chunk prefetch — call on nav hover/focus so the first click
 * into a cold tab does not wait on the network for the JS bundle.
 */
const prefetchers = {
  "/app": () => import("@/pages/Briefing"),
  "/app/me": () => import("@/pages/MyDay"),
  "/app/sales": () => import("@/pages/Pipeline"),
  "/app/decisions": () => import("@/pages/Decisions"),
  "/app/telemetry": () => import("@/pages/Telemetry"),
  "/app/financials": () => import("@/pages/Financials"),
  "/app/tasks": () => import("@/pages/Tasks"),
  "/app/reports": () => import("@/pages/Reports"),
  "/app/calendar": () => import("@/pages/CalendarPage"),
  "/app/people": () => import("@/pages/People"),
  "/app/ask": () => import("@/pages/AskHelm"),
  "/app/members": () => import("@/pages/Members"),
  "/app/integrations": () => import("@/pages/Integrations"),
  "/app/billing": () => import("@/pages/Billing"),
  "/app/settings": () => import("@/pages/AccountSettings"),
  "/app/help": () => import("@/pages/AppHelp"),
  "/app/departments/production": () => import("@/pages/Production"),
  "/app/departments/procurement": () => import("@/pages/Procurement"),
  "/app/departments/legal": () => import("@/pages/Legal"),
  "/app/departments/engineering_maintenance": () => import("@/pages/Maintenance"),
  "/app/departments/hr": () => import("@/pages/HR"),
};

const warmed = new Set();

export function prefetchRoute(to) {
  if (!to || typeof to !== "string") return;
  const path = to.split("?")[0].replace(/\/$/, "") || "/app";
  if (warmed.has(path)) return;
  const loader = prefetchers[path];
  if (!loader) {
    // Unknown department placeholder / dynamic path — warm the placeholder chunk.
    if (path.startsWith("/app/departments/")) {
      warmed.add(path);
      import("@/pages/DepartmentPlaceholder").catch(() => {});
    }
    return;
  }
  warmed.add(path);
  loader().catch(() => {
    warmed.delete(path);
  });
}

export function prefetchRouteHandlers(to) {
  return {
    onMouseEnter: () => prefetchRoute(to),
    onFocus: () => prefetchRoute(to),
  };
}
