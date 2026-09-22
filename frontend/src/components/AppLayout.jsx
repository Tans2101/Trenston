import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  LayoutDashboard, GitBranch, Activity, KanbanSquare,
  FileText, Calendar, Contact, MessageSquareText,
  Menu, X, UsersRound, ChevronDown, Check, Plus, Sun, Moon, Monitor, Wallet, Search, Bell,
  HelpCircle, Shield, Scale, Settings, Plug, Download, ScrollText,
  Trash2, Building2, CreditCard, ShieldCheck, AlertTriangle, FolderOpen,
  Info, LayoutGrid, Receipt,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { useFetch } from "@/hooks/useFetch";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { useDepartmentsQuery } from "@/hooks/useDepartmentsQuery";
import { api } from "@/lib/api";
import { toast } from "sonner";
import SubscriptionGate from "@/components/SubscriptionGate";
import CompanySetup from "@/pages/CompanySetup";
import { helmPlanLabel, helmWorkspacePlanLabel, helmHasFullAccess, helmIsPaidPlan } from "@/lib/helmPlan";
import { departmentIcon } from "@/lib/departmentIcons";
import { cn } from "@/lib/utils";
import { LoadingScreen } from "@/components/kit";
import { consumeReferralCode, withReferralPayload } from "@/lib/referral";
import { departmentPath } from "@/lib/departmentRoutes";
import { canManageBilling } from "@/lib/access";
import { prefetchRouteHandlers } from "@/lib/prefetchRoute";
import ProfileDropdown from "@/components/kokonutui/profile-dropdown";
import ActionSearchBar from "@/components/kokonutui/action-search-bar";
import SmoothTab, { SmoothTabItem } from "@/components/kokonutui/smooth-tab";
import TrenstonMark from "@/components/HelmMark";
import { SITE_SEARCH_ACTIONS } from "@/lib/siteSearchActions";

const NAV = [
  { to: "/app/me", label: "My Day", icon: Sun, id: "myday", end: true },
  { to: "/app", label: "Briefing", icon: LayoutDashboard, id: "briefing", end: true },
  { to: "/app/decisions", label: "Decisions", icon: GitBranch, id: "decisions" },
  { to: "/app/telemetry", label: "Telemetry", icon: Activity, id: "telemetry", section: "telemetry" },
  { to: "/app/financials", label: "Financials", icon: Wallet, id: "financials", section: "financials" },
  { to: "/app/tasks", label: "Tasks", icon: KanbanSquare, id: "tasks" },
  { to: "/app/reports", label: "Reports", icon: FileText, id: "reports" },
  { to: "/app/calendar", label: "Calendar", icon: Calendar, id: "calendar" },
  { to: "/app/people", label: "People", icon: Contact, id: "people" },
  { to: "/app/ask", label: "Ask Trenston", icon: MessageSquareText, id: "ask" },
  { to: "/app/members", label: "Team & Access", icon: UsersRound, id: "members", perm: "members:invite" },
];

function navItemVisible(item, user) {
  // Pack-only perms (e.g. members:invite) — unchanged shallow check.
  if (item.perm && !(user?.perms || []).includes(item.perm)) return false;
  // Grant-aware sections (e.g. telemetry, financials) — includes pack holders via /auth/me.
  if (item.section && !(user?.granted_sections || []).includes(item.section)) return false;
  return true;
}

function departmentNavVisible(dept) {
  if (!dept?.visible_in_nav) return false;
  // Financials is gated via the main NAV entry + SectionGate; hide the dept duplicate.
  if (dept.type === "accounting_finance") return false;
  return true;
}

function departmentNavTo(type) {
  return departmentPath(type);
}

const SITE_SEARCH_ICONS = {
  about: Info,
  features: LayoutGrid,
  help: HelpCircle,
  "security-page": Shield,
  terms: FileText,
  privacy: Scale,
  refunds: Receipt,
};

function pathMatches(to, pathname, end) {
  if (end) return pathname === to;
  return pathname === to || pathname.startsWith(`${to}/`);
}

/** Digits 1–9 then 0 for the first 10 visible main-nav rows; null beyond that. */
function navShortcutLabel(index) {
  if (index < 0 || index > 9) return null;
  return index === 9 ? "0" : String(index + 1);
}

function isTypingTarget(el) {
  if (!el || !(el instanceof Element)) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return Boolean(el.closest("[contenteditable='true'], [contenteditable='']"));
}

