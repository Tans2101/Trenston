import { Suspense, useEffect } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { rememberOAuthReturn, takeOAuthReturn } from "@/lib/oauthReturn";
import { useAuth } from "@/context/AuthContext";
import { AppLayout, WorkspaceGate } from "@/components/lazyAppShell";
import { LoadingScreen } from "@/components/kit";

export default function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (!user) return;
    const target = takeOAuthReturn();
    if (target && target !== `${location.pathname}${location.search}`) navigate(target, { replace: true });
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <LoadingScreen label="Loading cockpit" />;
  if (!user) {
    rememberOAuthReturn(location);
    return <Navigate to="/login" replace />;
  }
  return (
    <Suspense fallback={<LoadingScreen label="Loading cockpit" />}>
      {user.needs_workspace ? <WorkspaceGate /> : <AppLayout />}
    </Suspense>
  );
}
