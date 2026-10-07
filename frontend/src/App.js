import "@/App.css";
// Patch sonner toast.error before any page imports it (object details crash React).
import "@/lib/notify";
import { Suspense, useEffect } from "react";
import { Analytics } from "@vercel/analytics/react";
import { BrowserRouter, Routes, Route, useLocation, Navigate, Outlet } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import SectionGate from "@/components/SectionGate";
import { CLERK_SIGN_IN_PATH, CLERK_SIGN_UP_PATH } from "@/lib/helmUrls";
import { persistReferralFromSearch } from "@/lib/referral";
import ErrorBoundary from "@/components/ErrorBoundary";
import { lazyWithReload } from "@/lib/chunkReload";
import { friendlyRequestError, shouldReportGlobalError } from "@/lib/friendlyErrors";
import CookieNotice from "@/components/CookieNotice";
import ConfirmHost from "@/components/ConfirmHost";
import Landing from "@/pages/Landing";
import { LoadingScreen } from "@/components/kit";
import { useTheme } from "@/context/ThemeContext";
import palette from "@/design/palette.json";
import { seoForPath, canonicalForPath, DEFAULT_OG_IMAGE } from "@/lib/seoPages";

// Sign-in and the signed-in app load on demand; public pages never need Clerk.
const GatedLayout = lazyWithReload(() => import("@/GatedApp"));
const AppProtectedGate = lazyWithReload(() => import("@/GatedApp").then((m) => ({ default: m.AppProtectedGate })));
const Login = lazyWithReload(() => import("@/pages/Login"));
const SignUpPage = lazyWithReload(() => import("@/pages/SignUp"));
const About = lazyWithReload(() => import("@/pages/About"));
const Features = lazyWithReload(() => import("@/pages/Features"));
const Pricing = lazyWithReload(() => import("@/pages/Pricing"));
const Changelog = lazyWithReload(() => import("@/pages/Changelog"));
const StatusPage = lazyWithReload(() => import("@/pages/Status"));
const PublicIntegrations = lazyWithReload(() => import("@/pages/PublicIntegrations"));
const Help = lazyWithReload(() => import("@/pages/Help"));
const Security = lazyWithReload(() => import("@/pages/Security"));
const Privacy = lazyWithReload(() => import("@/pages/Privacy"));
const Terms = lazyWithReload(() => import("@/pages/Terms"));
const Refunds = lazyWithReload(() => import("@/pages/Refunds"));
const Unsubscribe = lazyWithReload(() => import("@/pages/Unsubscribe"));
const Briefing = lazyWithReload(() => import("@/pages/Briefing"));
const MyDay = lazyWithReload(() => import("@/pages/MyDay"));
const Pipeline = lazyWithReload(() => import("@/pages/Pipeline"));
const Decisions = lazyWithReload(() => import("@/pages/Decisions"));
const Telemetry = lazyWithReload(() => import("@/pages/Telemetry"));
const Financials = lazyWithReload(() => import("@/pages/Financials"));
const FinancialModeling = lazyWithReload(() => import("@/pages/FinancialModeling"));
const Tasks = lazyWithReload(() => import("@/pages/Tasks"));
const Reports = lazyWithReload(() => import("@/pages/Reports"));
const CalendarPage = lazyWithReload(() => import("@/pages/CalendarPage"));
const People = lazyWithReload(() => import("@/pages/People"));
const AskTrenston = lazyWithReload(() => import("@/pages/AskHelm"));
const Members = lazyWithReload(() => import("@/pages/Members"));
const Integrations = lazyWithReload(() => import("@/pages/Integrations"));
const Billing = lazyWithReload(() => import("@/pages/Billing"));
const AccountSettings = lazyWithReload(() => import("@/pages/AccountSettings"));
const AppHelp = lazyWithReload(() => import("@/pages/AppHelp"));
const DepartmentPlaceholder = lazyWithReload(() => import("@/pages/DepartmentPlaceholder"));
const NotFound = lazyWithReload(() => import("@/pages/NotFound"));
const Production = lazyWithReload(() => import("@/pages/Production"));
const Procurement = lazyWithReload(() => import("@/pages/Procurement"));
const Legal = lazyWithReload(() => import("@/pages/Legal"));
const Maintenance = lazyWithReload(() => import("@/pages/Maintenance"));
const HR = lazyWithReload(() => import("@/pages/HR"));