function SidebarThemeControl() {
  const { user, setUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const options = [
    { id: "light", label: "Light", icon: Sun },
    { id: "dark", label: "Dark", icon: Moon },
    { id: "system", label: "Auto", icon: Monitor },
  ];

  const apply = (id) => {
    setTheme(id);
    if (user && setUser) setUser({ ...user, appearance: id });
  };

  return (
    <div
      role="group"
      aria-label="Color theme"
      data-testid="sidebar-theme-control"
      className="cir-rail__theme"
    >
      {options.map(({ id, label, icon: Icon }) => {
        const active = theme === id;
        return (
          <button
            key={id}
            type="button"
            data-testid={`sidebar-theme-${id === "system" ? "auto" : id}`}
            aria-pressed={active}
            onClick={() => apply(id)}
            className="cir-rail__theme-btn"
          >
            <Icon className="h-3 w-3 shrink-0" />
            <span className="truncate">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

function WorkspaceSwitcher({ onNavigate, billingEnforced }) {
  const { user } = useAuth();
  const { data } = useFetch("/workspaces");
  const [open, setOpen] = useState(false);
  const list = data?.workspaces || [];
  const active = list.find((w) => w.active) || list[0];

  const switchWs = async (id) => {
    if (id === active?.workspace_id) { setOpen(false); return; }
    try {
      await api.post("/workspaces/switch", { workspace_id: id });
      window.location.href = "/app";
    } catch (e) { toast.error("Could not switch workspace"); }
  };

  const create = async () => {
    const name = window.prompt("Name your new company workspace");
    if (!name) return;
    try {
      if (!user?.age_confirmed) {
        const ok = window.confirm(
          "Confirm you are 18 or older (or using Trenston under a parent/guardian) to create a company.",
        );
        if (!ok) return;
        await api.patch("/account/age-confirmation", { confirmed: true });
      }
      await api.post("/workspaces", withReferralPayload({ name }));
      consumeReferralCode();
      window.location.href = "/app";
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not create workspace"); }
  };

  if (!active) return null;
  return (
    <div className="relative px-1 pt-2">
      <button data-testid="workspace-switcher" onClick={() => setOpen((o) => !o)}
        className="inline-flex max-w-full items-center gap-2 rounded-full px-3 py-2 text-left transition-colors hover:bg-helm-fg/[0.04]">
        <div className="w-6 h-6 rounded-full bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center text-[11px] text-helm-gold font-mono shrink-0">
          {active.name?.[0]?.toUpperCase() || "K"}
        </div>
        <div className="min-w-0 text-left">
          <p className="text-xs text-helm-fg truncate">{active.name}</p>
          <p className="text-[10px] text-helm-muted uppercase font-mono tracking-wide">{active.role} · {helmWorkspacePlanLabel(active.plan, billingEnforced)}</p>
        </div>
        <ChevronDown className={cn("w-4 h-4 text-helm-muted shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute left-1 right-1 mt-1 z-50 rounded-xl border border-helm-line bg-helm-card shadow-xl overflow-hidden">
          {list.map((w) => (
            <button key={w.workspace_id} onClick={() => switchWs(w.workspace_id)}
              data-testid={`ws-option-${w.workspace_id}`}
              className="w-full flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-helm-fg/5">
              <span className="flex-1 min-w-0 text-xs text-helm-fg truncate">{w.name}</span>
              {w.active && <Check className="w-3.5 h-3.5 text-helm-gold" />}
            </button>
          ))}
          <button onClick={create} data-testid="ws-create-btn"
            className="w-full flex items-center gap-2 px-3 py-2 text-left border-t border-helm-line transition-colors hover:bg-helm-fg/5 text-helm-gold">
            <Plus className="w-3.5 h-3.5" /><span className="text-xs">New company</span>
          </button>
        </div>
      )}
    </div>
  );
}

const QUICK_ACTION_IDS = ["myday", "briefing", "calendar", "ask", "reports"];

function SidebarPromoCard({ billingEnforced, isPaid, canBilling, onNavigate }) {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return window.sessionStorage.getItem("helm_sidebar_promo_dismissed") === "1";
    } catch {
      return false;
    }
  });
  const navigate = useNavigate();

  if (dismissed) return null;

  const pitch = !isPaid && billingEnforced && canBilling
    ? {
        title: "Upgrade your plan",
        body: "More seats, higher Ask Trenston limits, and accounting sync.",
        cta: "See plans",
        to: "/app/billing",
        testId: "sidebar-promo-upgrade",
      }
    : {
        title: "Connect your tools",
        body: "Link Google, QuickBooks, or your bank so the briefing stays live.",
        cta: "Integrations",
        to: "/app/integrations",
        testId: "sidebar-promo-integrations",
      };

  const dismiss = () => {
    try {
      window.sessionStorage.setItem("helm_sidebar_promo_dismissed", "1");
    } catch {
      /* ignore */
    }
    setDismissed(true);
  };

  return (
    <div
      className="relative rounded-xl border border-helm-gold/35 bg-helm-gold/12 p-3"
      data-testid={pitch.testId}
    >
      <button
        type="button"
        aria-label="Dismiss"
        onClick={dismiss}
        className="absolute top-2 right-2 text-helm-muted hover:text-helm-fg p-0.5"
      >
        <X className="w-3.5 h-3.5" />
      </button>
      <p className="text-xs font-medium text-helm-fg pr-5 leading-snug">{pitch.title}</p>
      <p className="mt-1 text-[11px] text-helm-muted leading-relaxed">{pitch.body}</p>
      <button
        type="button"
        onClick={() => {
          navigate(pitch.to);
          onNavigate?.();
        }}
        className="mt-2 text-[11px] font-medium text-helm-gold hover:text-helm-gold-hover"
      >
        {pitch.cta} →
      </button>
    </div>
  );
}

function SidebarContent({ onNavigate, billingEnforced, enableNavShortcuts = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: company } = useCompanyQuery();
  const { data: deptData } = useDepartmentsQuery();
  const isPro = helmHasFullAccess(company?.plan, billingEnforced);
  const isPaid = helmIsPaidPlan(company?.plan, billingEnforced);
  const mainNav = useMemo(() => NAV.filter((item) => navItemVisible(item, user)), [user]);
  const deptNav = (deptData?.departments || []).filter((d) => departmentNavVisible(d));
  const canBilling = canManageBilling(user);

  // Prefer a department match when on a dept route so the main track stays quiet.
  const activeDeptId = deptNav.find((d) => pathMatches(departmentNavTo(d.type), location.pathname, false))?.type || null;
  const activeMainId = activeDeptId
    ? null
    : (mainNav.find((item) => pathMatches(item.to, location.pathname, item.end))?.id || null);

  const navBtn = ({ isActive }) =>
    cn("cir-rail__link group relative", isActive && "cir-rail__link--active");

  useEffect(() => {
    if (!enableNavShortcuts) return undefined;
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key < "0" || e.key > "9") return;
      if (isTypingTarget(document.activeElement)) return;
      const index = e.key === "0" ? 9 : Number(e.key) - 1;
      const item = mainNav[index];
      if (!item) return;
      e.preventDefault();
      navigate(item.to);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enableNavShortcuts, mainNav, navigate]);

  return (
    <div className="cir-rail" data-testid="app-sidebar-rail">
      <div className="flex items-center gap-2.5 px-3 pt-2 pb-2" data-testid="sidebar-brand">
        <TrenstonMark size={28} className="rounded-md" />
        <span className="text-sm font-semibold tracking-tight" style={{ color: "var(--cir-ink)" }}>
          Trenston
        </span>
      </div>

      <WorkspaceSwitcher onNavigate={onNavigate} billingEnforced={billingEnforced} />

      <nav className="flex-1 overflow-y-auto py-2" aria-label="App">
        <SmoothTab
          orientation="vertical"
          variant="pill"
          activeId={activeDeptId ? `dept-${activeDeptId}` : activeMainId}
          className="cir-rail__track"
          indicatorClassName="cir-rail__indicator"
        >
          {mainNav.map((item, index) => {
            const shortcut = navShortcutLabel(index);
            return (
              <SmoothTabItem key={item.id} id={item.id}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  {...prefetchRouteHandlers(item.to)}
                  data-testid={`sidebar-nav-${item.id}`}
                  className={navBtn}
                >
                  {({ isActive }) => (
                    <>
                      <item.icon className={cn("cir-rail__icon w-[18px] h-[18px] shrink-0")} />
                      <span className="cir-rail__label truncate flex-1 text-left">{item.label}</span>
                      {shortcut ? (
                        <span
                          className="cir-rail__shortcut ml-auto font-mono text-[10px] tabular-nums shrink-0"
                          aria-hidden
                        >
                          {shortcut}
                        </span>
                      ) : null}
                    </>
                  )}
                </NavLink>
              </SmoothTabItem>
            );
          })}
          {deptNav.length > 0 ? (
            <p className="cir-rail__section">Departments</p>
          ) : null}
          {deptNav.map((dept) => {
            const Icon = departmentIcon(dept.icon);
            const to = departmentNavTo(dept.type);
            return (
              <SmoothTabItem key={dept.type} id={`dept-${dept.type}`}>
                <NavLink
                  to={to}
                  onClick={onNavigate}
                  {...prefetchRouteHandlers(to)}
                  data-testid={`sidebar-dept-${dept.type}`}
                  className={navBtn}
                >
                  {() => (
                    <>
                      <Icon className="cir-rail__icon w-[18px] h-[18px] shrink-0" />
                      <span className="cir-rail__label truncate">{dept.name}</span>
                    </>
                  )}
                </NavLink>
              </SmoothTabItem>
            );
          })}
        </SmoothTab>
      </nav>

      <div className="px-1 pb-2 space-y-2">
        <SidebarPromoCard
          billingEnforced={billingEnforced}
          isPaid={isPaid}
          canBilling={canBilling}
          onNavigate={onNavigate}
        />
        <SidebarThemeControl />
        <ProfileDropdown
          name={user?.name || "CEO"}
          picture={user?.picture}
          planLabel={helmPlanLabel(company?.plan, isPro, billingEnforced)}
          showBilling={canBilling}
          onBilling={() => { navigate("/app/billing"); onNavigate?.(); }}
          onIntegrations={() => { navigate("/app/integrations"); onNavigate?.(); }}
          onSettings={() => { navigate("/app/settings"); onNavigate?.(); }}
          onHelp={() => { navigate("/app/help"); onNavigate?.(); }}
          onLogout={logout}
        />
      </div>
    </div>
  );
}

function useQuickNavActions() {
  const { user } = useAuth();
  const { data: deptData } = useDepartmentsQuery();
  const isOwner = user?.role === "owner" || user?.pack === "owner";
  const canBilling = canManageBilling(user);
  const canExportActivity = isOwner || (user?.perms || []).includes("members:manage");

  return useMemo(() => {
    const navActions = NAV.filter((item) => navItemVisible(item, user)).map((item) => {
      const Icon = item.icon;
      return {
        id: item.id,
        label: item.label,
        to: item.to,
        description: "App",
        icon: <Icon className="w-4 h-4" />,
      };
    });
    const deptActions = (deptData?.departments || [])
      .filter((d) => departmentNavVisible(d))
      .map((dept) => {
        const Icon = departmentIcon(dept.icon);
        return {
          id: `dept-${dept.type}`,
          label: dept.name,
          to: departmentNavTo(dept.type),
          description: "Department",
          keywords: ["department", dept.type],
          icon: <Icon className="w-4 h-4" />,
        };
      });

    const settingsActions = [
      {
        id: "settings",
        label: "Settings",
        to: "/app/settings",
        description: "Settings",
        keywords: ["account", "preferences"],
        icon: <Settings className="w-4 h-4" />,
      },
      {
        id: "settings-appearance",
        label: "Appearance",
        to: "/app/settings#appearance",
        description: "Settings",
        keywords: ["theme", "dark", "light", "system"],
        icon: <Sun className="w-4 h-4" />,
      },
      {
        id: "settings-security",
        label: "Security overview",
        to: "/app/settings#settings-security",
        description: "Settings",
        keywords: ["encryption", "privacy", "protect"],
        icon: <ShieldCheck className="w-4 h-4" />,
      },
      {
        id: "settings-departments",
        label: "Departments",
        to: "/app/settings#manage-departments",
        description: "Settings",
        keywords: ["team", "lanes", "manage departments"],
        icon: <Building2 className="w-4 h-4" />,
      },
      {
        id: "settings-documents",
        label: "Documents",
        to: "/app/settings#documents-library",
        description: "Settings",
        keywords: ["files", "pdf", "library", "uploads"],
        icon: <FolderOpen className="w-4 h-4" />,
      },
      {
        id: "settings-integrations",
        label: "Integrations",
        to: "/app/integrations",
        description: "Settings",
        keywords: ["google", "quickbooks", "calendar", "connect", "oauth"],
        icon: <Plug className="w-4 h-4" />,
      },
      {
        id: "settings-help",
        label: "Help",
        to: "/app/help",
        description: "Settings",
        keywords: ["howto", "guide", "faq", "onboarding", "walkthrough", "glossary"],
        icon: <HelpCircle className="w-4 h-4" />,
      },
      {
        id: "settings-export",
        label: "Export data",
        to: "/app/settings#export-data",
        description: "Settings",
        keywords: ["download", "backup", "json"],
        icon: <Download className="w-4 h-4" />,
      },
      {
        id: "settings-delete-account",
        label: "Delete account",
        to: "/app/settings#delete-account",
        description: "Settings",
        keywords: ["remove", "close account"],
        icon: <Trash2 className="w-4 h-4" />,
      },
    ];

    if (canExportActivity) {
      settingsActions.push({
        id: "settings-activity",
        label: "Export activity log",
        to: "/app/settings#export-activity",
        description: "Settings",
        keywords: ["audit", "csv", "activity"],
        icon: <ScrollText className="w-4 h-4" />,
      });
    }
    if (isOwner) {
      settingsActions.push({
        id: "settings-delete-workspace",
        label: "Delete workspace",
        to: "/app/settings#delete-workspace",
        description: "Settings",
        keywords: ["company", "remove workspace"],
        icon: <AlertTriangle className="w-4 h-4" />,
      });
    }
    if (canBilling) {
      settingsActions.push({
        id: "billing",
        label: "Billing",
        to: "/app/billing",
        description: "Account",
        keywords: ["plan", "subscription", "payment"],
        icon: <CreditCard className="w-4 h-4" />,
      });
    }

    const siteActions = SITE_SEARCH_ACTIONS.map((item) => {
      const Icon = SITE_SEARCH_ICONS[item.id] || HelpCircle;
      return {
        ...item,
        icon: <Icon className="w-4 h-4" />,
      };
    });

    const byId = new Map(navActions.map((a) => [a.id, a]));
    const quickActions = QUICK_ACTION_IDS.map((id) => byId.get(id)).filter(Boolean);

    return {
      actions: [...navActions, ...deptActions, ...settingsActions, ...siteActions],
      quickActions,
      departmentActions: deptActions,
    };
  }, [user, deptData, isOwner, canBilling, canExportActivity]);
}

function QuickNavPalette({ open, onOpenChange, variant = "dialog", searchRef, enableShortcut = true }) {
  const navigate = useNavigate();
  const { actions, quickActions, departmentActions } = useQuickNavActions();

  return (
    <ActionSearchBar
      ref={searchRef}
      variant={variant}
      open={open}
      onOpenChange={onOpenChange}
      actions={actions}
      quickActions={quickActions}
      departmentActions={departmentActions}
      enableShortcut={enableShortcut}
      onSelect={(action) => {
        if (!action?.to) return;
        if (action.to.startsWith("mailto:")) {
          window.location.href = action.to;
          return;
        }
        // Public marketing URLs leave the cockpit shell so the address bar
        // actually becomes /features, /about, etc. (not an in-app overlay).
        if (!action.to.startsWith("/app")) {
          window.location.assign(action.to);
          return;
        }
        navigate(action.to);
        // Re-trigger hash scroll when already on settings with a new hash.
        if (action.to.includes("#")) {
          const hash = action.to.split("#")[1];
          window.setTimeout(() => {
            document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 120);
        }
      }}
    />
  );
}

export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const desktopSearchRef = useRef(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { data: billing } = useFetch("/billing/plans");
  const { data: company, loading: companyLoading } = useCompanyQuery();
  const billingEnforced = billing?.billing_enforced === true;
  const pastDue = billingEnforced && billing?.subscription_status === "past_due";
  const trialing = billing?.subscription_status === "trialing";
  const isPro = helmHasFullAccess(company?.plan, billingEnforced);
  const onBilling = location.pathname.startsWith("/app/billing");
  const canBilling = canManageBilling(user);
  const needsCompanySetup = company?.role === "owner" && company?.company_setup_done === false;
  const planLabel = helmPlanLabel(company?.plan, isPro, billingEnforced);
  const trialDaysLeft = (() => {
    if (!trialing) return null;
    const end = billing?.trial_ends_at || billing?.current_period_end;
    if (!end) return 7;
    const ms = new Date(end).getTime() - Date.now();
    return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
  })();
  const planBadge = trialing && trialDaysLeft != null
    ? `${planLabel} trial — ${trialDaysLeft} day${trialDaysLeft === 1 ? "" : "s"} left`
    : planLabel;

  const openSearch = () => setSearchOpen(true);

  // ⌘K: desktop focuses the top-bar pill; mobile opens the dialog.
  useEffect(() => {
    const onKey = (e) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "k") return;
      e.preventDefault();
      if (window.matchMedia("(min-width: 1024px)").matches) {
        desktopSearchRef.current?.focus();
      } else {
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (companyLoading && !company) {
    return <LoadingScreen label="Loading Trenston" />;
  }

  if (needsCompanySetup) {
    return <CompanySetup company={company} />;
  }

  return (
    <div className="app-shell min-h-screen">
      {pastDue && (
        <div className="lg:pl-[240px] bg-helm-status-warning/12 border-b border-helm-status-warning/35 px-5 py-2.5 text-center text-sm text-helm-fg" data-testid="global-past-due-banner">
          Payment past due: <button type="button" onClick={() => window.location.href = "/app/billing"} className="underline font-medium text-helm-status-warning">update billing</button> to keep Trenston access.
        </div>
      )}
      {/* Desktop nav rail — cir-tabs pill shell */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-[240px] flex-col z-40">
        <SidebarContent billingEnforced={billingEnforced} enableNavShortcuts />
      </aside>

      {/* Mobile top bar */}
      <div className="lg:hidden sticky top-0 z-50 flex items-center justify-between px-4 h-14 bg-helm-bg/95 backdrop-blur-md border-b border-helm-line">
        <div className="flex items-center gap-2">
          <TrenstonMark size={28} className="rounded-md" />
          <span className="text-helm-fg font-semibold text-sm">Trenston</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid="mobile-search-btn"
            onClick={openSearch}
            className="text-helm-fg p-2"
            aria-label="Search"
          >
            <Search className="w-5 h-5" />
          </button>
          <button data-testid="mobile-menu-btn" onClick={() => setMobileOpen(true)} className="text-helm-fg p-2">
            <Menu className="w-5 h-5" />
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[300px] bg-transparent px-1 pt-2 pb-2">
            <button onClick={() => setMobileOpen(false)} className="absolute top-5 right-5 text-helm-muted z-10">
              <X className="w-5 h-5" />
            </button>
            <SidebarContent
              onNavigate={() => setMobileOpen(false)}
              billingEnforced={billingEnforced}
            />
          </div>
        </div>
      )}

      {/* Mobile search dialog */}
      <div className="lg:hidden">
        <QuickNavPalette
          open={searchOpen}
          onOpenChange={setSearchOpen}
          variant="dialog"
          enableShortcut={false}
        />
      </div>

      <main className="lg:pl-[240px] relative z-10">
        {/* Desktop persistent top bar */}
        <div
          className="hidden lg:flex sticky top-0 z-40 h-14 items-center gap-3 px-5 md:px-8 lg:px-10 bg-helm-bg/95 backdrop-blur-md border-b border-helm-line"
          data-testid="desktop-top-bar"
        >
          <div className="flex-1 min-w-0">
            <QuickNavPalette
              variant="inline"
              searchRef={desktopSearchRef}
              enableShortcut={false}
            />
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span
              data-testid="topbar-plan-badge"
              className="hidden xl:inline-flex items-center rounded-full border border-helm-line px-3 py-1 text-xs text-helm-muted whitespace-nowrap"
            >
              {planBadge}
            </span>
            <button
              type="button"
              data-testid="topbar-notifications"
              aria-label="Notifications"
              onClick={() => navigate("/app/tasks")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-helm-line text-helm-muted transition-colors hover:bg-helm-fg/[0.04] hover:text-helm-fg"
            >
              <Bell className="w-4 h-4" />
            </button>
            <ProfileDropdown
              name={user?.name || "CEO"}
              picture={user?.picture}
              planLabel={planLabel}
              showBilling={canBilling}
              onBilling={() => navigate("/app/billing")}
              onIntegrations={() => navigate("/app/integrations")}
              onSettings={() => navigate("/app/settings")}
              onHelp={() => navigate("/app/help")}
              onLogout={logout}
            />
          </div>
        </div>
        <div className="w-full px-5 md:px-8 lg:px-10 py-8 md:py-10">
          {onBilling ? (
            <Outlet />
          ) : (
            <SubscriptionGate isPro={isPro} canManageBilling={canBilling}>
              <Outlet />
            </SubscriptionGate>
          )}
        </div>
      </main>
    </div>
  );
}
