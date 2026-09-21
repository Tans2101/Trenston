import { useState } from "react";
import { useSignIn, useSignUp } from "@clerk/clerk-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function oauthErrorMessage(err) {
  const code = err?.errors?.[0]?.code || err?.code || "";
  const long = err?.errors?.[0]?.longMessage || err?.errors?.[0]?.message || err?.message || "";
  if (code || long) return [code, long].filter(Boolean).join(": ");
  return "Google sign-in failed. Allow popups, or try again.";
}

/**
 * Google / Microsoft OAuth that always returns to www Trenston SSO callbacks —
 * never Clerk Account Portal (accounts.trenston.com), which Cloudflare challenges.
 */
export default function AuthSocialButtons({ mode = "sign-in", className }) {
  const { isLoaded: signInLoaded, signIn } = useSignIn();
  const { isLoaded: signUpLoaded, signUp } = useSignUp();
  const [busy, setBusy] = useState(null);
  const loaded = mode === "sign-up" ? signUpLoaded : signInLoaded;

  const startOAuth = async (strategy) => {
    if (!loaded) return;
    const origin = window.location.origin.replace(/\/$/, "");
    const basePath = mode === "sign-up" ? "/sign-up" : "/login";
    const redirectUrl = `${origin}${basePath}/sso-callback`;
    const redirectUrlComplete = `${origin}/app`;
    setBusy(strategy);
    try {
      if (mode === "sign-up") {
        if (!signUp) throw new Error("Sign-up not ready");
        await signUp.authenticateWithRedirect({
          strategy,
          redirectUrl,
          redirectUrlComplete,
        });
      } else {
        if (!signIn) throw new Error("Sign-in not ready");
        await signIn.authenticateWithRedirect({
          strategy,
          redirectUrl,
          redirectUrlComplete,
        });
      }
    } catch (err) {
      console.error("OAuth start failed", err);
      toast.error(oauthErrorMessage(err));
      setBusy(null);
    }
  };

  return (
    <div className={cn("w-full space-y-2 mb-4", className)} data-testid="auth-social-buttons">
      <button
        type="button"
        disabled={!loaded || Boolean(busy)}
        onClick={() => startOAuth("oauth_google")}
        className="w-full h-11 inline-flex items-center justify-center gap-2 rounded-full bg-helm-navy text-helm-cream text-sm font-medium hover:bg-helm-navy/90 disabled:opacity-50"
        data-testid="oauth-google-btn"
      >
        {busy === "oauth_google" ? "Redirecting…" : "Continue with Google"}
      </button>
      <button
        type="button"
        disabled={!loaded || Boolean(busy)}
        onClick={() => startOAuth("oauth_microsoft")}
        className="w-full h-11 inline-flex items-center justify-center gap-2 rounded-full bg-white text-helm-navy text-sm font-medium border border-helm-navy/20 hover:bg-helm-navy/[0.04] disabled:opacity-50"
        data-testid="oauth-microsoft-btn"
      >
        {busy === "oauth_microsoft" ? "Redirecting…" : "Continue with Microsoft"}
      </button>
      <p className="text-[11px] text-center text-helm-slate pt-1">
        Uses a full-page Google redirect on this site (not accounts.trenston.com).
      </p>
    </div>
  );
}
