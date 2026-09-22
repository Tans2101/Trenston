import "@/App.css";
// Patch sonner toast.error before any page imports it (object details crash React).
import "@/lib/notify";
import { lazy, Suspense, useEffect } from "react";
import { Analytics } from "@vercel/analytics/react";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import { Toaster, toast } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import ClerkHelmBridge from "@/components/ClerkHelmBridge";
import AppearanceSync from "@/components/AppearanceSync";
import ClerkProviderBootstrap, { useClerkMode } from "@/components/ClerkProviderBootstrap";
import ProtectedRoute from "@/components/ProtectedRoute";
import ProtectedRouteClerk from "@/components/ProtectedRouteClerk";
import SectionGate from "@/components/SectionGate";
import { CLERK_SIGN_IN_PATH, CLERK_SIGN_UP_PATH } from "@/lib/helmUrls";
import { persistReferralFromSearch } from "@/lib/referral";
import ErrorBoundary from "@/components/ErrorBoundary";
import CookieNotice from "@/components/CookieNotice";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import SignUpPage from "@/pages/SignUp";
import { LoadingScreen } from "@/components/kit";
import { useTheme } from "@/context/ThemeContext";
import palette from "@/design/palette.json";
import { seoForPath, canonicalForPath, DEFAULT_OG_IMAGE } from "@/lib/seoPages";

