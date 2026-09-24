/** Workspace-local calendar helpers. The workspace timezone (IANA) defaults to Asia/Manila. */

export const DEFAULT_TIMEZONE = "Asia/Manila";

function safeTz(tz) {
  const name = (tz || "").trim() || DEFAULT_TIMEZONE;
  try {
    new Intl.DateTimeFormat("en-CA", { timeZone: name });
    return name;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

/** YYYY-MM-DD for "today" in the given timezone (not the browser's, not UTC). */
export function todayISO(tz) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: safeTz(tz),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

/** YYYY-MM for the current month in the given timezone. */
export function thisMonthISO(tz) {
  return todayISO(tz).slice(0, 7);
}

/** Shift a YYYY-MM-DD string by whole days (calendar math, timezone-free). */
export function addDaysISO(iso, days) {
  const [y, m, d] = String(iso).split("-").map(Number);
  const dt = new Date(Date.UTC(y, (m || 1) - 1, d || 1));
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

/** "9:05 AM"-style local time for an ISO timestamp in the given timezone. */
export function formatTimeInTz(iso, tz) {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: safeTz(tz),
    hour: "numeric",
    minute: "2-digit",
  }).format(dt);
}

/** All IANA zones the browser knows (falls back to the default when unsupported). */
export function supportedTimezones() {
  try {
    if (typeof Intl.supportedValuesOf === "function") {
      return Intl.supportedValuesOf("timeZone");
    }
  } catch {
    /* older browsers */
  }
  return [DEFAULT_TIMEZONE];
}
