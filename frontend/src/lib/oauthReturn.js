/**
 * Keeps the page a signed-out person was trying to open alive across the login
 * page, then sends them back to it once they are signed in. That covers an email
 * link to a task or briefing, a bookmarked page, an expired session, and an
 * in-progress "Connect an AI assistant" sign-in at /app/oauth/authorize.
 *
 * Only paths inside the signed-in app (/app, /app/...) are ever stored or
 * returned, so the saved value can never send someone to another site.
 */
const KEY = "trenston_oauth_return";
const MAX_AGE_MS = 30 * 60 * 1000;

/** True for /app, /app/..., or /app?... — never for //host or other origins. */
export function isAppPath(path) {
  return (
    typeof path === "string"
    && /^\/app(\/|\?|$)/.test(path)
    && !path.includes("\\")
    && !/[\r\n]/.test(path)
  );
}

export function rememberOAuthReturn(location) {
  try {
    const path = `${location?.pathname || ""}${location?.search || ""}`;
    // The default landing page needs no memory; it is where sign-in goes anyway.
    if (!isAppPath(path) || location.pathname === "/app" || location.pathname === "/app/") return;
    sessionStorage.setItem(KEY, JSON.stringify({ path, at: Date.now() }));
  } catch {
    /* storage unavailable: the person lands on the home page instead */
  }
}

export function takeOAuthReturn() {
  try {
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    if (!raw) return null;
    let path = raw;
    let at = Date.now();
    if (raw.startsWith("{")) {
      const parsed = JSON.parse(raw);
      path = parsed?.path;
      at = Number(parsed?.at) || 0;
    }
    if (Date.now() - at > MAX_AGE_MS) return null;
    return isAppPath(path) ? path : null;
  } catch {
    return null;
  }
}
