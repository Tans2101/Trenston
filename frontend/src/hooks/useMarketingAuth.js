import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

/**
 * Auth CTA helpers for public marketing pages.
 * Does not wait on Clerk /api/auth/config — public routes sit outside ClerkProviderBootstrap.
 * With PublicShell's deferInitialAuth, this never blocks on a backend call.
 */
export function useMarketingAuth() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  const authed = !loading && !!user;
  const enter = () => navigate(authed ? "/app" : "/sign-up");
  return { authed, enter, loading };
}
