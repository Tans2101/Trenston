/**
 * Shared page data fetcher — thin react-query wrapper.
 *
 * Choice (a): keep the useFetch(path) API so every department tab gets
 * stale-while-revalidate caching without rewriting each page. Query keys are
 * ["fetch", path, ...deps] so mutations can invalidate with invalidateFetchQueries().
 *
 * Freshness is driven by write-path invalidation (frontend + backend), not by
 * a long staleTime. The short staleTime only dedupes rapid remounts / tab
 * switches so revisits show last data instantly while a background refetch
 * runs when the entry is stale.
 */
import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { invalidateFetchQueries } from "@/lib/fetchInvalidation";
import { friendlyRequestError } from "@/lib/friendlyErrors";

/** Short client stale window — safety net / dedupe only; writes invalidate. */
export const FETCH_STALE_MS = 5_000;

/** Stable default so omitted deps don't allocate a new [] every render. */
const EMPTY_DEPS = [];

export function fetchQueryKey(path) {
  return ["fetch", path];
}

export function useFetch(path, deps = EMPTY_DEPS) {
  const queryClient = useQueryClient();
  const enabled = Boolean(path);
  // deps are folded into the key so callers that pass e.g. [weekStart] refetch
  // when those change, matching the previous useEffect dependency behavior.
  // Memoize so useCallback(setData) doesn't see a new key array every render
  // (CI treats that exhaustive-deps warning as a build error).
  const queryKey = useMemo(
    () => (enabled ? ["fetch", path, ...deps] : ["fetch", "__disabled__"]),
    // Spread caller deps (primitives) — do not depend on the deps array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps is a value list
    [enabled, path, ...deps],
  );

  const query = useQuery({
    queryKey,
    enabled,
    staleTime: FETCH_STALE_MS,
    // Remount after staleTime → show cache, refetch in background (no skeleton).
    refetchOnMount: true,
    refetchOnWindowFocus: true,
    queryFn: async () => {
      const { data } = await api.get(path);
      return data;
    },
  });

  const setData = useCallback(
    (updater) => {
      queryClient.setQueryData(queryKey, (prev) => {
        if (typeof updater === "function") return updater(prev ?? null);
        return updater;
      });
    },
    [queryClient, queryKey],
  );

  // isLoading = pending && fetching — false when cached data exists (tab revisit).
  const loading = enabled ? query.isLoading : false;

  return {
    data: enabled ? (query.data ?? null) : null,
    loading,
    error: enabled ? (query.error ?? null) : null,
    reload: () => query.refetch(),
    setData,
    // True while a (re)fetch is in flight — lets deep links wait for fresh
    // data instead of judging a just-created record against a stale cache.
    isFetching: enabled ? Boolean(query.isFetching) : false,
  };
}

export function useInvalidateFetch() {
  const queryClient = useQueryClient();
  return useCallback(
    (pathPrefix) => invalidateFetchQueries(queryClient, pathPrefix),
    [queryClient],
  );
}

export { invalidateFetchQueries };

export function fetchErrorMessage(error, fallback = "Could not load data. Check your connection and try again.") {
  if (!error) return fallback;
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((d) => d.msg || String(d)).join(", ");
  const friendly = friendlyRequestError(error);
  if (friendly) return friendly;
  // Axios' own messages ("Network Error", "Request failed with status code 500") are not user copy.
  if (error?.isAxiosError) return fallback;
  return error?.message || fallback;
}

/** Parse API error detail when responseType was blob (e.g. CSV download). */
export async function blobErrorDetail(error, fallback = "Request failed") {
  const data = error?.response?.data;
  if (data instanceof Blob) {
    try {
      const text = await data.text();
      const parsed = JSON.parse(text);
      if (typeof parsed?.detail === "string") return parsed.detail;
    } catch {
      /* ignore */
    }
  }
  return fetchErrorMessage(error, fallback);
}
