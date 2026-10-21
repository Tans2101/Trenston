import { useFetch } from "@/hooks/useFetch";

/**
 * Whether this company has a custom dashboard the signed-in person may open,
 * and whether they are the Trenston operator (who manages custom clients).
 * Errors read as "no custom dashboard" so the normal app is never blocked.
 */
export function useCustomDashboardStatus() {
  const { data } = useFetch("/custom-dashboard/status");
  return {
    customEnabled: Boolean(data?.enabled),
    customTitle: data?.title || "Custom dashboard",
    operator: Boolean(data?.operator),
    customBilling: Boolean(data?.custom_billing),
  };
}