function TrenstonToaster() {
  const { resolvedTheme } = useTheme();
  const light = resolvedTheme === "light";
  return (
    <Toaster
      theme={resolvedTheme}
      position="top-right"
      toastOptions={{
        style: {
          background: light ? "#FFFFFF" : palette.inkCard,
          border: `1px solid ${light ? "#E3E3E0" : "#262626"}`,
          color: light ? "#0A0A0A" : palette.cream,
          borderRadius: "6px",
        },
        classNames: {
          toast: "group",
        },
      }}
    />
  );
}


/** SEO title/meta/canonical — runs for public and auth-gated routes under one BrowserRouter. */
function DocumentSeo() {
  const location = useLocation();
  useEffect(() => {
    persistReferralFromSearch(location.search);
  }, [location.search]);
  useEffect(() => {
    const path = location.pathname.replace(/\/$/, "") || "/";
    const page = seoForPath(path);
    const titles = {
      "/login": "Sign in · Trenston",
      "/sign-up": "Create account · Trenston",
      "/app": "Briefing · Trenston",
      "/app/ask": "Ask Trenston",
      "/app/financials": "Financials · Trenston",
      "/app/billing": "Billing · Trenston",
      "/app/settings": "Settings · Trenston",
      "/app/help": "Help · Trenston",
      "/app/members": "Team & Access · Trenston",
      "/app/integrations": "Integrations · Trenston",
    };
    if (page) {
      document.title = page.title;
    } else if (titles[path] || titles[location.pathname]) {
      document.title = titles[path] || titles[location.pathname];
    } else if (path.startsWith("/app/")) {
      const segment = path.split("/")[2] || "app";
      const label = segment.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      document.title = `${label} · Trenston`;
    } else {
      document.title = "Trenston";
    }

    const canonicalHref = canonicalForPath(path);
    let canonical = document.querySelector('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.setAttribute("rel", "canonical");
      document.head.appendChild(canonical);
    }
    canonical.setAttribute("href", canonicalHref);

    const setMeta = (attr, key, value) => {
      if (!value) return;
      let el = document.querySelector(`meta[${attr}="${key}"]`);
      if (!el) {
        el = document.createElement("meta");
        el.setAttribute(attr, key);
        document.head.appendChild(el);
      }
      el.setAttribute("content", value);
    };

    // Auth / app shells must not compete with marketing URLs in Google.
    const privatePath =
      path.startsWith("/app") ||
      path === "/login" ||
      path === "/sign-up" ||
      path.startsWith("/payment");
    if (privatePath) {
      setMeta("name", "robots", "noindex, nofollow");
    } else {
      const robots = document.querySelector('meta[name="robots"]');
      if (robots) robots.remove();
    }

    if (page) {
      setMeta("name", "description", page.description);
      setMeta("property", "og:title", page.ogTitle || page.title);
      setMeta("property", "og:description", page.ogDescription || page.description);
      setMeta("name", "twitter:title", page.ogTitle || page.title);
      setMeta("name", "twitter:description", page.ogDescription || page.description);
    }
    setMeta("property", "og:url", canonicalHref);
    setMeta("property", "og:image", DEFAULT_OG_IMAGE);
    setMeta("name", "twitter:image", DEFAULT_OG_IMAGE);
  }, [location.pathname]);
  return null;
}


/** Public marketing / legal pages — no ClerkProviderBootstrap, no /api/auth/config wait.
 * Homepage path: App → BrowserRouter → AppRoutes → PublicShell → Landing.
 * ClerkProviderBootstrap wraps only /login, /sign-up, /app/* (ClerkGatedShell).
 */
function PublicShell() {
  return (
    <AuthProvider deferInitialAuth>
      <ErrorBoundary>
        <Suspense fallback={<LoadingScreen label="Loading" />}>
          <Outlet />
        </Suspense>
      </ErrorBoundary>
    </AuthProvider>
  );
}


