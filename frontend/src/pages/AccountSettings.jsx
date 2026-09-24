import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Download, ScrollText, Sun, Monitor, ShieldCheck, Plug, Building2, Eraser, UserRound, ImageIcon, Globe } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { blobErrorDetail } from "@/hooks/useFetch";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { PageHeader, GlassCard } from "@/components/kit";
import DangerConfirmCard from "@/components/DangerConfirmCard";
import DepartmentsSettings from "@/components/DepartmentsSettings";
import DocumentsLibrarySettings from "@/components/DocumentsLibrarySettings";
import InviteCeoCard from "@/components/InviteCeoCard";
import { useTheme } from "@/context/ThemeContext";
import SwitchButton from "@/components/kokonutui/switch-button";
import { cn } from "@/lib/utils";
import { canManageBilling, hasPerm } from "@/lib/access";
import { addDaysISO, DEFAULT_TIMEZONE, supportedTimezones, todayISO } from "@/lib/dates";

export default function AccountSettings() {
  const { user, setUser, logout } = useAuth();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const location = useLocation();
  const { data: company, reload: reloadCompany } = useCompanyQuery();
  const isOwner = user?.role === "owner" || user?.pack === "owner";
  const canBilling = canManageBilling(user);
  const canClearSample = hasPerm(user, "workspace:edit");
  const canExportActivity = isOwner || (user?.perms || []).includes("members:manage");
  const [busy, setBusy] = useState(null);
  const [companyName, setCompanyName] = useState("");
  const [timezoneDraft, setTimezoneDraft] = useState(DEFAULT_TIMEZONE);
  const [displayName, setDisplayName] = useState("");
  const [confirmAccount, setConfirmAccount] = useState("");
  const [confirmWorkspace, setConfirmWorkspace] = useState("");
  const [confirmClearSample, setConfirmClearSample] = useState("");
  const [showAccountConfirm, setShowAccountConfirm] = useState(false);
  const [showWorkspaceConfirm, setShowWorkspaceConfirm] = useState(false);
  const [showClearSampleConfirm, setShowClearSampleConfirm] = useState(false);
  const pictureInputRef = useRef(null);
  const logoInputRef = useRef(null);
  const workspaceTz = company?.timezone;
  const [actStart, setActStart] = useState(() => addDaysISO(todayISO(workspaceTz), -30));
  const [actEnd, setActEnd] = useState(() => todayISO(workspaceTz));

  useEffect(() => {
    setCompanyName(company?.name || "");
  }, [company?.name]);

  useEffect(() => {
    setTimezoneDraft(company?.timezone || DEFAULT_TIMEZONE);
  }, [company?.timezone]);

  useEffect(() => {
    setDisplayName((user?.name || "").trim());
  }, [user?.name]);

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

  const timezoneOptions = supportedTimezones();

  const saveTimezone = async () => {
    const next = timezoneDraft.trim();
    if (!timezoneOptions.includes(next)) {
      toast.error("Pick a timezone from the list");
      return;
    }
    if (next === (company?.timezone || DEFAULT_TIMEZONE)) {
      toast.message("Timezone is unchanged");
      return;
    }
    setBusy("timezone");
    try {
      await api.patch("/company", { timezone: next, company_setup_done: true });
      toast.success("Timezone saved");
      reloadCompany();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save timezone");
    } finally {
      setBusy(null);
    }
  };

  const saveDisplayName = async () => {
    const next = displayName.trim();
    if (!next) {
      toast.error("Display name is required");
      return;
    }
    if (next === (user?.name || "").trim()) {
      toast.message("Name is unchanged");
      return;
    }
    setBusy("display-name");
    try {
      const { data } = await api.patch("/account/profile", { name: next });
      setUser((u) => (u ? { ...u, name: data?.name || next } : u));
      toast.success("Display name updated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update display name");
    } finally {
      setBusy(null);
    }
  };

  const uploadPicture = async (file) => {
    if (!file) return;
    setBusy("picture");
    try {
      const body = new FormData();
      body.append("file", file);
      const { data } = await api.post("/account/picture", body);
      setUser((u) => (u ? { ...u, picture: data?.picture || null } : u));
      toast.success("Profile picture updated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not upload picture");
    } finally {
      setBusy(null);
      if (pictureInputRef.current) pictureInputRef.current.value = "";
    }
  };

  const clearPicture = async () => {
    setBusy("picture");
    try {
      await api.delete("/account/picture");
      setUser((u) => (u ? { ...u, picture: null } : u));
      toast.success("Profile picture removed");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not remove picture");
    } finally {
      setBusy(null);
    }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    setBusy("logo");
    try {
      const body = new FormData();
      body.append("file", file);
      await api.post("/company/logo", body);
      toast.success("Company logo updated");
      reloadCompany();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not upload logo");
    } finally {
      setBusy(null);
      if (logoInputRef.current) logoInputRef.current.value = "";
    }
  };

  const clearLogo = async () => {
    setBusy("logo");
    try {
      await api.delete("/company/logo");
      toast.success("Company logo removed");
      reloadCompany();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not remove logo");
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
      a.download = `trenston-export-${todayISO(workspaceTz)}.json`;
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
      a.download = `trenston-activity-${actStart}-to-${actEnd}.csv`;
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

  const cancelClearSampleConfirm = () => {
    setShowClearSampleConfirm(false);
    setConfirmClearSample("");
  };

  const clearSampleData = async () => {
    if (!showClearSampleConfirm) {
      setShowClearSampleConfirm(true);
      return;
    }
    if (confirmClearSample.trim().toLowerCase() !== "start fresh") {
      toast.error('Type "start fresh" to confirm');
      return;
    }
    setBusy("clear-sample");
    try {
      await api.post("/workspace/clear-sample");
      toast.success("Sample data removed. You're starting fresh.");
      try {
        window.localStorage.removeItem(`helm-sample-banner-${company?.workspace_id || ""}`);
      } catch {
        // ignore
      }
      reloadCompany();
      setShowClearSampleConfirm(false);
      setConfirmClearSample("");
      window.location.href = "/app";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not remove sample data");
      setBusy(null);
      setConfirmClearSample("");
    }
  };

  const deleteAccount = async () => {
    if (!emailConfirm) {
      toast.error("Your account needs an email before it can be deleted");
      return;
    }
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
    if (!workspaceConfirm) {
      toast.error("Set a company name before deleting the workspace");
      return;
    }
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

      <GlassCard id="profile" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="profile-settings-card">
        <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
          <UserRound className="w-4 h-4" />
          <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Your profile</span>
        </div>
        <p className="text-sm text-helm-muted mb-4 leading-relaxed">
          Display name and photo shown in the sidebar, assignee pickers, and across the cockpit.
        </p>
        <div className="flex items-center gap-4 mb-4">
          <div className="h-14 w-14 rounded-full border border-helm-line bg-helm-fg/[0.04] overflow-hidden flex items-center justify-center shrink-0">
            {user?.picture ? (
              <img src={user.picture} alt="" className="h-full w-full object-cover" />
            ) : (
              <UserRound className="w-6 h-6 text-helm-muted" />
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              ref={pictureInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              data-testid="profile-picture-input"
              onChange={(e) => uploadPicture(e.target.files?.[0])}
            />
            <button
              type="button"
              data-testid="profile-picture-upload"
              disabled={!!busy}
              onClick={() => pictureInputRef.current?.click()}
              className="rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5 disabled:opacity-60"
            >
              {busy === "picture" ? "Uploading…" : "Upload photo"}
            </button>
            {user?.picture && (
              <button
                type="button"
                data-testid="profile-picture-clear"
                disabled={!!busy}
                onClick={clearPicture}
                className="rounded-md border border-helm-line text-helm-muted text-sm px-3 py-2 hover:bg-helm-fg/5 disabled:opacity-60"
              >
                Remove
              </button>
            )}
          </div>
        </div>
        <label className="block text-xs text-helm-muted mb-1">Display name</label>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            data-testid="display-name-input"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && saveDisplayName()}
            maxLength={120}
            className="flex-1 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/40"
            placeholder="Your name"
          />
          <button
            type="button"
            data-testid="display-name-save"
            onClick={saveDisplayName}
            disabled={busy === "display-name"}
            className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
          >
            {busy === "display-name" ? "Saving…" : "Save name"}
          </button>
        </div>
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

      {isOwner && (
        <GlassCard id="company-timezone" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="company-timezone-card">
          <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
            <Globe className="w-4 h-4" />
            <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Timezone</span>
          </div>
          <p className="text-sm text-helm-muted mb-4 leading-relaxed">
            Sets what &ldquo;today&rdquo; means for daily updates, reports, production logs, and your calendar.
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              data-testid="company-timezone-input"
              aria-label="Company timezone"
              list="company-timezone-options"
              value={timezoneDraft}
              onChange={(e) => setTimezoneDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveTimezone()}
              className="flex-1 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/40"
              placeholder="Search timezones, e.g. Asia/Manila"
            />
            <datalist id="company-timezone-options">
              {timezoneOptions.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
            <button
              type="button"
              data-testid="company-timezone-save"
              onClick={saveTimezone}
              disabled={busy === "timezone"}
              className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
            >
              {busy === "timezone" ? "Saving…" : "Save timezone"}
            </button>
          </div>
        </GlassCard>
      )}

      {isOwner && (
        <GlassCard id="company-logo" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="company-logo-card">
          <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
            <ImageIcon className="w-4 h-4" />
            <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Company logo</span>
          </div>
          <p className="text-sm text-helm-muted mb-4 leading-relaxed">
            CEO only. Shows in the sidebar brand mark and as the browser tab icon for this workspace.
          </p>
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-md border border-helm-line bg-helm-fg/[0.04] overflow-hidden flex items-center justify-center shrink-0">
              {company?.logo_url ? (
                <img src={company.logo_url} alt="" className="h-full w-full object-cover" />
              ) : (
                <Building2 className="w-6 h-6 text-helm-muted" />
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                ref={logoInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                data-testid="company-logo-input"
                onChange={(e) => uploadLogo(e.target.files?.[0])}
              />
              <button
                type="button"
                data-testid="company-logo-upload"
                disabled={!!busy}
                onClick={() => logoInputRef.current?.click()}
                className="rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5 disabled:opacity-60"
              >
                {busy === "logo" ? "Uploading…" : "Upload logo"}
              </button>
              {company?.logo_url && (
                <button
                  type="button"
                  data-testid="company-logo-clear"
                  disabled={!!busy}
                  onClick={clearLogo}
                  className="rounded-md border border-helm-line text-helm-muted text-sm px-3 py-2 hover:bg-helm-fg/5 disabled:opacity-60"
                >
                  Remove
                </button>
              )}
            </div>
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

      {canClearSample && company?.template === "sample" && (
        <GlassCard id="clear-sample" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="clear-sample-card">
          <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
            <Eraser className="w-4 h-4" />
            <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Sample data</span>
          </div>
          <p className="text-sm text-helm-muted mb-4 leading-relaxed">
            You&apos;re exploring with Northwind Robotics sample data. Remove it to start fresh with your own numbers —
            billing, integrations, and company profile stay intact.
          </p>
          {!showClearSampleConfirm ? (
            <button
              type="button"
              data-testid="clear-sample-btn"
              onClick={clearSampleData}
              disabled={!!busy}
              className="rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/5 disabled:opacity-60"
            >
              Remove sample data
            </button>
          ) : (
            <div className="space-y-3" data-testid="clear-sample-confirm">
              <p className="text-sm text-helm-fg leading-relaxed">
                This deletes sample financials, decisions, tasks, people, and reports. Type{" "}
                <span className="font-mono text-helm-gold">start fresh</span> to confirm.
              </p>
              <input
                data-testid="confirm-clear-sample-input"
                value={confirmClearSample}
                onChange={(e) => setConfirmClearSample(e.target.value)}
                placeholder="start fresh"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="confirm-clear-sample-btn"
                  onClick={clearSampleData}
                  disabled={busy === "clear-sample"}
                  className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
                >
                  {busy === "clear-sample" ? "Removing…" : "Start fresh"}
                </button>
                <button
                  type="button"
                  data-testid="cancel-clear-sample-btn"
                  onClick={cancelClearSampleConfirm}
                  disabled={busy === "clear-sample"}
                  className="rounded-md border border-helm-line text-helm-muted text-sm px-4 py-2.5 hover:bg-helm-fg/5"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </GlassCard>
      )}

      <div
        className={cn("grid gap-4 mb-4", isOwner && "md:grid-cols-2")}
        data-testid="danger-zone-row"
      >
        <DangerConfirmCard
          id="delete-account"
          className="fade-up h-full"
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
          disabled={Boolean(busy) && busy !== "account"}
          busyLabel="Deleting…"
          onAction={deleteAccount}
          onCancel={cancelAccountConfirm}
          actionTestId="delete-account-btn"
          cancelTestId="cancel-delete-account-btn"
          inputTestId="confirm-account-input"
        />

        {isOwner && (
          <DangerConfirmCard
            id="delete-workspace"
            className="fade-up h-full"
            title="Delete workspace"
            message="Are you sure you want to delete this workspace? All company data for every member will be permanently removed. This action cannot be undone."
            confirmLabel="Delete"
            confirmingLabel="Delete"
            icon="alert"
            showConfirm={showWorkspaceConfirm}
            confirmHint={workspaceConfirm || undefined}
            confirmValue={confirmWorkspace}
            onConfirmValueChange={setConfirmWorkspace}
            confirmPlaceholder={company?.name || ""}
            busy={busy === "workspace"}
            disabled={Boolean(busy) && busy !== "workspace"}
            busyLabel="Deleting…"
            onAction={deleteWorkspace}
            onCancel={cancelWorkspaceConfirm}
            actionTestId="delete-workspace-btn"
            cancelTestId="cancel-delete-workspace-btn"
            inputTestId="confirm-workspace-input"
          />
        )}
      </div>
    </div>
  );
}
