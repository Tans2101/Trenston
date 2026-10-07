import { Suspense } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { AppLayout, WorkspaceGate } from "@/components/lazyAppShell";
import { LoadingScreen } from "@/components/kit";

export default function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) return <LoadingScreen label="Loading cockpit" />;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <Suspense fallback={<LoadingScreen label="Loading cockpit" />}>
      {user.needs_workspace ? <WorkspaceGate /> : <AppLayout />}
    </Suspense>
  );
}
