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
import { CLERK_SIGN_IN_PATH, helmSignUpUrl } from "@/lib/helmUrls";
import AuthMarketingHeader from "@/components/marketing/AuthMarketingHeader";
import AuthProductShowcase from "@/components/marketing/AuthProductShowcase";
import trenstonMarkMono from "@/assets/trenston-mark-mono.svg";

export default function Login() {
  const { clerkEnabled, configLoading } = useClerkMode();
  if (configLoading) {
    return <LoadingScreen label="Loading sign-in" />;
  }
  if (!clerkEnabled) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white p-8">
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
      <div className="min-h-screen flex flex-col items-center justify-center bg-white p-8 text-center">
        <LoadingScreen label={sessionError ? "Sign-in problem" : "Finishing sign-in"} />
        {sessionError && (
          <div className="mt-6 max-w-md space-y-4">
            <p className="text-sm text-helm-status-negative">{sessionError}</p>
            <button
              type="button"
              className="text-sm text-mk-navy font-semibold hover:underline"
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
      <div className="relative flex flex-col items-center justify-center bg-white px-6 py-24 md:px-10 min-h-screen">
        <AuthMarketingHeader />
        <div className="w-full max-w-sm flex flex-col items-center text-center">
          <img src={trenstonMarkMono} alt="" width={48} height={48} className="h-12 w-12" draggable={false} />
          <h1 className="mt-6 text-3xl md:text-4xl font-semibold tracking-[-0.035em] text-mk-black">
            Sign in to Trenston
          </h1>
          <p className="mt-2 text-sm text-mk-gray leading-relaxed">
            Sign in with Google, or email. Then open your workspace.
          </p>

          {urlError === "session_retired" && (
            <p className="mt-4 text-sm text-helm-status-warning">That sign-in link has expired. Please sign in again below.</p>
          )}

          {passwordMinLength > 8 && (
            <p className="mt-3 text-xs text-mk-gray leading-relaxed">
              Email passwords need at least {passwordMinLength} characters.
            </p>
          )}

          <div className="mt-8 w-full text-left" data-testid="clerk-sign-in">
            <div id="clerk-captcha" />
            <SignIn
              appearance={clerkAppearance}
              routing="path"
              path={CLERK_SIGN_IN_PATH}
              signUpUrl={signUpPath}
              fallbackRedirectUrl={redirectUrl}
              signUpFallbackRedirectUrl={redirectUrl}
            />
          </div>

          <div className="mt-8 w-full space-y-3 border-t border-mk-line pt-6">
            <p className="text-sm text-mk-gray">
              New here?{" "}
              <Link to="/sign-up" className="text-mk-black font-medium hover:underline">
                Create account
              </Link>
            </p>
            <nav className="flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs text-mk-gray" aria-label="Legal">
              <Link to="/privacy" className="hover:text-mk-black transition-colors">Privacy</Link>
              <Link to="/terms" className="hover:text-mk-black transition-colors">Terms</Link>
              <Link to="/security" className="hover:text-mk-black transition-colors">Security</Link>
              <Link to="/refunds" className="hover:text-mk-black transition-colors">Refunds</Link>
            </nav>
          </div>
        </div>
      </div>

      <AuthProductShowcase />
    </div>
  );
}
