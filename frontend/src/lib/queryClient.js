/** Shared QueryClient handle so axios can invalidate useFetch caches after writes. */
let _client = null;

export function setAppQueryClient(client) {
  _client = client;
}

export function getAppQueryClient() {
  return _client;
}

/**
 * Retry network blips and server errors, never "no access" / "not found" /
 * bad input. A 403 used to retry 3 times with backoff, so a teammate opening
 * a page they can't see stared at a loading skeleton for ~7 seconds.
 */
export function shouldRetryQuery(failureCount, error) {
  const status = error?.response?.status;
  if (status >= 400 && status < 500 && status !== 408 && status !== 429) return false;
  return failureCount < 3;
}
