/**
 * Pure helpers for My Day — soft-refresh vs fatal load, section readiness.
 * Kept out of the React page so behavior is unit-testable (matches Decisions/Briefing).
 */

/** Soft-refresh only: cached payload exists while a background refetch failed. */
export function isSoftMyDayFeedError(error, data) {
  return Boolean(error && data);
}

/**
 * Fatal for a single feed only when there is no cached payload.
 * Decisions stay optional for the rest of the page (section-local error).
 */
export function isFatalMyDayFeed(error, data) {
  return Boolean((error && !data) || (!error && data === undefined));
}

/** True when every required feed is still on first load with no cache. */
export function isMyDayInitialLoading(feeds) {
  return (feeds || []).every(({ loading, data }) => loading && !data);
}

/** Any required feed has a soft-refresh failure. */
export function hasMyDaySoftRefreshError(feeds) {
  return (feeds || []).some(({ error, data }) => isSoftMyDayFeedError(error, data));
}
