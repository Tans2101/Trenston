/** Clerk component paths — set in app code / build env (Dashboard Paths are locked in Core 2).
 * CRA: REACT_APP_CLERK_SIGN_IN_URL, REACT_APP_CLERK_SIGN_UP_URL
 * @see https://clerk.com/docs/guides/development/clerk-environment-variables
 */
export const CLERK_SIGN_IN_PATH = (
  process.env.REACT_APP_CLERK_SIGN_IN_URL || "/login"
).trim() || "/login";

export const CLERK_SIGN_UP_PATH = (
  process.env.REACT_APP_CLERK_SIGN_UP_URL || "/sign-up"
).trim() || "/sign-up";

export const CLERK_AFTER_AUTH_PATH = (
  process.env.REACT_APP_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL
  || process.env.REACT_APP_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL
  || process.env.REACT_APP_CLERK_SIGN_IN_FORCE_REDIRECT_URL
  || process.env.REACT_APP_CLERK_SIGN_UP_FORCE_REDIRECT_URL
  || "/app"
).trim() || "/app";

/** Absolute Trenston URLs for OAuth redirect_url allow-list (must be full URL). */
export function helmOrigin() {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return (process.env.REACT_APP_HELM_ORIGIN || "").trim();
}

export function helmAppUrl(path = "/app") {
  const origin = helmOrigin();
  const p = path.startsWith("/") ? path : `/${path}`;
  return origin ? `${origin}${p}` : p;
}

/** Canonical app origin for absolute Clerk URLs (never accounts.*). */
export function helmCanonicalOrigin(fallback) {
  const fromApi = (fallback || "").trim().replace(/\/$/, "");
  if (fromApi) return fromApi;
  return helmOrigin();
}

/** Component path for Sign-in (path-style — what ClerkProvider expects). */
export function helmSignInUrl(canonicalOrigin) {
  if (!canonicalOrigin) return CLERK_SIGN_IN_PATH;
  // Same-site: prefer path so clerk-js does not fall back to Account Portal host.
  const origin = helmCanonicalOrigin(canonicalOrigin);
  const live = typeof window !== "undefined" ? window.location.origin : "";
  if (!live || origin === live || origin.includes("trenston.com")) {
    return CLERK_SIGN_IN_PATH;
  }
  return `${origin}${CLERK_SIGN_IN_PATH}`;
}

/** Component path for Sign-up. */
export function helmSignUpUrl(canonicalOrigin) {
  if (!canonicalOrigin) return CLERK_SIGN_UP_PATH;
  const origin = helmCanonicalOrigin(canonicalOrigin);
  const live = typeof window !== "undefined" ? window.location.origin : "";
  if (!live || origin === live || origin.includes("trenston.com")) {
    return CLERK_SIGN_UP_PATH;
  }
  return `${origin}${CLERK_SIGN_UP_PATH}`;
}

/** Absolute SSO callback for authenticateWithRedirect (allow-listed on Clerk). */
export function clerkSsoCallbackUrl(mode = "sign-in") {
  const base = mode === "sign-up" ? CLERK_SIGN_UP_PATH : CLERK_SIGN_IN_PATH;
  return helmAppUrl(`${base}/sso-callback`);
}

/** Clerk post-auth redirect — absolute only for true multi-domain. */
export function clerkPostAuthUrl(fallback) {
  return fallback || helmAppUrl(CLERK_AFTER_AUTH_PATH);
}