const About = lazy(() => import("@/pages/About"));
const Features = lazy(() => import("@/pages/Features"));
const Pricing = lazy(() => import("@/pages/Pricing"));
const Changelog = lazy(() => import("@/pages/Changelog"));
const StatusPage = lazy(() => import("@/pages/Status"));
const PublicIntegrations = lazy(() => import("@/pages/PublicIntegrations"));
const Help = lazy(() => import("@/pages/Help"));
const Security = lazy(() => import("@/pages/Security"));
const Privacy = lazy(() => import("@/pages/Privacy"));
const Terms = lazy(() => import("@/pages/Terms"));
const Refunds = lazy(() => import("@/pages/Refunds"));
const Unsubscribe = lazy(() => import("@/pages/Unsubscribe"));
const Briefing = lazy(() => import("@/pages/Briefing"));
const MyDay = lazy(() => import("@/pages/MyDay"));
const Pipeline = lazy(() => import("@/pages/Pipeline"));
const Decisions = lazy(() => import("@/pages/Decisions"));
const Telemetry = lazy(() => import("@/pages/Telemetry"));
const Financials = lazy(() => import("@/pages/Financials"));
const Tasks = lazy(() => import("@/pages/Tasks"));
const Reports = lazy(() => import("@/pages/Reports"));
const CalendarPage = lazy(() => import("@/pages/CalendarPage"));
const People = lazy(() => import("@/pages/People"));
const AskTrenston = lazy(() => import("@/pages/AskHelm"));
const Members = lazy(() => import("@/pages/Members"));
const Integrations = lazy(() => import("@/pages/Integrations"));
const Billing = lazy(() => import("@/pages/Billing"));
const AccountSettings = lazy(() => import("@/pages/AccountSettings"));
const AppHelp = lazy(() => import("@/pages/AppHelp"));
const DepartmentPlaceholder = lazy(() => import("@/pages/DepartmentPlaceholder"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const Production = lazy(() => import("@/pages/Production"));
const Procurement = lazy(() => import("@/pages/Procurement"));
const Legal = lazy(() => import("@/pages/Legal"));
const Maintenance = lazy(() => import("@/pages/Maintenance"));
const HR = lazy(() => import("@/pages/HR"));


function TrenstonToaster() {
  const { resolvedTheme } = useTheme();
  const light = resolvedTheme === "light";
  return (
    <Toaster
      theme={resolvedTheme}
      position="top-right"
      toastOptions={{
        style: {
          background: light ? palette.cream : palette.inkCard,
          border: `1px solid ${light ? palette.navy : palette.cream}29`,
          color: light ? palette.navy : palette.cream,
        },
        classNames: {
          toast: "group",
        },
      }}
    />
  );
}


function AppRouter() {
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
  const { clerkEnabled, configLoading } = useClerkMode();
  const Protected = configLoading
    ? () => <LoadingScreen label="Loading cockpit" />
    : clerkEnabled
      ? ProtectedRouteClerk
      : ProtectedRoute;

  if (location.hash?.includes("session_id=")) {
    return <Navigate to="/login?error=session_retired" replace />;
  }
  return (
    <Suspense fallback={<LoadingScreen label="Loading" />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
        <Route path="/features" element={<Features />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/changelog" element={<Changelog />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/integrations" element={<PublicIntegrations />} />
        <Route path="/help" element={<Help />} />
        <Route path="/security" element={<Security />} />
        {/* Path routing: SignIn/SignUp own /sso-callback and /continue (do not steal with AuthenticateWithRedirectCallback) */}
        <Route path={`${CLERK_SIGN_IN_PATH}/*`} element={<Login />} />
        <Route path={`${CLERK_SIGN_UP_PATH}/*`} element={<SignUpPage />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/refunds" element={<Refunds />} />
        <Route path="/unsubscribe" element={<Unsubscribe />} />
        <Route path="/app" element={<Protected />}>
          <Route index element={<Briefing />} />
          <Route path="me" element={<MyDay />} />
          <Route path="sales" element={<Pipeline />} />
          <Route path="decisions" element={<Decisions />} />
          <Route path="telemetry" element={<SectionGate section="telemetry"><Telemetry /></SectionGate>} />
          <Route path="financials" element={<SectionGate section="financials"><Financials /></SectionGate>} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="reports" element={<Reports />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="people" element={<People />} />
          <Route path="ask" element={<AskTrenston />} />
          <Route path="members" element={<Members />} />
          <Route path="integrations" element={<Integrations />} />
          <Route path="billing" element={<Billing />} />
          <Route path="settings" element={<AccountSettings />} />
          <Route path="help" element={<AppHelp />} />
          <Route path="departments/production" element={<Production />} />
          <Route path="departments/procurement" element={<Procurement />} />
          <Route path="departments/legal" element={<Legal />} />
          <Route path="departments/engineering_maintenance" element={<Maintenance />} />
          <Route path="departments/hr" element={<HR />} />
          <Route path="departments/sales" element={<Navigate to="/app/sales" replace />} />
          <Route path="departments/accounting_finance" element={<Navigate to="/app/financials" replace />} />
          <Route path="departments/:deptType" element={<DepartmentPlaceholder />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}

function ClerkAuthShell() {
  const { signOut } = useClerk();
  return (
    <AuthProvider onLogoutExtra={() => signOut()} deferInitialAuth>
      {/* Toaster stays outside ErrorBoundary — a bad toast must not blank the app. */}
      <ErrorBoundary>
        <BrowserRouter>
          <AppearanceSync />
          <ClerkHelmBridge />
          <AppRouter />
          <CookieNotice />
        </BrowserRouter>
      </ErrorBoundary>
      <TrenstonToaster />
    </AuthProvider>
  );
}

function TrenstonAppShell() {
  return (
    <AuthProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <AppearanceSync />
          <AppRouter />
          <CookieNotice />
        </BrowserRouter>
      </ErrorBoundary>
      <TrenstonToaster />
    </AuthProvider>
  );
}

function AuthShell() {
  const { clerkEnabled, configLoading } = useClerkMode();
  if (configLoading) {
    return <LoadingScreen label="Loading" />;
  }
  return clerkEnabled ? <ClerkAuthShell /> : <TrenstonAppShell />;
}

function App() {
  useEffect(() => {
    const onError = () => {
      toast.error("Something went wrong. Please try again");
    };
    const onRejection = () => {
      toast.error("Something went wrong. Please try again");
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);
  return (
    <div className="App">
      <ClerkProviderBootstrap>
        <AuthShell />
      </ClerkProviderBootstrap>
      <Analytics />
    </div>
  );
}

export default App;
