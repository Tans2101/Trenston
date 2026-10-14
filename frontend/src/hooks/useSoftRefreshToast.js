import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { fetchErrorMessage } from "@/hooks/useFetch";
import { softRefreshKey } from "@/lib/softRefresh";

/**
 * When a background refetch fails but the page still has data, keep the page and
 * say so once (per error), instead of replacing everything with an error screen.
 */
export function useSoftRefreshToast(error, data, fallback = "Could not refresh. Showing the last loaded data.") {
  const shownFor = useRef(null);
  const soft = Boolean(error && data);
  useEffect(() => {
    if (!soft) {
      shownFor.current = null;
      return;
    }
    const key = softRefreshKey(error);
    if (shownFor.current === key) return;
    shownFor.current = key;
    toast.error(fetchErrorMessage(error, fallback));
  }, [soft, error, fallback]);
}
