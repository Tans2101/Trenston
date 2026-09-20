/**
 * Map mutation URL prefixes → useFetch path prefixes to invalidate.
 * Called from the shared API client after successful writes so every tab's
 * react-query cache drops immediately (freshness guarantee), instead of
 * waiting out FETCH_STALE_MS.
 */
import { getAppQueryClient } from "./queryClient";

const MUTATION_INVALIDATIONS = [
  { match: "/production/work-orders", paths: ["/production/work-orders", "/me/work-items", "/calendar"] },
  { match: "/procurement/requests", paths: ["/procurement/requests", "/me/work-items", "/calendar", "/production/work-orders", "/financials", "/briefing"] },
  { match: "/procurement/settings", paths: ["/procurement/requests", "/procurement/settings", "/briefing"] },
  { match: "/maintenance/settings", paths: ["/maintenance/tickets", "/maintenance/settings", "/briefing"] },
  { match: "/legal/matters", paths: ["/legal/matters", "/me/work-items", "/calendar"] },
  { match: "/maintenance/tickets", paths: ["/maintenance/tickets", "/me/work-items", "/calendar", "/production/work-orders"] },
  { match: "/hr/", paths: ["/hr/", "/me/work-items", "/members"] },
  { match: "/sales/targets", paths: ["/sales/order-book", "/briefing"] },
  { match: "/sales/order-book", paths: ["/sales/order-book", "/briefing"] },
  { match: "/maintenance/", paths: ["/maintenance/tickets", "/maintenance/spares", "/maintenance/schedules", "/maintenance/contracts", "/maintenance/settings", "/briefing"] },
  { match: "/deals", paths: ["/deals", "/telemetry", "/briefing"] },
  { match: "/financials", paths: ["/financials", "/briefing", "/telemetry"] },
  { match: "/documents", paths: ["/financials", "/documents"] },
  { match: "/tasks", paths: ["/tasks", "/tasks/me", "/me/work-items"] },
  { match: "/decisions", paths: ["/decisions", "/briefing", "/me/work-items"] },
  { match: "/notes", paths: ["/notes"] },
  { match: "/updates", paths: ["/updates/me", "/updates/today"] },
  { match: "/calendar", paths: ["/calendar"] },
  { match: "/people", paths: ["/people", "/members"] },
  { match: "/reports", paths: ["/reports"] },
  { match: "/telemetry", paths: ["/telemetry", "/briefing"] },
  { match: "/integrations", paths: ["/integrations", "/calendar", "/briefing", "/financials"] },
  { match: "/members", paths: ["/members", "/people", "/access/sections"] },
  { match: "/departments", paths: ["/departments"] },
];

export function fetchPathsToInvalidate(method, urlPath) {
  if (!method || !urlPath) return [];
  const m = method.toUpperCase();
  if (m === "GET" || m === "HEAD" || m === "OPTIONS") return [];
  const path = urlPath.split("?")[0];
  const out = new Set();
  for (const rule of MUTATION_INVALIDATIONS) {
    if (path === rule.match || path.startsWith(rule.match)) {
      rule.paths.forEach((p) => out.add(p));
    }
  }
  return [...out];
}

/** Invalidate every useFetch cache whose path starts with prefix (e.g. "/deals"). */
export function invalidateFetchQueries(queryClient, pathPrefix) {
  if (!queryClient) return Promise.resolve();
  return queryClient.invalidateQueries({
    predicate: (q) => {
      const key = q.queryKey;
      if (!Array.isArray(key) || key[0] !== "fetch") return false;
      if (!pathPrefix) return true;
      const path = key[1];
      return typeof path === "string" && (
        path === pathPrefix
        || path.startsWith(`${pathPrefix}?`)
        || path.startsWith(`${pathPrefix}/`)
      );
    },
  });
}

export function invalidateFetchAfterMutation(method, urlPath) {
  const client = getAppQueryClient();
  if (!client) return;
  const prefixes = fetchPathsToInvalidate(method, urlPath);
  prefixes.forEach((p) => {
    invalidateFetchQueries(client, p);
  });
  // Pipeline uses a dedicated ["deals", ...] key, not useFetch.
  if (prefixes.includes("/deals") || (urlPath || "").includes("/deals")) {
    client.invalidateQueries({ queryKey: ["deals"] });
  }
}
