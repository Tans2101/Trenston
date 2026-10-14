const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function withTimeout(promise, ms, label = "timeout") {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      setTimeout(() => reject(new Error(label)), ms);
    }),
  ]);
}

function jwtExpMs(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

let cachedToken = null;
let cachedExpMs = 0;
let inflight = null;
let cacheGeneration = 0;

/** Drop cached JWT (e.g. after sign-out). */
export function clearClerkTokenCache() {
  cachedToken = null;
  cachedExpMs = 0;
  inflight = null;
  cacheGeneration += 1;
}

/**
 * Fast path for API calls: reuse Clerk JWT until ~60s before expiry.
 * Uses Clerk's own cache (skipCache: false) — never hammer Clerk on every click.
 * On refresh failure, still returns a not-yet-expired cached token when possible.
 */
export async function getCachedClerkToken(getToken, session, { tokenTimeoutMs = 1500 } = {}) {
  const now = Date.now();
  if (cachedToken && cachedExpMs - 60_000 > now) {
    return cachedToken;
  }
  if (inflight) return inflight;

  const gen = cacheGeneration;
  const priorToken = cachedToken && cachedExpMs > now + 5_000 ? cachedToken : null;

  inflight = (async () => {
    try {
      // Fetch session + auth tokens in parallel so a cold refresh finishes in
      // ~tokenTimeoutMs instead of up to 2× that when run sequentially.
      const [fromSession, fromAuth] = await Promise.all([
        session?.getToken
          ? withTimeout(session.getToken(), tokenTimeoutMs, "session-token-timeout").catch(() => null)
          : Promise.resolve(null),
        withTimeout(getToken(), tokenTimeoutMs, "auth-token-timeout").catch(() => null),
      ]);
      const token = fromSession || fromAuth;
      if (gen !== cacheGeneration) return null;
      if (token && token.split(".").length === 3) {
        cachedToken = token;
        cachedExpMs = jwtExpMs(token) || now + 55_000;
        return token;
      }
      // Refresh timed out / failed — keep serving a still-valid JWT.
      return priorToken;
    } finally {
      if (gen === cacheGeneration) inflight = null;
    }
  })();

  return inflight;
}

/**
 * Bootstrap / first-sign-in only: bounded retries.
 * Prefer Clerk cache; only skipCache on later attempts if the first fails.
 */
export async function resolveClerkToken(
  getToken,
  session,
  { attempts = 4, delayMs = 300, tokenTimeoutMs = 8000 } = {},
) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      // Never abandon the first request early: giving up after 2s and forcing a
      // fresh network fetch each time kept restarting slow Clerk round-trips
      // (typical from far-away regions) so sign-in never finished.
      const skipCache = i > 1;
      const opts = skipCache ? { skipCache: true } : undefined;
      // Ask both in parallel (they return the same JWT); the old sequential
      // awaits could burn 2× the timeout on every attempt.
      const [fromSession, fromAuth] = await Promise.all([
        session
          ? withTimeout(session.getToken(opts), tokenTimeoutMs, "session-token-timeout").catch(() => null)
          : Promise.resolve(null),
        withTimeout(getToken(opts), tokenTimeoutMs, "auth-token-timeout").catch(() => null),
      ]);
      const token = fromSession || fromAuth;
      if (token && token.split(".").length === 3) {
        cachedToken = token;
        cachedExpMs = jwtExpMs(token) || Date.now() + 55_000;
        return token;
      }
    } catch {
      /* retry */
    }
    await sleep(delayMs);
  }
  return null;
}
