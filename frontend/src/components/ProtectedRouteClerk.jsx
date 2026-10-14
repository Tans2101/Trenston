import { Suspense, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { rememberOAuthReturn, takeOAuthReturn } from "@/lib/oauthReturn";
import { useAuth as useClerkAuth, useSession, useClerk } from "@clerk/clerk-react";
import { useAuth } from "@/context/AuthContext";
import { AppLayout, WorkspaceGate } from "@/components/lazyAppShell";
import { LoadingScreen } from "@/components/kit";
import ClerkLoadError from "@/components/ClerkLoadError";
import { useClerkReady } from "@/hooks/useClerkReady";
import { clerkSessionComplete, CLERK_AUTH_OPTS } from "@/lib/clerkSession";

/** Protected routes when Clerk is enabled — wait for Clerk→Trenston session exchange. */
export default function ProtectedRouteClerk() {
  const { user, sessionError, clearSessionError, logout } = useAuth();
  const {
    isSignedIn,
    userId,
    sessionId,
    sessionStatus,
  } = useClerkAuth(CLERK_AUTH_OPTS);
  const { session } = useSession();
  const { signOut } = useClerk();
  const { clerkReady, clerkTimedOut } = useClerkReady();
  const [connectTimedOut, setConnectTimedOut] = useState(false);
  const [connectSlow, setConnectSlow] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // Resume an AI-assistant connection that started before sign-in.
  useEffect(() => {
    if (!user) return;
    const target = takeOAuthReturn();
    if (target && target !== `${location.pathname}${location.search}`) navigate(target, { replace: true });
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const clerkComplete = clerkSessionComplete({
    isSignedIn, userId, sessionId, session, sessionStatus,
  });

  // Clerk Dashboard (or user.deleted webhook) can end the Clerk session while
  // AuthContext still holds a Trenston user — clear local state and leave /app.
  useEffect(() => {
    if (!clerkReady || !user) return;
    if (clerkComplete) return;
    logout();
  }, [clerkReady, user, clerkComplete, logout]);

  useEffect(() => {
    if (user || !clerkComplete || sessionError) {
      setConnectTimedOut(false);
      setConnectSlow(false);
      return undefined;
    }
    // Longer than the bridge's own retries, so we only show an error when it is
    // genuinely stuck, not while a slow connection is still finishing.
    const t = setTimeout(() => setConnectTimedOut(true), 45000);
    const slow = setTimeout(() => setConnectSlow(true), 8000);
    return () => { clearTimeout(t); clearTimeout(slow); };
  }, [user, clerkComplete, sessionError]);

  if (clerkTimedOut) {
    return <ClerkLoadError />;
  }

  if (!clerkReady) {
    return <LoadingScreen label="Loading cockpit" />;
  }

  // Clerk session gone — logout effect above is clearing; don't flash the app.
  if (user && !clerkComplete) {
    return <LoadingScreen label="Signing out" />;
  }

  if (user) {
    return (
      <Suspense fallback={<LoadingScreen label="Loading cockpit" />}>
        {user.needs_workspace ? <WorkspaceGate /> : <AppLayout />}
      </Suspense>
    );
  }

  if (sessionStatus === "pending" && !user) {
    return <Navigate to="/sign-up" replace />;
  }

  if (clerkComplete) {
    if (sessionError || connectTimedOut) {
      const message = sessionError || "Connecting your account is taking too long. Try again.";
      return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-helm-ink p-8 text-center">
          <p className="text-lg text-helm-fg mb-2">Could not connect your account</p>
          <p className="text-sm text-helm-status-negative max-w-md mb-6">{message}</p>
          {/* Reload keeps the Clerk session and re-runs the connection; signing out is the last resort. */}
          <button
            type="button"
            className="rounded-lg bg-helm-gold text-helm-navy px-4 py-2 text-sm font-medium"
            onClick={() => window.location.reload()}
          >
            Try again
          </button>
          <button
            type="button"
            className="mt-4 text-sm text-helm-muted hover:text-helm-fg underline"
            onClick={async () => {
              clearSessionError();
              setConnectTimedOut(false);
              await signOut();
              window.location.href = "/login";
            }}
          >
            Sign out instead
          </button>
        </div>
      );
    }
    return <LoadingScreen label={connectSlow ? "Still connecting, this is taking a little longer than usual" : "Connecting your account"} />;
  }

  rememberOAuthReturn(location);
  return <Navigate to="/login" replace />;
}
