import { useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { SignIn, useAuth as useClerkAuth, useSession, useClerk } from "@clerk/clerk-react";
import { useAuth } from "@/context/AuthContext";
import { useClerkMode } from "@/components/ClerkProviderBootstrap";
import { clerkAppearance } from "@/lib/clerkTheme";
import { LoadingScreen } from "@/components/kit";
import ClerkLoadError from "@/components/ClerkLoadError";
import { useClerkReady } from "@/hooks/useClerkReady";
import { clerkSessionComplete, CLERK_AUTH_OPTS } from "@/lib/clerkSession";
import { clerkAfterAuthRedirect } from "@/lib/clerkRedirect";
import { helmSignUpUrl } from "@/lib/helmUrls";
import AuthMarketingHeader from "@/components/marketing/AuthMarketingHeader";
import AuthProductShowcase from "@/components/marketing/AuthProductShowcase";
import TrenstonMark from "@/components/HelmMark";

export default function Login() {
  const { clerkEnabled, configLoading } = useClerkMode();
  if (configLoading) {
    return <LoadingScreen label="Loading sign-in" />;
  }
  if (!clerkEnabled) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-helm-cream p-8">
        <p className="text-sm text-helm-status-negative">Sign-in is not available. Clerk is not configured on this deployment.</p>
      </div>
    );
  }
  return <LoginClerk />;
}

function LoginClerk() {
  const { postAuthUrl, helmCanonicalOrigin, clerkMultiDomain, passwordMinLength } = useClerkMode();
  const redirectUrl = clerkAfterAuthRedirect({ clerkMultiDomain, postAuthUrl });
  const signUpPath = helmSignUpUrl(helmCanonicalOrigin);
  const [searchParams] = useSearchParams();
  const urlError = searchParams.get("error");
  const { user, loading, sessionError, clearSessionError } = useAuth();
  const { isSignedIn, userId, sessionId, sessionStatus } = useClerkAuth(CLERK_AUTH_OPTS);
  const { session } = useSession();
  const { signOut } = useClerk();
  const navigate = useNavigate();
  const { clerkReady, clerkTimedOut } = useClerkReady();

  const clerkComplete = clerkSessionComplete({ isSignedIn, userId, sessionId, session, sessionStatus });

  useEffect(() => {
    if (!loading && user) navigate("/app", { replace: true });
  }, [user, loading, navigate]);

  useEffect(() => {
    if (!clerkReady || user) return;
    if (clerkComplete) navigate("/app", { replace: true });
  }, [clerkReady, clerkComplete, user, navigate]);

  if (clerkTimedOut) {
    return <ClerkLoadError />;
  }

  if (!clerkReady || loading) {
    return <LoadingScreen label="Loading sign-in" />;
  }

  if (clerkComplete && !user) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-helm-cream p-8 text-center">
        <LoadingScreen label={sessionError ? "Sign-in problem" : "Finishing sign-in"} />
        {sessionError && (
          <div className="mt-6 max-w-md space-y-4">
            <p className="text-sm text-helm-status-negative">{sessionError}</p>
            <button
              type="button"
              className="text-sm text-helm-gold hover:underline"
              onClick={async () => {
                clearSessionError();
                await signOut();
                window.location.href = "/login";
              }}
            >
              Sign out and try again
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Auth form — light panel */}
      <div className="relative flex flex-col items-center justify-center bg-helm-cream px-6 py-24 md:px-10 min-h-screen">
        <AuthMarketingHeader />
        <div className="w-full max-w-sm flex flex-col items-center text-center">
          <TrenstonMark size={48} className="rounded-md" />
          <h1 className="mt-6 font-display text-2xl md:text-3xl font-semibold tracking-tight text-helm-navy">
            Sign in to Trenston
          </h1>
          <p className="mt-2 text-sm text-helm-slate leading-relaxed">
            Sign in with Google, or email. Then open your workspace.
          </p>

          {urlError === "session_retired" && (
            <p className="mt-4 text-sm text-helm-status-warning">That sign-in link has expired. Please sign in again below.</p>
          )}

          {passwordMinLength > 8 && (
            <p className="mt-3 text-xs text-helm-slate leading-relaxed">
              Email passwords need at least {passwordMinLength} characters. Google sign-in skips this.
            </p>
          )}

          <div className="mt-8 w-full text-left" data-testid="clerk-sign-in">
            <SignIn
              appearance={clerkAppearance}
              routing="path"
              path="/login"
              signUpUrl={signUpPath}
              oauthFlow="redirect"
              forceRedirectUrl={redirectUrl}
              fallbackRedirectUrl={redirectUrl}
            />
          </div>

          <div className="mt-8 w-full space-y-3 border-t border-helm-navy/10 pt-6">
            <p className="text-sm text-helm-slate">
              New here?{" "}
              <Link to="/sign-up" className="text-helm-navy font-medium hover:underline">
                Create account
              </Link>
            </p>
            <nav className="flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs text-helm-slate" aria-label="Legal">
              <Link to="/privacy" className="hover:text-helm-navy transition-colors">Privacy</Link>
              <Link to="/terms" className="hover:text-helm-navy transition-colors">Terms</Link>
              <Link to="/security" className="hover:text-helm-navy transition-colors">Security</Link>
              <Link to="/refunds" className="hover:text-helm-navy transition-colors">Refunds</Link>
            </nav>
          </div>
        </div>
      </div>

      <AuthProductShowcase />
    </div>
  );
}
