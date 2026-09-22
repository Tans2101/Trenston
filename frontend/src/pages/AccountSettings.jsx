import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, ScrollText, Sun, Monitor, ShieldCheck, Plug, Building2 } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useFetch, blobErrorDetail } from "@/hooks/useFetch";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { PageHeader, GlassCard } from "@/components/kit";
import DangerConfirmCard from "@/components/DangerConfirmCard";
import DepartmentsSettings from "@/components/DepartmentsSettings";
import DocumentsLibrarySettings from "@/components/DocumentsLibrarySettings";
import InviteCeoCard from "@/components/InviteCeoCard";
import { useTheme } from "@/context/ThemeContext";
import SwitchButton from "@/components/kokonutui/switch-button";
import { cn } from "@/lib/utils";
import { canManageBilling } from "@/lib/access";

export default function AccountSettings() {
  const { user, setUser, logout } = useAuth();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const location = useLocation();
  const { data: company, reload: reloadCompany } = useCompanyQuery();
  const isOwner = user?.role === "owner" || user?.pack === "owner";
  const canBilling = canManageBilling(user);
  const canExportActivity = isOwner || (user?.perms || []).includes("members:manage");
  const [busy, setBusy] = useState(null);
  const [companyName, setCompanyName] = useState("");
  const [confirmAccount, setConfirmAccount] = useState("");
  const [confirmWorkspace, setConfirmWorkspace] = useState("");
  const [showAccountConfirm, setShowAccountConfirm] = useState(false);
  const [showWorkspaceConfirm, setShowWorkspaceConfirm] = useState(false);
  const [actStart, setActStart] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  });
  const [actEnd, setActEnd] = useState(() => new Date().toISOString().slice(0, 10));

  useEffect(() => {
    setCompanyName(company?.name || "");
  }, [company?.name]);

  useEffect(() => {
    const hash = location.hash?.replace(/^#/, "");
    if (!hash) return undefined;
    const t = window.setTimeout(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
    return () => window.clearTimeout(t);
  }, [location.hash, location.pathname]);

  const emailConfirm = (user?.email || "").trim().toLowerCase();
  const workspaceConfirm = (company?.name || "").trim();

  const applyTheme = (id) => {
    setTheme(id);
    if (user) setUser({ ...user, appearance: id });
  };

  const saveCompanyName = async () => {
    const next = companyName.trim();
    if (!next) {
      toast.error("Company name is required");
      return;
    }
    if (next === (company?.name || "").trim()) {
      toast.message("Name is unchanged");
      return;
    }
    setBusy("rename");
    try {
      await api.patch("/company", { name: next, company_setup_done: true });
      toast.success("Company renamed");
      reloadCompany();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not rename company");
    } finally {
      setBusy(null);
    }
  };

  const exportData = async () => {
    setBusy("export");
    try {
      const { data } = await api.get("/account/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `helm-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Export downloaded");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not export data");
    } finally {
      setBusy(null);
    }
  };

  const exportActivity = async () => {
    if (!actStart || !actEnd) {
      toast.error("Choose a start and end date");
      return;
    }
    setBusy("activity");
    try {
      const res = await api.get("/activities/export", {
        params: { start: actStart, end: actEnd, format: "csv" },
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `helm-activity-${actStart}-to-${actEnd}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Activity log downloaded");
    } catch (e) {
      toast.error(await blobErrorDetail(e, "Could not export activity log"));
    } finally {
      setBusy(null);
    }
  };

  const cancelAccountConfirm = () => {
    setShowAccountConfirm(false);
    setConfirmAccount("");
  };

  const cancelWorkspaceConfirm = () => {
    setShowWorkspaceConfirm(false);
    setConfirmWorkspace("");
  };

  const deleteAccount = async () => {
    if (!showAccountConfirm) {
      setShowAccountConfirm(true);
      return;
    }
    if (confirmAccount.trim().toLowerCase() !== emailConfirm) {
      toast.error("Type your email exactly to confirm");
      return;
    }
    setBusy("account");
    try {
      await api.delete("/account");
      toast.success("Account deleted");
      await logout();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete account");
      setBusy(null);
      // Leave confirm open for retry, but clear the typed value so it isn't half-stale.
      setConfirmAccount("");
    }
  };

  const deleteWorkspace = async () => {
    if (!showWorkspaceConfirm) {
      setShowWorkspaceConfirm(true);
      return;
    }
    if (confirmWorkspace.trim() !== workspaceConfirm) {
      toast.error("Type the workspace name exactly to confirm");
      return;
    }
    setBusy("workspace");
    try {
      await api.delete("/workspaces/current");
      toast.success("Workspace deleted");
      window.location.href = "/app";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete workspace");
      setBusy(null);
      setConfirmWorkspace("");
    }
  };

  return (
    <div className="max-w-2xl">
      <PageHeader
        title="Account settings"
        subtitle="Appearance, departments, documents, integrations, referrals, data export, and account controls."
      />

      <GlassCard id="settings-security" className="p-5 mb-4 fade-up scroll-mt-24">
        <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
          <ShieldCheck className="w-4 h-4" />
          <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Security</span>
        </div>
        <p className="text-sm text-helm-muted mb-4 leading-relaxed">
          How Trenston encrypts credentials, isolates workspaces, stores private files, and handles deletion.
        </p>
        <Link
          to="/security"
          className="inline-flex items-center text-sm text-helm-gold hover:text-helm-gold-hover"
        >
          Read how Trenston protects company data →
        </Link>
      </GlassCard>

      <GlassCard id="appearance" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="appearance-settings">
        <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
          <Sun className="w-4 h-4" />
          <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Appearance</span>
        </div>
        <p className="text-sm text-helm-muted mb-4 leading-relaxed">
          Choose how the Trenston cockpit looks. Light mode is the default for reading dense data.
          Your choice is saved to your account and follows you across devices.
        </p>
        <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Color theme">
          <SwitchButton
            mode={theme === "system" ? resolvedTheme : theme}
            resolvedMode={resolvedTheme}
            data-testid={
              (theme === "system" ? resolvedTheme : theme) === "dark" ? "theme-dark" : "theme-light"
            }
            onToggle={() => {
              const current = theme === "system" ? resolvedTheme : theme;
              applyTheme(current === "dark" ? "light" : "dark");
            }}
          />
          {(theme === "system" ? resolvedTheme : theme) === "dark" ? (
            <button
              type="button"
              data-testid="theme-light"
              className="sr-only"
              onClick={() => applyTheme("light")}
            >
              Light
            </button>
          ) : (
            <button
              type="button"
              data-testid="theme-dark"
              className="sr-only"
              onClick={() => applyTheme("dark")}
            >
              Dark
            </button>
          )}
          <button
            type="button"
            data-testid="theme-system"
            aria-pressed={theme === "system"}
            onClick={() => applyTheme("system")}
            className={cn(
              "inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm transition-colors",
              theme === "system"
                ? "border-helm-gold/35 bg-helm-gold/12 text-helm-fg"
                : "border-helm-line bg-helm-card text-helm-muted hover:text-helm-fg hover:border-helm-gold/35",
            )}
          >
            <Monitor className={cn("h-4 w-4", theme === "system" ? "text-helm-gold" : "text-helm-muted")} />
            System
          </button>
        </div>
        {theme === "system" && (
          <p className="mt-3 text-xs text-helm-muted">
            This device is currently using {resolvedTheme} mode.
          </p>
        )}
      </GlassCard>

      {isOwner && (
        <GlassCard id="company-name" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="company-rename-card">
          <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
            <Building2 className="w-4 h-4" />
            <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Company name</span>
          </div>
          <p className="text-sm text-helm-muted mb-4 leading-relaxed">
            Only the CEO can rename this company. The name shows in the sidebar workspace switcher and on exports.
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              data-testid="company-rename-input"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveCompanyName()}
              maxLength={120}
              className="flex-1 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/40"
              placeholder="Company name"
            />
            <button
              type="button"
              data-testid="company-rename-save"
              onClick={saveCompanyName}
              disabled={busy === "rename"}
              className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
            >
              {busy === "rename" ? "Saving…" : "Save name"}
            </button>
          </div>
        </GlassCard>
      )}

      {isOwner && <InviteCeoCard />}
      <DepartmentsSettings />
      <DocumentsLibrarySettings />

      <GlassCard id="integrations" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="settings-integrations-card">
        <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
          <Plug className="w-4 h-4" />
          <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Integrations</span>
        </div>
        <p className="text-sm text-helm-muted mb-4 leading-relaxed">
            Connect Google Calendar, QuickBooks, and other tools. Google is personal to each teammate; accounting connects once for the company.
        </p>
        <Link
          to="/app/integrations"
          data-testid="settings-integrations-link"
          className="inline-flex items-center text-sm text-helm-gold hover:text-helm-gold-hover"
        >
          Manage integrations →
        </Link>
      </GlassCard>

      <GlassCard id="export-data" className="p-5 mb-4 fade-up scroll-mt-24">
        <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
          <Download className="w-4 h-4" />
          <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Export data</span>
        </div>
        <p className="text-sm text-helm-muted mb-4 leading-relaxed">
          Download a JSON copy of data associated with your account and active workspace.
        </p>
        <button
          data-testid="export-data-btn"
          onClick={exportData}
          disabled={!!busy}
          className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 transition-colors hover:bg-helm-gold-hover disabled:opacity-60"
        >
          {busy === "export" ? "Exporting…" : "Export data"}
        </button>
        {canBilling && (
          <a
            href="/app/billing"
            data-testid="settings-billing-link"
            className="ml-3 inline-flex items-center rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/5"
          >
            Billing
          </a>
        )}
      </GlassCard>

      {canExportActivity && (
        <GlassCard id="export-activity" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="export-activity-card">
          <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
            <ScrollText className="w-4 h-4" />
            <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Export activity log</span>
          </div>
          <p className="text-sm text-helm-muted mb-4 leading-relaxed">
            Download a CSV audit trail (timestamp, actor, area, action, message) for a date range. Owner/admin only.
          </p>
          <div className="grid grid-cols-2 gap-3 mb-4">
            <label className="text-xs text-helm-muted">Start
              <input data-testid="activity-export-start" type="date" value={actStart} onChange={(e) => setActStart(e.target.value)}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg" />
            </label>
            <label className="text-xs text-helm-muted">End
              <input data-testid="activity-export-end" type="date" value={actEnd} onChange={(e) => setActEnd(e.target.value)}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg" />
            </label>
          </div>
          <button
            data-testid="export-activity-btn"
            onClick={exportActivity}
            disabled={!!busy}
            className="rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold font-medium text-sm px-4 py-2.5 transition-colors hover:bg-helm-gold/10 disabled:opacity-60"
          >
            {busy === "activity" ? "Exporting…" : "Export activity log"}
          </button>
        </GlassCard>
      )}

      <DangerConfirmCard
        id="delete-account"
        className="mb-4 fade-up"
        title="Delete account"
        message="Are you sure you want to delete your account? All of your data will be permanently removed. This action cannot be undone."
        confirmLabel="Delete"
        confirmingLabel="Delete"
        icon="alert"
        showConfirm={showAccountConfirm}
        confirmHint={user?.email}
        confirmValue={confirmAccount}
        onConfirmValueChange={setConfirmAccount}
        confirmPlaceholder={user?.email}
        busy={busy === "account"}
        onAction={deleteAccount}
        onCancel={cancelAccountConfirm}
        actionTestId="delete-account-btn"
        cancelTestId="cancel-delete-account-btn"
        inputTestId="confirm-account-input"
      />

      {isOwner && (
        <DangerConfirmCard
          id="delete-workspace"
          className="fade-up"
          title="Delete workspace"
          message="Are you sure you want to delete this workspace? All company data for every member will be permanently removed. This action cannot be undone."
          confirmLabel="Delete"
          confirmingLabel="Delete"
          icon="alert"
          showConfirm={showWorkspaceConfirm}
          confirmHint={company?.name || "workspace name"}
          confirmValue={confirmWorkspace}
          onConfirmValueChange={setConfirmWorkspace}
          confirmPlaceholder={company?.name}
          busy={busy === "workspace"}
          onAction={deleteWorkspace}
          onCancel={cancelWorkspaceConfirm}
          actionTestId="delete-workspace-btn"
          cancelTestId="cancel-delete-workspace-btn"
          inputTestId="confirm-workspace-input"
        />
      )}
    </div>
  );
}
