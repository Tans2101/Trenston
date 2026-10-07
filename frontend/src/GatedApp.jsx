/**
 * Auth-gated shell for /login, /sign-up and /app/*. Loaded on demand so public
 * marketing pages do not download Clerk or the signed-in app.
 */
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import { AuthProvider } from "@/context/AuthContext";
import ClerkHelmBridge from "@/components/ClerkHelmBridge";
import AppearanceSync from "@/components/AppearanceSync";
import ClerkProviderBootstrap, { useClerkMode } from "@/components/ClerkProviderBootstrap";
import ProtectedRoute from "@/components/ProtectedRoute";
import ProtectedRouteClerk from "@/components/ProtectedRouteClerk";
import ErrorBoundary from "@/components/ErrorBoundary";
import { LoadingScreen } from "@/components/kit";

export function AppProtectedGate() {
  const { clerkEnabled, configLoading } = useClerkMode();
  if (configLoading) {
    return <LoadingScreen label="Loading cockpit" />;
  }
  const Protected = clerkEnabled ? ProtectedRouteClerk : ProtectedRoute;
  return <Protected />;
}


function ClerkAuthShell() {
  const { signOut } = useClerk();
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <Navigate to="/login?error=session_retired" replace />;
  }
  return (
    <AuthProvider onLogoutExtra={() => signOut()} deferInitialAuth>
      <ErrorBoundary>
        <AppearanceSync />
        <ClerkHelmBridge />
        <Outlet />
      </ErrorBoundary>
    </AuthProvider>
  );
}


function TrenstonAppShell() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <Navigate to="/login?error=session_retired" replace />;
  }
  return (
    <AuthProvider>
      <ErrorBoundary>
        <AppearanceSync />
        <Outlet />
      </ErrorBoundary>
    </AuthProvider>
  );
}


/** /login, /sign-up, /app/* — wait on useClerkMode (/api/auth/config). */
function ClerkGatedShell() {
  const { clerkEnabled, configLoading } = useClerkMode();
  if (configLoading) {
    return <LoadingScreen label="Loading" />;
  }
  return clerkEnabled ? <ClerkAuthShell /> : <TrenstonAppShell />;
}


export default function GatedLayout() {
  return (
    <ClerkProviderBootstrap>
      <ClerkGatedShell />
    </ClerkProviderBootstrap>
  );
}
