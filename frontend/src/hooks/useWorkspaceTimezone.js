import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { DEFAULT_TIMEZONE } from "@/lib/dates";

/** Workspace IANA timezone from the cached /company query (default Asia/Manila). */
export function useWorkspaceTimezone() {
  const { data: company } = useCompanyQuery();
  return company?.timezone || DEFAULT_TIMEZONE;
}
