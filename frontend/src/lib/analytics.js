/**
 * Anonymous funnel events. No cookies, no user ids, no IP stored (the server
 * only uses the IP for rate limiting). Respects Do Not Track. Never throws and
 * never blocks the click that triggered it.
 *
 * Allowed names and props are enforced again server-side (backend/site_events.py).
 */
import { API } from "@/lib/api";

function trackingOff() {
  try {
    return navigator.doNotTrack === "1" || window.doNotTrack === "1";
  } catch {
    return false;
  }
}

export function track(name, props = {}) {
  try {
    if (typeof window === "undefined" || trackingOff()) return;
    const body = JSON.stringify({ name, path: window.location.pathname, props });
    fetch(`${API}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
      credentials: "omit",
    }).catch(() => {});
  } catch {
    /* tracking must never break the page */
  }
}
