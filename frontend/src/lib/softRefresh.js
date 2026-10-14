/**
 * Soft-refresh contract for useFetch pages: keep cached UI when a background
 * refetch fails; only block the page when there is nothing to show.
 */

export function isFatalSoftLoad({ error, data }) {
  return Boolean((error && !data) || !data);
}

export function softRefreshKey(error) {
  return error?.message || error?.code || "soft-refresh";
}
