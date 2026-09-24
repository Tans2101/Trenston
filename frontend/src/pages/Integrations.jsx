import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Calendar, Building2, Check, ExternalLink, RefreshCw,
  Cloud, Github, MessageSquare, Clock, ArrowRight, Link2, Unlink,
} from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, ErrorScreen, SkeletonCardList } from "@/components/kit";
import { cn } from "@/lib/utils";

const ICONS = {
  google: Calendar,
  quickbooks: Building2,
  xero: Building2,
  sap_b1: Building2,
  hubspot: Cloud,
  github: Github,
  slack: MessageSquare,
};

// Google Workspace capabilities (backend google_oauth.google_capabilities keys).
const GOOGLE_CAPABILITY_LABELS = [
  ["calendar_write", "Calendar"],
  ["gmail", "Gmail threads"],
  ["gmail_compose", "Gmail drafts"],
  ["sheets", "Sheets export"],
  ["drive_file", "Drive import"],
];

const STATUS_LABELS = {
  connected: { text: "Connected", className: "text-helm-fg bg-helm-status-positive/12" },
  not_connected: { text: "Not connected", className: "text-helm-muted border border-helm-line" },
  unavailable: { text: "Unavailable", className: "text-helm-muted border border-helm-line" },
  coming_soon: { text: "Coming soon", className: "text-helm-muted border border-helm-line" },
  error: { text: "Slack disconnected", className: "text-helm-status-negative bg-helm-status-negative/12" },
};

function formatLastSynced(iso) {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function StatusBadge({ status }) {
  const cfg = STATUS_LABELS[status] || STATUS_LABELS.not_connected;
  const Icon = status === "connected" ? Check : null;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wide rounded px-2 py-1", cfg.className)}>
      {Icon && <Icon className="w-3 h-3" />}
      {cfg.text}
    </span>
  );
}

