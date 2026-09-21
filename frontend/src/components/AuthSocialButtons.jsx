import { useState } from "react";
import { useSignIn, useSignUp } from "@clerk/clerk-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  CLERK_AFTER_AUTH_PATH,
  CLERK_SIGN_UP_PATH,
  clerkSsoCallbackUrl,
  helmAppUrl,
} from "@/lib/helmUrls";

/** Always www — apex trenston.com 308s to www and can drop OAuth state mid-flow. */
function bounceApexToWww() {
  if (typeof window === "undefined") return false;
  if (window.location.hostname !== "trenston.com") return false;
  window.location.replace(`https://www.trenston.com${window.location.pathname}${window.location.search}`);
  return true;
}

function oauthErrorMessage(err) {
  const code = err?.errors?.[0]?.code || err?.code || "";
  const long = err?.errors?.[0]?.longMessage || err?.errors?.[0]?.message || err?.message || "";
  if (code || long) return [code, long].filter(Boolean).join(": ");
  return `Google sign-in failed. Try again from www.trenston.com${CLERK_SIGN_UP_PATH}.`;
}

/**
 * Google / Microsoft OAuth that returns only to www Trenston SSO callbacks.
 * Clerk's hosted Account Portal (accounts.trenston.com) is Cloudflare-challenged;
 * if OAuth fails, Clerk dumps users there — we avoid that path entirely when we can.
 */
export default function AuthSocialButtons({ mode = "sign-in", className }) {
  const { isLoaded: signInLoaded, signIn } = useSignIn();
  const { isLoaded: signUpLoaded, signUp } = useSignUp();
  const [busy, setBusy] = useState(null);
  const loaded = mode === "sign-up" ? signUpLoaded : signInLoaded;

  const startOAuth = async (strategy) => {
    if (!loaded) return;
    // Bounce apex → www before starting OAuth so redirect_url matches the live host.
    if (bounceApexToWww()) return;
    const redirectUrl = clerkSsoCallbackUrl(mode);
    const redirectUrlComplete = helmAppUrl(CLERK_AFTER_AUTH_PATH);
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
    </div>
  );
}
