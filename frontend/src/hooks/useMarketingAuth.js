import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { track } from "@/lib/analytics";

/**
 * Auth CTA helpers for public marketing pages.
 * Does not wait on Clerk /api/auth/config — public routes sit outside ClerkProviderBootstrap.
 * With PublicShell's deferInitialAuth, this never blocks on a backend call.
 */
/**
 * Public pages never run the Clerk exchange, so `user` stays empty there.
 * Clerk keeps a readable `__client_uat` cookie (a timestamp, "0" when signed out),
 * which tells us a session probably exists without waiting on any network call.
 * It only changes button wording; /app still checks the real session.
 */
export function hasSessionHint(cookieString) {
  try {
    const src = cookieString ?? (typeof document !== "undefined" ? document.cookie : "");
    return src
      .split(";")
      .map((c) => c.trim())
      .some((c) => {
        const [name, value = ""] = c.split("=");
        return (name === "__client_uat" || name.startsWith("__client_uat_")) && value !== "" && value !== "0";
      });
  } catch {
    return false;
  }
}

export function useMarketingAuth() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  const authed = (!loading && !!user) || hasSessionHint();
  const enter = (e) => {
    // Called straight from onClick: the button's test id says which CTA it was.
    const where = e?.currentTarget?.dataset?.testid || "cta";
    if (!authed) track("cta_click", { where });
    navigate(authed ? "/app" : "/sign-up");
  };
  return { authed, enter, loading };
}
