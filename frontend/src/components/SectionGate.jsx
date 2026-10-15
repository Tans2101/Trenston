import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { LoadingScreen } from "@/components/kit";

/**
 * Route guard for Manage Access sections (e.g. telemetry, financials).
 * Pack holders and explicitly granted members pass via user.granted_sections.
 */
export default function SectionGate({ section, children, fallback = null }) {
  const { user, loading } = useAuth();

  if (loading) return <LoadingScreen label="Loading cockpit" />;
  if (!user) return <Navigate to="/login" replace />;

  const granted = user.granted_sections || [];
  if (section && !granted.includes(section)) {
    const dest = fallback || user.default_route || "/app";
    return <Navigate to={dest} replace />;
  }
  return children;
}
