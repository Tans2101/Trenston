import { useEffect, useRef } from "react";
import { useAuth as useClerkAuth, useSession } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import { useClerkMode } from "@/components/ClerkProviderBootstrap";
import { useAuth } from "@/context/AuthContext";
import { api, setClerkTokenGetter } from "@/lib/api";
import { clearClerkTokenCache, getCachedClerkToken, resolveClerkToken } from "@/lib/clerkToken";
import { clerkSessionComplete, CLERK_AUTH_OPTS } from "@/lib/clerkSession";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function exchangeClerkSession(token) {
  try {
    const { data } = await api.post(
      "/auth/clerk/exchange",
      {},
      // Shorter than the default 20s: a stuck request is retried quickly instead
      // of leaving the user staring at "Connecting your account".
      { headers: { Authorization: `Bearer ${token}` }, timeout: 25000 },
    );
    return data;
  } catch (exchangeErr) {
    if (exchangeErr?.response?.status === 404) {
      const { data } = await api.get("/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 25000,
      });
      return data;
    }
    throw exchangeErr;
  }
}

/** Sync Clerk session → Trenston user via POST /auth/clerk/exchange */
export default function ClerkHelmBridge() {
  const {
    isLoaded, isSignedIn, getToken, userId, sessionId, sessionStatus,
  } = useClerkAuth(CLERK_AUTH_OPTS);
  const { session, isLoaded: sessionLoaded } = useSession();
  const { user, setUser, setSessionError, clearSessionError } = useAuth();
  const { helmCanonicalOrigin, clerkPrimaryOrigin, clerkMultiDomain } = useClerkMode();
  const navigate = useNavigate();
  const syncRunId = useRef(0);
  const tokenGetterRef = useRef(null);
  const lastExchangedClerkUserId = useRef(null);

  const clerkReady = isLoaded && sessionLoaded;
  const clerkComplete = clerkSessionComplete({
    isSignedIn, userId, sessionId, session, sessionStatus,
  });

  // Keep getter registration stable — update via ref so dep churn doesn't null the
  // interceptor mid-flight or wipe a still-valid JWT cache.
  tokenGetterRef.current = { clerkComplete, getToken, session };

  useEffect(() => {
    setClerkTokenGetter(async () => {
      const cur = tokenGetterRef.current;
      if (!cur?.clerkComplete) return null;
      return getCachedClerkToken(cur.getToken, cur.session);
    });
    return () => setClerkTokenGetter(null);
  }, []);

  useEffect(() => {
    if (!clerkComplete) {
      clearClerkTokenCache();
    }
  }, [clerkComplete]);

  useEffect(() => {
    if (!clerkReady || !clerkComplete) return;

    // Already synced this Clerk identity into Trenston.
    if (user && lastExchangedClerkUserId.current === userId) return;
    // First paint after setUser before the ref is stamped — record and hold.
    if (user && lastExchangedClerkUserId.current == null) {
      lastExchangedClerkUserId.current = userId;
      return;
    }
    // Clerk account switched while a Trenston principal is still set — drop and re-exchange.
    if (user && lastExchangedClerkUserId.current !== userId) {
      lastExchangedClerkUserId.current = null;
      setUser(null);
      return;
    }

    const runId = ++syncRunId.current;
    let cancelled = false;

    (async () => {
      clearSessionError();
      const t0 = Date.now();
      for (let attempt = 0; attempt < 40 && !cancelled; attempt += 1) {
        try {
          const token = await resolveClerkToken(getToken, session);
          const tTok = Date.now() - t0;
          if (!token) {
            await sleep(500);
            continue;
          }
          const data = await exchangeClerkSession(token);
          // Timing breadcrumb so a slow sign-in can be diagnosed from the browser console.
          console.info(`[trenston-auth] token ${tTok}ms, exchange ${Date.now() - t0 - tTok}ms, attempt ${attempt + 1}`);
          if (cancelled || runId !== syncRunId.current) return;
          lastExchangedClerkUserId.current = userId;
          setUser(data);
          clearSessionError();
          // Clerk may redirect to apexcoach.tech; send user to helmcontrol after session exchange.
          if (
            clerkMultiDomain
            && helmCanonicalOrigin
            && clerkPrimaryOrigin
            && typeof window !== "undefined"
          ) {
            const here = window.location.origin.replace(/\/$/, "");
            const clerkOrigin = clerkPrimaryOrigin.replace(/\/$/, "");
            const canon = helmCanonicalOrigin.replace(/\/$/, "");
            if (here === clerkOrigin && canon !== clerkOrigin) {
              window.location.replace(`${canon}/app`);
              return;
            }
          }
          // Only enter the cockpit from auth entry routes. Marketing pages
          // (/about, /features, …) must stay reachable while signed in.
          const path = window.location.pathname;
          const fromAuthEntry =
            path.startsWith("/login") || path.startsWith("/sign-up");
          if (fromAuthEntry) {
            navigate("/app", { replace: true });
          }
          return;
        } catch (e) {
          const status = e?.response?.status;
          if (status === 503 && attempt < 39) {
            await sleep(1500);
            continue;
          }
          if (attempt < 8 && (status >= 500 || !status)) {
            await sleep(500);
            continue;
          }
          if (cancelled || runId !== syncRunId.current) return;
          const detail = e?.response?.data?.detail;
          setSessionError(
            typeof detail === "string"
              ? detail
              : `Sign-in failed (${status || "network"}).`,
          );
          console.error("Clerk Trenston sync failed", e?.response?.data || e);
          return;
        }
      }
      if (!cancelled && runId === syncRunId.current) {
        setSessionError("Clerk session not ready. Wait a moment, then refresh.");
      }
    })();

    return () => { cancelled = true; };
  }, [
    clerkReady, clerkComplete, user, session?.id, sessionId, userId, sessionStatus,
    getToken, session, setUser, setSessionError, clearSessionError, navigate,
    clerkMultiDomain, clerkPrimaryOrigin, helmCanonicalOrigin,
  ]);

  return null;
}
