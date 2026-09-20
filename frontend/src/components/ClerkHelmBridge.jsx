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
      { headers: { Authorization: `Bearer ${token}` } },
    );
    return data;
  } catch (exchangeErr) {
    if (exchangeErr?.response?.status === 404) {
      const { data } = await api.get("/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
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
    if (!clerkReady || !clerkComplete || user) return;

    const runId = ++syncRunId.current;
    let cancelled = false;

    (async () => {
      clearSessionError();
      for (let attempt = 0; attempt < 40 && !cancelled; attempt += 1) {
        try {
          const token = await resolveClerkToken(getToken, session);
          if (!token) {
            await sleep(500);
            continue;
          }
          const data = await exchangeClerkSession(token);
          if (cancelled || runId !== syncRunId.current) return;
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
          if (attempt < 5 && (status >= 500 || !status)) {
            await sleep(1000);
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