function AppRoutes() {
  return (
    <Routes>
      {/* Auth-gated first so /login, /sign-up, /app win over public splat */}
      <Route
        element={(
          <Suspense fallback={<LoadingScreen label="Loading" />}>
            <GatedLayout />
          </Suspense>
        )}
      >
        {/* Path routing: SignIn/SignUp own /sso-callback and /continue */}
        <Route
          path={`${CLERK_SIGN_IN_PATH}/*`}
          element={(
            <Suspense fallback={<LoadingScreen label="Loading" />}>
              <Login />
            </Suspense>
          )}
        />
        <Route
          path={`${CLERK_SIGN_UP_PATH}/*`}
          element={(
            <Suspense fallback={<LoadingScreen label="Loading" />}>
              <SignUpPage />
            </Suspense>
          )}
        />
        <Route
          path="/app"
          element={(
            <Suspense fallback={<LoadingScreen label="Loading cockpit" />}>
              <AppProtectedGate />
            </Suspense>
          )}
        >
          <Route index element={<Suspense fallback={<LoadingScreen label="Loading" />}><Briefing /></Suspense>} />
          <Route path="me" element={<Suspense fallback={<LoadingScreen label="Loading" />}><MyDay /></Suspense>} />
          <Route path="sales" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Pipeline /></Suspense>} />
          <Route path="decisions" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Decisions /></Suspense>} />
          <Route path="telemetry" element={<Suspense fallback={<LoadingScreen label="Loading" />}><SectionGate section="telemetry"><Telemetry /></SectionGate></Suspense>} />
          <Route path="financials" element={<Suspense fallback={<LoadingScreen label="Loading" />}><SectionGate section="financials"><Financials /></SectionGate></Suspense>} />
          <Route path="modeling" element={<Suspense fallback={<LoadingScreen label="Loading" />}><SectionGate section="financials"><FinancialModeling /></SectionGate></Suspense>} />
          <Route path="tasks" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Tasks /></Suspense>} />
          <Route path="reports" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Reports /></Suspense>} />
          <Route path="calendar" element={<Suspense fallback={<LoadingScreen label="Loading" />}><CalendarPage /></Suspense>} />
          <Route path="people" element={<Suspense fallback={<LoadingScreen label="Loading" />}><People /></Suspense>} />
          <Route path="ask" element={<Suspense fallback={<LoadingScreen label="Loading" />}><AskTrenston /></Suspense>} />
          <Route path="members" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Members /></Suspense>} />
          <Route path="integrations" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Integrations /></Suspense>} />
          <Route path="billing" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Billing /></Suspense>} />
          <Route path="settings" element={<Suspense fallback={<LoadingScreen label="Loading" />}><AccountSettings /></Suspense>} />
          <Route path="help" element={<Suspense fallback={<LoadingScreen label="Loading" />}><AppHelp /></Suspense>} />
          <Route path="departments/production" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Production /></Suspense>} />
          <Route path="departments/procurement" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Procurement /></Suspense>} />
          <Route path="departments/legal" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Legal /></Suspense>} />
          <Route path="departments/engineering_maintenance" element={<Suspense fallback={<LoadingScreen label="Loading" />}><Maintenance /></Suspense>} />
          <Route path="departments/hr" element={<Suspense fallback={<LoadingScreen label="Loading" />}><HR /></Suspense>} />
          <Route path="departments/sales" element={<Navigate to="/app/sales" replace />} />
          <Route path="departments/accounting_finance" element={<Navigate to="/app/financials" replace />} />
          <Route path="departments/:deptType" element={<Suspense fallback={<LoadingScreen label="Loading" />}><DepartmentPlaceholder /></Suspense>} />
          <Route path="*" element={<Suspense fallback={<LoadingScreen label="Loading" />}><NotFound /></Suspense>} />
        </Route>
      </Route>

      <Route element={<PublicShell />}>
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
        <Route path="/features" element={<Features />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/changelog" element={<Changelog />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/integrations" element={<PublicIntegrations />} />
        <Route path="/help" element={<Help />} />
        <Route path="/security" element={<Security />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/refunds" element={<Refunds />} />
        <Route path="/unsubscribe" element={<Unsubscribe />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}


function App() {
  useEffect(() => {
    const report = (error, message) => {
      if (!shouldReportGlobalError(error, message)) return;
      // Fixed id: a burst of the same failure updates one toast instead of stacking.
      toast.error(friendlyRequestError(error) || "Something went wrong. Please try again", {
        id: "unexpected-error",
      });
    };
    const onError = (event) => report(event.error, event.message);
    const onRejection = (event) => report(event.reason);
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);
  return (
    <div className="App">
      <BrowserRouter>
        <DocumentSeo />
        <AppRoutes />
        <CookieNotice />
        <TrenstonToaster />
        <ConfirmHost />
      </BrowserRouter>
      <Analytics />
    </div>
  );
}

export default App;
