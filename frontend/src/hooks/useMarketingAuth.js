import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { track } from "@/lib/analytics";

/**
 * Auth CTA helpers for public marketing pages.
 * Does not wait on Clerk /api/auth/config — public routes sit outside ClerkProviderBootstrap.
 * With PublicShell's deferInitialAuth, this never blocks on a backend call.
 */
export function useMarketingAuth() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  const authed = !loading && !!user;
  const enter = (e) => {
    // Called straight from onClick: the button's test id says which CTA it was.
    const where = e?.currentTarget?.dataset?.testid || "cta";
    if (!authed) track("cta_click", { where });
    navigate(authed ? "/app" : "/sign-up");
  };
  return { authed, enter, loading };
}