function IntegrationCard({ it, canManage, canUseConnection, canConnectGoogle, onConnect, onDisconnect, onSync, onNavigate, syncingProvider }) {
  const Icon = ICONS[it.id] || Cloud;
  const status = it.status || (it.connected ? "connected" : "not_connected");
  const lastSynced = it.sync_action ? formatLastSynced(it.last_synced_at) : null;
  const isComingSoon = it.coming_soon || status === "coming_soon";
  const isUnavailable = status === "unavailable";
  const isOAuth = it.kind === "oauth" && it.oauth;
  const isCredentials = it.kind === "credentials";
  const syncBusy = syncingProvider === it.provider;
  const isGoogle = it.provider === "google";
  // Google Workspace is per-user — any teammate can connect their own account.
  const canAct = isGoogle ? Boolean(canConnectGoogle ?? true) : canManage;

  const handleConnect = () => {
    if (isComingSoon || isUnavailable) return;
    if (isOAuth || isCredentials) {
      it.connected ? onDisconnect(it.provider) : onConnect(it.provider);
    } else if (it.cta_route) {
      onNavigate(it.cta_route);
    }
  };

  return (
    <GlassCard key={it.id} className="p-5 fade-up flex flex-col" data-testid={`integration-${it.id}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-lg bg-helm-fg/5 border border-helm-line flex items-center justify-center">
          <Icon className="w-5 h-5 text-helm-gold" />
        </div>
        <StatusBadge status={status} />
      </div>

      <h3 className="text-helm-fg font-medium">{it.name}</h3>
      <p className="text-[11px] font-mono uppercase tracking-wide text-helm-muted mt-0.5">{it.category}</p>
      <p className="text-sm text-helm-muted mt-2 leading-relaxed flex-1 min-h-[40px]">{it.description}</p>

      {it.value && (
        <p className="text-xs text-helm-muted mt-3 leading-relaxed border-l-2 border-helm-gold/35 pl-2">{it.value}</p>
      )}

      {it.connected && it.tenant_name && (
        <p className="text-xs text-helm-muted mt-2" data-testid={`${it.id}-tenant-name`}>
          {it.provider === "sap_b1" ? "Company DB" : "Organisation"}:{" "}
          <span className="text-helm-fg">{it.tenant_name}</span>
        </p>
      )}

      {isGoogle && it.connected && it.capabilities && (
        <ul className="mt-3 flex flex-wrap gap-1.5" data-testid={`${it.id}-capabilities`}>
          {GOOGLE_CAPABILITY_LABELS.map(([key, label]) => {
            const on = Boolean(it.capabilities[key]);
            return (
              <li
                key={key}
                className={cn(
                  "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] border",
                  on
                    ? "border-helm-status-positive/30 text-helm-fg bg-helm-status-positive/10"
                    : "border-helm-line text-helm-muted",
                )}
              >
                {on && <Check className="w-3 h-3" />}
                {label}
                {!on && <span className="sr-only"> (not enabled)</span>}
              </li>
            );
          })}
        </ul>
      )}

      {isUnavailable && (
        <p className="text-xs text-helm-muted mt-3 leading-relaxed" data-testid={`${it.id}-unavailable-hint`}>
          This connection isn’t available for your workspace yet. Try again later, or use Trenston without it.
        </p>
      )}

      {isGoogle && !it.connected && !isComingSoon && !isUnavailable && (
        <p
          className="text-xs text-helm-muted mt-3 leading-relaxed rounded-md border border-helm-line bg-helm-fg/[0.02] px-3 py-2"
          data-testid={`${it.id}-unverified-hint`}
        >
          Google may show <span className="text-helm-fg">“Google hasn&apos;t verified this app.”</span>{" "}
          That&apos;s expected while Trenston finishes Google&apos;s review. Click{" "}
          <span className="text-helm-fg">Advanced</span>, then{" "}
          <span className="text-helm-fg">Go to Trenston (unsafe)</span> to continue — your connection is still encrypted.
        </p>
      )}

      {it.needs_reconsent && it.connected && canAct && (
        <button
          type="button"
          data-testid={`reconnect-${it.id}`}
          onClick={() => onConnect(it.provider)}
          className="mt-3 w-full inline-flex items-center justify-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm py-2 hover:bg-helm-gold/10"
        >
          <RefreshCw className="w-3.5 h-3.5" /> {it.connect_label || "Reconnect Google"}
        </button>
      )}

      {it.sync_action && it.connected && lastSynced && (
        <p className="text-xs text-helm-muted mt-3 flex items-center gap-1" data-testid={`${it.id}-last-synced`}>
          <Clock className="w-3 h-3" /> Last synced {lastSynced}
        </p>
      )}

      
      {it.connected && canManage && !isGoogle && !canUseConnection && (
        <p className="text-xs text-helm-muted mt-3 leading-relaxed" data-testid={`${it.id}-token-restricted`}>
          Only the teammate who connected this integration (or a workspace owner) can sync or use it.
        </p>
      )}

      {it.sync_action && it.connected && canManage && canUseConnection && (
        <button
          type="button"
          data-testid={`sync-${it.id}-btn`}
          onClick={() => onSync(it.provider)}
          disabled={syncBusy}
          className="mt-3 w-full inline-flex items-center justify-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm py-2 hover:bg-helm-gold/10 disabled:opacity-60"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", syncBusy && "animate-spin")} />
          {syncBusy
            ? "Syncing…"
            : it.provider === "hubspot"
              ? "Sync to Pipeline"
              : "Sync to Financials"}
        </button>
      )}

      {it.connected && it.cta_route && (
        <button
          type="button"
          onClick={() => onNavigate(it.cta_route)}
          className="mt-3 w-full inline-flex items-center justify-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm py-2 hover:bg-helm-fg/5"
        >
          <ArrowRight className="w-3.5 h-3.5" /> {it.cta_label || "Open in Trenston"}
        </button>
      )}

      {!isComingSoon && (
        <button
          data-testid={`action-${it.id}`}
          onClick={handleConnect}
          disabled={isComingSoon || isUnavailable || (!canAct && !it.connected)}
          className={cn(
            "mt-4 w-full inline-flex items-center justify-center gap-1.5 rounded-md text-sm py-2.5 transition-colors disabled:opacity-50",
            it.connected
              ? "border border-helm-line text-helm-muted hover:bg-helm-fg/5"
              : isUnavailable
                ? "border border-helm-line text-helm-muted cursor-not-allowed"
                : "bg-helm-gold text-helm-navy font-medium hover:bg-helm-gold-hover",
          )}
        >
          {it.connected ? (
            <><Unlink className="w-3.5 h-3.5" /> Disconnect</>
          ) : isUnavailable ? (
            <><Link2 className="w-3.5 h-3.5" /> Connect unavailable</>
          ) : (
            <><ExternalLink className="w-3.5 h-3.5" /> {it.connect_label || `Connect ${it.name}`}</>
          )}
        </button>
      )}
    </GlassCard>
  );
}

export default function Integrations() {
  const { data, loading, error, reload } = useFetch("/integrations");
  const [params, setParams] = useSearchParams();
  const [syncingProvider, setSyncingProvider] = useState(null);
  const [slackUrl, setSlackUrl] = useState("");
  const [slackBusy, setSlackBusy] = useState(false);
  const [slackEditing, setSlackEditing] = useState(false);
  const [xeroTenantBusy, setXeroTenantBusy] = useState(false);
  const [sapModalOpen, setSapModalOpen] = useState(false);
  const [sapBusy, setSapBusy] = useState(false);
  const [sapForm, setSapForm] = useState({
    service_layer_url: "",
    company_db: "",
    username: "",
    password: "",
  });
  const navigate = useNavigate();

  useEffect(() => {
    if (params.get("connected")) {
      const connected = params.get("connected");
      const name = connected === "google"
        ? "Google Workspace"
        : connected === "quickbooks"
          ? "QuickBooks"
          : connected === "xero"
            ? "Xero"
            : connected === "hubspot"
              ? "HubSpot"
            : connected;
      toast.success(`${name} connected. Your data will flow into Trenston`);
      setParams({});
      reload();
    } else if (params.get("xero_select")) {
      toast.message("Choose which Xero organisation to sync");
      setParams({});
      reload();
    } else if (params.get("error")) {
      const err = params.get("error");
      const provider = params.get("provider");
      const reason = (params.get("reason") || "").toLowerCase();
      const providerName = provider === "quickbooks"
        ? "QuickBooks"
        : provider === "xero"
          ? "Xero"
          : provider === "hubspot"
            ? "HubSpot"
            : provider === "google"
              ? "Google"
              : "The provider";
      let message = "Could not complete the connection. Try again or use a different account.";
      if (err === "xero_org") {
        message = "No Xero organisations were available on that account.";
      } else if (err === "save") {
        message = reason === "seal"
          ? `${providerName} accepted the grant, but Trenston could not encrypt tokens. Set INTEGRATION_ENCRYPTION_KEY on Render (Fernet key), redeploy, then Connect again.`
          : `${providerName} accepted the grant, but Trenston could not save the connection. Check Render logs, then try Connect again.`;
      } else if (err === "token") {
        if (reason === "invalid_client") {
          message = `${providerName} rejected Trenston's app keys. On Render, set the matching ${provider === "quickbooks" ? "sandbox Development" : "OAuth"} Client ID/Secret, redeploy, then Connect again.`;
        } else if (reason === "invalid_grant") {
          message = `${providerName} rejected the auth code (expired or redirect URI mismatch). Confirm the Redirect URI is exact, then Connect again (codes are single-use).`;
        } else if (reason === "network") {
          message = `${providerName} accepted the grant, but Trenston could not reach the token server. Try Connect again in a minute.`;
        } else {
          message = `${providerName} accepted the grant, but Trenston could not finish the connection${reason ? ` (${reason})` : ""}. Check OAuth keys and redirect URI on Render, then try Connect again.`;
        }
      }
      toast.error(message);
      setParams({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  if (loading) {
    return (
      <div>
        <PageHeader
          title="Integrations"
          subtitle="Connect your calendar, accounting, and tools. Trenston pulls your data in so the briefing, financials, and calendar stay current."
        />
        <SkeletonCardList count={5} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load integrations"
        message={fetchErrorMessage(error, "Integrations data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  const gate = (provider) => {
    if (provider === "google") return true;
    if (!data.can_manage) {
      toast.error("Only workspace owners can connect integrations");
      return false;
    }
    if (data.integrations_enabled === false) {
      toast.error("Upgrade your plan to connect integrations");
      navigate("/app/billing", {
        state: { billingNotice: "Integrations require a paid Helm plan." },
      });
      return false;
    }
    return true;
  };

  const oauthConnect = async (provider) => {
    if (!gate(provider)) return;
    if (provider === "sap_b1") {
      setSapForm({ service_layer_url: "", company_db: "", username: "", password: "" });
      setSapModalOpen(true);
      return;
    }
    try {
      const { data: res } = await api.get(`/integrations/${provider}/connect`);
      if (res.configured && res.authorization_url) {
        window.location.href = res.authorization_url;
      } else {
        toast.info(res.message || "This connection isn't available yet on your Trenston instance.");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start connection");
    }
  };

  const connectSapB1 = async () => {
    if (!gate("sap_b1")) return;
    if (!sapForm.service_layer_url.trim() || !sapForm.company_db.trim() || !sapForm.username.trim() || !sapForm.password) {
      toast.error("Service Layer URL, company database, username, and password are required");
      return;
    }
    setSapBusy(true);
    try {
      await api.post("/integrations/sap_b1/connect", {
        service_layer_url: sapForm.service_layer_url.trim(),
        company_db: sapForm.company_db.trim(),
        username: sapForm.username.trim(),
        password: sapForm.password,
      });
      toast.success("SAP Business One connected");
      setSapModalOpen(false);
      setSapForm({ service_layer_url: "", company_db: "", username: "", password: "" });
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not connect SAP Business One");
    } finally {
      setSapBusy(false);
    }
  };

  const oauthDisconnect = async (provider) => {
    if (!gate(provider)) return;
    try {
      await api.post(`/integrations/${provider}/disconnect`);
      reload();
      toast.success("Disconnected");
    } catch {
      toast.error("Could not disconnect");
    }
  };

  const syncAccounting = async (provider) => {
    if (!gate(provider)) return;
    setSyncingProvider(provider);
    try {
      const { data: res } = await api.post(`/integrations/${provider}/sync`, {}, { timeout: 120000 });
      const label = provider === "xero" ? "Xero" : provider === "hubspot" ? "HubSpot" : provider === "sap_b1" ? "SAP Business One" : "QuickBooks";
      const unit = provider === "hubspot" ? "deal" : "transaction";
      toast.success(`Synced ${res.synced_count} ${unit}${res.synced_count === 1 ? "" : "s"} from ${label}`);
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${provider} sync failed`);
      if (e?.response?.status === 401) reload();
    } finally {
      setSyncingProvider(null);
    }
  };

  const selectXeroTenant = async (tenantId) => {
    if (!gate("xero")) return;
    setXeroTenantBusy(true);
    try {
      const { data: res } = await api.post("/integrations/xero/select-tenant", { tenant_id: tenantId });
      toast.success(`Xero organisation selected: ${res.tenant_name || "done"}`);
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not select organisation");
    } finally {
      setXeroTenantBusy(false);
    }
  };

  const saveSlackWebhook = async (nextUrl = slackUrl) => {
    if (!gate("slack")) return;
    const url = (nextUrl || "").trim();
    setSlackBusy(true);
    try {
      await api.put("/integrations/slack-webhook", { webhook_url: url });
      toast.success(url ? "Slack connected" : "Slack webhook removed");
      setSlackUrl("");
      setSlackEditing(false);
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save webhook");
    } finally {
      setSlackBusy(false);
    }
  };

  const slackBroken = data.slack_webhook_status === "broken";
  const slackConfigured = Boolean(data.slack_webhook_configured);
  const connectable = data.integrations.filter((i) => (i.kind === "oauth" || i.kind === "credentials") && !i.coming_soon);
  const roadmap = data.integrations.filter((i) => i.coming_soon);
  const connectedCount = connectable.filter((i) => i.connected).length;

  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="Connect your calendar, accounting, and tools. Trenston pulls your data in so the briefing, financials, and calendar stay current."
      />

      <GlassCard className="p-4 mb-8 fade-up border-helm-line">
        <p className="text-sm text-helm-muted leading-relaxed">
          <span className="text-helm-fg">Google Calendar &amp; Gmail</span> are personal — each teammate connects
          their own Google account and only sees their meetings and threads. Accounting (QuickBooks, Xero, SAP)
          and HubSpot are <span className="text-helm-fg">per company workspace</span>; owners connect those once.
          OAuth apps never share passwords; SAP Business One stores Service Layer credentials encrypted at rest.
          {connectedCount > 0 && (
            <span className="text-helm-status-positive/90"> {connectedCount} connected.</span>
          )}
        </p>
        <p className="text-xs text-helm-muted mt-3 leading-relaxed" data-testid="google-unverified-page-hint">
          Connecting Google may show <span className="text-helm-fg">“Google hasn&apos;t verified this app.”</span>{" "}
          Click <span className="text-helm-fg">Advanced</span>, then{" "}
          <span className="text-helm-fg">Go to Trenston (unsafe)</span> — expected until Google finishes reviewing Trenston.
        </p>
      </GlassCard>

      {data.can_manage && (data.xero_pending_tenants || []).length > 0 && (
        <GlassCard className="p-5 mb-8 fade-up border-helm-gold/35" data-testid="xero-tenant-picker">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-helm-muted mb-2">Choose Xero organisation</p>
          <p className="text-sm text-helm-muted mb-4 leading-relaxed">
            Your Xero login can access more than one organisation. Pick which one Trenston should sync into Financials.
          </p>
          <div className="space-y-2">
            {data.xero_pending_tenants.map((t) => (
              <button
                key={t.tenant_id}
                type="button"
                data-testid={`xero-tenant-${t.tenant_id}`}
                disabled={xeroTenantBusy}
                onClick={() => selectXeroTenant(t.tenant_id)}
                className="w-full text-left rounded-md border border-helm-line bg-helm-fg/[0.02] px-4 py-3 hover:border-helm-gold/35 hover:bg-helm-fg/[0.04] disabled:opacity-60"
              >
                <span className="text-sm text-helm-fg">{t.tenant_name}</span>
                <span className="block text-[10px] font-mono text-helm-muted mt-0.5">{t.tenant_id}</span>
              </button>
            ))}
          </div>
        </GlassCard>
      )}

      <h2 className="text-[11px] font-mono uppercase tracking-[0.2em] text-helm-muted mb-3">Connect your accounts</h2>
      {data.can_manage && typeof data.encryption_ready === "boolean" && (
        <p className="text-xs text-helm-muted mb-3" data-testid="oauth-diag">
          Encryption: {data.encryption_ready ? "ready" : "missing INTEGRATION_ENCRYPTION_KEY on Render"}
          {data.quickbooks_env ? ` · QuickBooks env: ${data.quickbooks_env}` : ""}
          {data.oauth_redirect_uris?.quickbooks
            ? ` · QB redirect: ${data.oauth_redirect_uris.quickbooks}`
            : ""}
        </p>
      )}
      <div className="grid md:grid-cols-2 gap-4 mb-10">
        {data.can_manage && (
          <GlassCard className="p-5 fade-up flex flex-col" data-testid="slack-webhook-card">
            <div className="flex items-start justify-between mb-3">
              <div className="w-10 h-10 rounded-lg bg-helm-fg/5 border border-helm-line flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-helm-gold" />
              </div>
              <StatusBadge
                status={
                  data.slack_webhook_status === "broken"
                    ? "error"
                    : data.slack_webhook_configured
                      ? "connected"
                      : "not_connected"
                }
              />
            </div>
            <h3 className="text-helm-fg font-medium">Slack</h3>
            <p className="text-[11px] font-mono uppercase tracking-wide text-helm-muted mt-0.5">Alerts</p>
            <p className="text-sm text-helm-muted mt-2 leading-relaxed flex-1 min-h-[40px]">
              {slackBroken
                ? "Slack stopped accepting alerts from this webhook. Paste a new Incoming Webhook URL to reconnect."
                : "Post high-severity Trenston alerts to a Slack channel with an Incoming Webhook URL."}
            </p>
            {slackBroken && (
              <p className="text-xs text-helm-status-negative font-mono mt-2" data-testid="slack-reconnect-hint">
                Slack disconnected — reconnect
              </p>
            )}
            {slackConfigured && !slackBroken && !slackEditing ? (
              <>
                <p className="text-xs text-helm-muted mt-3">
                  Webhook{" "}
                  <span className="font-mono text-helm-fg break-all" data-testid="slack-webhook-masked">
                    {data.slack_webhook_masked}
                  </span>
                </p>
                <div className="mt-4 flex items-center gap-2">
                  <button
                    type="button"
                    data-testid="replace-slack-webhook-btn"
                    disabled={slackBusy}
                    onClick={() => setSlackEditing(true)}
                    className="rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/5 disabled:opacity-60"
                  >
                    Replace
                  </button>
                  <button
                    type="button"
                    data-testid="remove-slack-webhook-btn"
                    disabled={slackBusy}
                    onClick={() => saveSlackWebhook("")}
                    className="rounded-md border border-helm-line text-helm-muted text-sm px-4 py-2.5 hover:bg-helm-fg/5 disabled:opacity-60"
                  >
                    {slackBusy ? "Removing…" : "Remove"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <label className="text-xs text-helm-muted block mt-3">
                  Incoming webhook URL
                  <input
                    data-testid="slack-webhook-input"
                    value={slackUrl}
                    onChange={(e) => setSlackUrl(e.target.value)}
                    placeholder="https://hooks.slack.com/services/…"
                    autoComplete="off"
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                  />
                </label>
                <div className="mt-4 flex items-center gap-2">
                  <button
                    type="button"
                    data-testid="save-slack-webhook-btn"
                    disabled={slackBusy || !slackUrl.trim()}
                    onClick={() => saveSlackWebhook()}
                    className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
                  >
                    {slackBusy ? "Saving…" : slackBroken ? "Reconnect Slack" : "Save webhook"}
                  </button>
                  {slackEditing && (
                    <button
                      type="button"
                      onClick={() => { setSlackEditing(false); setSlackUrl(""); }}
                      className="rounded-md border border-helm-line text-helm-muted text-sm px-4 py-2.5 hover:bg-helm-fg/5"
                    >
                      Cancel
                    </button>
                  )}
                  {slackBroken && slackConfigured && (
                    <button
                      type="button"
                      data-testid="remove-slack-webhook-btn"
                      disabled={slackBusy}
                      onClick={() => saveSlackWebhook("")}
                      className="rounded-md border border-helm-line text-helm-muted text-sm px-4 py-2.5 hover:bg-helm-fg/5 disabled:opacity-60"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </>
            )}
          </GlassCard>
        )}
        {connectable.map((it) => (
          <IntegrationCard
            key={it.id}
            it={it}
            canManage={data.can_manage}
            canConnectGoogle={data.can_connect_google !== false}
            canUseConnection={Boolean(data.can_use_connection?.[it.provider ?? it.id])}
            onConnect={oauthConnect}
            onDisconnect={oauthDisconnect}
            onSync={syncAccounting}
            onNavigate={(route) => navigate(route)}
            syncingProvider={syncingProvider}
          />
        ))}
      </div>

      {roadmap.length > 0 && (
        <>
          <h2 className="text-[11px] font-mono uppercase tracking-[0.2em] text-helm-muted mb-3">Coming soon</h2>
          <p className="text-sm text-helm-muted mb-4 max-w-2xl">More connections on the way, with engineering tools next.</p>
          <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
            {roadmap.map((it) => (
              <IntegrationCard
                key={it.id}
                it={it}
                canManage={data.can_manage}
                canConnectGoogle={data.can_connect_google !== false}
                canUseConnection={Boolean(data.can_use_connection?.[it.provider ?? it.id])}
                onConnect={oauthConnect}
                onDisconnect={oauthDisconnect}
                onSync={syncAccounting}
                onNavigate={(route) => navigate(route)}
                syncingProvider={syncingProvider}
              />
            ))}
          </div>
        </>
      )}

      {sapModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" data-testid="sap-b1-connect-modal">
          <GlassCard className="w-full max-w-md p-5">
            <h3 className="text-helm-fg font-medium text-lg">Connect SAP Business One</h3>
            <p className="text-sm text-helm-muted mt-1 leading-relaxed">
              Enter your Service Layer URL and company login. Trenston encrypts these credentials and syncs A/R + A/P invoices into Financials.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-mono uppercase tracking-wide text-helm-muted">
                Service Layer URL
                <input
                  data-testid="sap-b1-url"
                  value={sapForm.service_layer_url}
                  onChange={(e) => setSapForm((f) => ({ ...f, service_layer_url: e.target.value }))}
                  placeholder="https://host:50000/b1s/v1"
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
              <label className="block text-xs font-mono uppercase tracking-wide text-helm-muted">
                Company database
                <input
                  data-testid="sap-b1-company-db"
                  value={sapForm.company_db}
                  onChange={(e) => setSapForm((f) => ({ ...f, company_db: e.target.value }))}
                  placeholder="SBODEMOUS"
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
              <label className="block text-xs font-mono uppercase tracking-wide text-helm-muted">
                Username
                <input
                  data-testid="sap-b1-username"
                  value={sapForm.username}
                  onChange={(e) => setSapForm((f) => ({ ...f, username: e.target.value }))}
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
              <label className="block text-xs font-mono uppercase tracking-wide text-helm-muted">
                Password
                <input
                  type="password"
                  data-testid="sap-b1-password"
                  value={sapForm.password}
                  onChange={(e) => setSapForm((f) => ({ ...f, password: e.target.value }))}
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                data-testid="sap-b1-cancel"
                onClick={() => setSapModalOpen(false)}
                className="rounded-md border border-helm-line text-helm-muted text-sm px-3 py-2 hover:bg-helm-fg/5"
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="sap-b1-submit"
                disabled={sapBusy}
                onClick={connectSapB1}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover disabled:opacity-60"
              >
                {sapBusy ? "Connecting…" : "Connect"}
              </button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
