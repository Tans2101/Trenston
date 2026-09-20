import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMemo, useState } from "react";
import {
  LayoutDashboard, GitBranch, Activity, KanbanSquare,
  FileText, Calendar, Contact, MessageSquareText,
  Menu, X, UsersRound, ChevronDown, Check, Plus, Sun, Wallet, Search,
  HelpCircle, Shield, Scale, Settings, Plug, Download, ScrollText,
  Trash2, Building2, CreditCard, ShieldCheck, AlertTriangle, FolderOpen,
  Info, LayoutGrid, Receipt,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/hooks/useFetch";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { useDepartmentsQuery } from "@/hooks/useDepartmentsQuery";
import { api } from "@/lib/api";
import { toast } from "sonner";
import SubscriptionGate from "@/components/SubscriptionGate";
import CompanySetup from "@/pages/CompanySetup";
import { helmPlanLabel, helmWorkspacePlanLabel, helmHasFullAccess } from "@/lib/helmPlan";
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

function SidebarContent({ onNavigate, billingEnforced, onOpenSearch }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: company } = useCompanyQuery();
  const { data: deptData } = useDepartmentsQuery();
  const isPro = helmHasFullAccess(company?.plan, billingEnforced);
  const mainNav = NAV.filter((item) => navItemVisible(item, user));
  const deptNav = (deptData?.departments || []).filter((d) => departmentNavVisible(d));
  const canBilling = canManageBilling(user);

  // Prefer a department match when on a dept route so the main track stays quiet.
  const activeDeptId = deptNav.find((d) => pathMatches(departmentNavTo(d.type), location.pathname, false))?.type || null;
  const activeMainId = activeDeptId
    ? null
    : (mainNav.find((item) => pathMatches(item.to, location.pathname, item.end))?.id || null);

  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "");

  const navBtn = ({ isActive }) =>
    cn(
      "group relative flex w-full items-center gap-2.5 rounded-full px-4 py-2.5 text-sm transition-colors duration-200",
      isActive
        ? "text-helm-navy border border-transparent"
        : "text-helm-muted border border-helm-line bg-helm-fg/[0.03] hover:text-helm-fg hover:bg-helm-fg/[0.06] hover:border-helm-fg/15",
    );

  return (
    <div className="flex flex-col h-full">
      <WorkspaceSwitcher onNavigate={onNavigate} billingEnforced={billingEnforced} />

      <div className="px-1 pt-3">
        <button
          type="button"
          data-testid="nav-search-btn"
          onClick={() => onOpenSearch?.()}
          className="inline-flex w-full max-w-full items-center gap-2.5 rounded-full border border-helm-line bg-helm-fg/[0.03] px-4 py-2.5 text-sm text-helm-muted transition-colors hover:text-helm-fg hover:bg-helm-fg/[0.06] hover:border-helm-fg/15"
        >
          <Search className="w-[18px] h-[18px] shrink-0" />
          <span className="flex-1 text-left truncate">Search</span>
          <kbd className="hidden sm:inline font-mono text-[10px] text-helm-muted border border-helm-line rounded-full px-1.5 py-0.5 shrink-0">
            {isMac ? "⌘K" : "Ctrl+K"}
          </kbd>
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-1 py-3" aria-label="App">
        <SmoothTab
          orientation="vertical"
          variant="pill"
          activeId={activeDeptId ? `dept-${activeDeptId}` : activeMainId}
          className="gap-2"
        >
          {mainNav.map((item) => (
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
                    <item.icon className={cn("w-[18px] h-[18px] shrink-0", isActive ? "text-helm-navy" : "text-helm-muted group-hover:text-helm-fg")} />
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            </SmoothTabItem>
          ))}
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
                  {({ isActive }) => (
                    <>
                      <Icon className={cn("w-[18px] h-[18px] shrink-0", isActive ? "text-helm-navy" : "text-helm-muted group-hover:text-helm-fg")} />
                      <span>{dept.name}</span>
                    </>
                  )}
                </NavLink>
              </SmoothTabItem>
            );
          })}
        </SmoothTab>
      </nav>

      <div className="px-1 pb-4">
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

function QuickNavPalette({ open, onOpenChange }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: deptData } = useDepartmentsQuery();
  const isOwner = user?.role === "owner" || user?.pack === "owner";
  const canBilling = canManageBilling(user);
  const canExportActivity = isOwner || (user?.perms || []).includes("members:manage");

  const actions = useMemo(() => {
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

    return [...navActions, ...deptActions, ...settingsActions, ...siteActions];
  }, [user, deptData, isOwner, canBilling, canExportActivity]);

  return (
    <ActionSearchBar
      open={open}
      onOpenChange={onOpenChange}
      actions={actions}
      onSelect={(action) => {
        if (!action?.to) return;
        if (action.to.startsWith("mailto:")) {
          window.location.href = action.to;
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
  const location = useLocation();
  const { user } = useAuth();
  const { data: billing } = useFetch("/billing/plans");
  const { data: company, loading: companyLoading } = useCompanyQuery();
  const billingEnforced = billing?.billing_enforced === true;
  const pastDue = billingEnforced && billing?.subscription_status === "past_due";
  const isPro = helmHasFullAccess(company?.plan, billingEnforced);
  const onBilling = location.pathname.startsWith("/app/billing");
  const canBilling = canManageBilling(user);
  const needsCompanySetup = company?.role === "owner" && company?.company_setup_done === false;

  if (companyLoading && !company) {
    return <LoadingScreen label="Loading Trenston" />;
  }

  if (needsCompanySetup) {
    return <CompanySetup company={company} />;
  }

  const openSearch = () => setSearchOpen(true);

  return (
    <div className="app-shell min-h-screen">
      {pastDue && (
        <div className="lg:pl-[220px] bg-helm-status-warning/12 border-b border-helm-status-warning/35 px-5 py-2.5 text-center text-sm text-helm-fg" data-testid="global-past-due-banner">
          Payment past due: <button type="button" onClick={() => window.location.href = "/app/billing"} className="underline font-medium text-helm-status-warning">update billing</button> to keep Trenston access.
        </div>
      )}
      {/* Desktop nav rail — same surface as the page, no enclosed panel */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-[220px] flex-col z-40 px-2">
        <SidebarContent billingEnforced={billingEnforced} onOpenSearch={openSearch} />
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
          <div className="absolute inset-y-0 left-0 w-[280px] bg-helm-bg px-2 pt-10">
            <button onClick={() => setMobileOpen(false)} className="absolute top-4 right-4 text-helm-muted z-10">
              <X className="w-5 h-5" />
            </button>
            <SidebarContent
              onNavigate={() => setMobileOpen(false)}
              billingEnforced={billingEnforced}
              onOpenSearch={() => { setMobileOpen(false); openSearch(); }}
            />
          </div>
        </div>
      )}

      <QuickNavPalette open={searchOpen} onOpenChange={setSearchOpen} />

      <main className="lg:pl-[220px] relative z-10">
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
