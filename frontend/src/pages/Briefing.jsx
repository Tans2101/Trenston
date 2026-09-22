import { useEffect, useState } from "react";
import { toast } from "sonner";
import { toastError } from "@/lib/notify";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, Send, UserCheck, Users, CheckCircle2, Circle, Mail, Plug, X, Eraser } from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { hasPerm } from "@/lib/access";
import { GlassCard, ErrorScreen, PageHeaderSkeleton, SkeletonKPIRow, SkeletonCardList } from "@/components/kit";
import { cn } from "@/lib/utils";
import Onboarding from "@/pages/Onboarding";
import { dayPartGreeting } from "@/lib/greeting";
import BentoGrid from "@/components/kokonutui/bento-grid";
import AiSummaryMeta from "@/components/AiSummaryMeta";
import BriefingCockpitHero from "@/components/BriefingCockpitHero";
import { toastGmailDraftNote } from "@/components/CirNote";

const toneDot = { positive: "bg-helm-status-positive", negative: "bg-helm-status-negative", neutral: "bg-helm-muted" };

function BriefLabel({ children, className }) {
  return (
    <h2 className={cn("text-sm font-medium tracking-tight text-helm-fg", className)}>
      {children}
    </h2>
  );
}

export default function Briefing() {
  const { user } = useAuth();
  const canManageIntegrations = hasPerm(user, "integrations:manage");
  const { data, loading: briefingLoading, error: briefingError, reload: reloadBriefing, setData } = useFetch("/briefing");
  const { data: company, loading: companyLoading, error: companyError, reload: reloadCompany } = useCompanyQuery();
  const { data: checklist, reload: reloadChecklist, setData: setChecklist } = useFetch("/onboarding/checklist");
  const {
    data: integPrompt,
    reload: reloadIntegPrompt,
    setData: setIntegPrompt,
  } = useFetch(canManageIntegrations ? "/onboarding/integrations-prompt" : null);
  const [genLoading, setGenLoading] = useState(false);
  const [delegateBusy, setDelegateBusy] = useState(null);
  const [dismissBusy, setDismissBusy] = useState(false);
  const [integDismissBusy, setIntegDismissBusy] = useState(false);
  const [sampleBannerDismissed, setSampleBannerDismissed] = useState(false);
  const [clearSampleBusy, setClearSampleBusy] = useState(false);
  const navigate = useNavigate();

  const canClearSample = hasPerm(user, "workspace:edit");
  const sampleBannerKey = company?.workspace_id
    ? `helm-sample-banner-${company.workspace_id}`
    : null;

  useEffect(() => {
    if (!sampleBannerKey) return;
    try {
      setSampleBannerDismissed(window.localStorage.getItem(sampleBannerKey) === "1");
    } catch {
      setSampleBannerDismissed(false);
    }
  }, [sampleBannerKey]);

  const loading = briefingLoading || companyLoading;
  const error = briefingError || companyError;
  const reload = () => { reloadBriefing(); reloadCompany(); };

  if (loading) {
    return (
      <div className="max-w-6xl">
        <PageHeaderSkeleton />
        <BriefingCockpitHero loading />
        <SkeletonKPIRow count={4} />
        <div className="grid lg:grid-cols-3 gap-4">
          <SkeletonCardList count={3} />
          <SkeletonCardList count={3} />
          <SkeletonCardList count={3} />
        </div>
      </div>
    );
  }
  if (error || !data || !company) {
    return (
      <ErrorScreen
        label="Could not load briefing"
        message={fetchErrorMessage(error, "Briefing data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }
  if (company.onboarding_done === false) return <Onboarding />;

  const canGenerateAi = Boolean(data.can_generate_ai_summary);

  const generate = async () => {
    if (genLoading || !canGenerateAi) return;
    setGenLoading(true);
    try {
      const { data: res } = await api.post("/briefing/generate");
      setData((prev) => ({
        ...(prev || {}),
        ai_summary: res.ai_summary,
        data_as_of: res.data_as_of || prev?.data_as_of,
        ai_summary_data_as_of: res.data_as_of || prev?.ai_summary_data_as_of,
      }));
      toast.success("Briefing updated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not generate briefing");
    } finally {
      setGenLoading(false);
    }
  };

  const assignDelegate = async (id) => {
    setDelegateBusy(id);
    try {
      await api.post(`/delegates/suggestions/${id}/assign`);
      toast.success(company?.has_team === false ? "Saved for later" : "Task created");
      reloadBriefing();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save task");
    } finally {
      setDelegateBusy(null);
    }
  };

  const dismissDelegate = async (id) => {
    setDelegateBusy(id);
    try {
      await api.post(`/delegates/suggestions/${id}/dismiss`);
      toast.success("Suggestion dismissed");
      reloadBriefing();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not dismiss");
    } finally {
      setDelegateBusy(null);
    }
  };

  const dismissChecklist = async () => {
    if (dismissBusy) return;
    setDismissBusy(true);
    try {
      await api.post("/onboarding/checklist/dismiss");
      setChecklist((prev) => (prev ? { ...prev, dismissed: true } : prev));
      toast.success("Setup checklist hidden");
      reloadChecklist();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not hide checklist");
    } finally {
      setDismissBusy(false);
    }
  };

  const dismissIntegrationsPrompt = async () => {
    if (integDismissBusy) return;
    setIntegDismissBusy(true);
    try {
      await api.post("/onboarding/integrations-prompt/dismiss");
      setIntegPrompt((prev) => (prev ? { ...prev, dismissed: true } : prev));
      toast.success("Integrations prompt hidden");
      reloadIntegPrompt();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not hide prompt");
    } finally {
      setIntegDismissBusy(false);
    }
  };

  const dismissSampleBanner = () => {
    setSampleBannerDismissed(true);
    if (!sampleBannerKey) return;
    try {
      window.localStorage.setItem(sampleBannerKey, "1");
    } catch {
      // Banner stays hidden for this session only.
    }
  };

  const clearSampleFromHome = async () => {
    if (clearSampleBusy || !canClearSample) return;
    if (!window.confirm("Remove all sample data and start fresh? Billing and integrations stay connected.")) {
      return;
    }
    setClearSampleBusy(true);
    try {
      await api.post("/workspace/clear-sample");
      toast.success("Sample data removed. You're starting fresh.");
      if (sampleBannerKey) {
        try {
          window.localStorage.removeItem(sampleBannerKey);
        } catch {
          // ignore
        }
      }
      window.location.href = "/app";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not remove sample data");
      setClearSampleBusy(false);
    }
  };

  const { greeting: timeGreet, briefingLabel } = dayPartGreeting();
  const greeting = `${timeGreet}, ${company?.ceo_name?.split(" ")[0] || "CEO"}`;
  const doneCount = checklist?.steps?.filter((s) => s.done).length ?? 0;
  const stepCount = checklist?.steps?.length ?? 0;
  const showChecklist = Boolean(checklist && !checklist.complete && !checklist.dismissed);
  const showIntegrationsPrompt = Boolean(
    canManageIntegrations
    && integPrompt
    && integPrompt.connected_count === 0
    && !integPrompt.dismissed,
  );
  const showSampleBanner = Boolean(
    canClearSample
    && company?.template === "sample"
    && !sampleBannerDismissed,
  );
  const metrics = data.metrics || [];
  const whatChanged = data.what_changed || [];
  const whatToDecide = data.what_to_decide || [];
  const whatToDelegate = data.what_to_delegate || [];
  const hasTeam = company?.has_team !== false;
  const setupHeadline = /start by logging your financials/i.test(data.headline || "");
  const financeMetrics = metrics.filter((m) => /mrr|revenue|^burn|runway/i.test(m.label || ""));
  const allFinanceMissing =
    financeMetrics.length > 0 && financeMetrics.every((m) => m.missing);
  // Hero empty-state card already covers the CTA when every finance KPI is missing.
  const showSetupPrompt = setupHeadline && !allFinanceMissing;

  return (
    <div className="max-w-6xl">
      <header className="mb-8 fade-up">
        <p className="text-xs uppercase tracking-[0.18em] text-helm-muted mb-3">
          {data.date} · {briefingLabel}
        </p>
        <h1 className="font-display text-3xl md:text-4xl font-normal tracking-tight text-helm-fg">{greeting}.</h1>
        {showSetupPrompt ? (
          <div
            className="mt-5 rounded-xl border border-helm-gold/35 bg-helm-gold/10 p-5 max-w-2xl"
            data-testid="briefing-setup-prompt"
          >
            <p className="font-display text-lg text-helm-fg tracking-tight">Ready when you are</p>
            <p className="mt-1.5 text-sm text-helm-muted leading-relaxed">
              Log a financial entry and invite your team so Briefing can show real numbers instead of placeholders.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="briefing-setup-financials"
                onClick={() => navigate("/app/financials#log-mrr")}
                className="inline-flex items-center gap-2 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover transition-colors"
              >
                Add financial entry
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
              {hasTeam ? (
                <button
                  type="button"
                  data-testid="briefing-setup-people"
                  onClick={() => navigate("/app/people")}
                  className="inline-flex items-center gap-2 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/[0.04] transition-colors"
                >
                  Invite your team
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </button>
              ) : null}
            </div>
          </div>
        ) : setupHeadline ? null : (
          <p className="text-helm-muted mt-3 max-w-2xl text-base leading-relaxed">{data.headline}</p>
        )}
      </header>

      <BriefingCockpitHero metrics={metrics} decisions={whatToDecide} />

      {showSampleBanner && (
        <section
          className="mb-6 fade-up rounded-xl border border-helm-gold/30 bg-helm-card p-5 shadow-sm"
          data-testid="sample-data-banner"
        >
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-helm-gold/12 border border-helm-gold/25 shrink-0">
              <Eraser className="w-4 h-4 text-helm-gold" />
            </span>
            <div className="min-w-0 flex-1">
              <BriefLabel>Exploring with sample data</BriefLabel>
              <p className="mt-1.5 text-sm text-helm-muted leading-relaxed">
                Northwind Robotics is loaded so you can click around. When you&apos;re ready, remove it and start with your own company data — or keep exploring and clear it later in Settings.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  data-testid="sample-banner-clear-btn"
                  onClick={clearSampleFromHome}
                  disabled={clearSampleBusy}
                  className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3.5 py-2 hover:bg-helm-gold-hover disabled:opacity-60"
                >
                  {clearSampleBusy ? "Removing…" : "Remove sample & start fresh"}
                </button>
                <button
                  type="button"
                  data-testid="sample-banner-settings-btn"
                  onClick={() => navigate("/app/settings#clear-sample")}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3.5 py-2 hover:bg-helm-fg/[0.04]"
                >
                  Settings
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  data-testid="dismiss-sample-banner"
                  onClick={dismissSampleBanner}
                  className="text-xs text-helm-muted underline underline-offset-2 hover:text-helm-fg transition-colors ml-1"
                >
                  Hide for now
                </button>
              </div>
            </div>
            <button
              type="button"
              data-testid="dismiss-sample-banner-x"
              onClick={dismissSampleBanner}
              className="text-helm-muted hover:text-helm-fg transition-colors p-0.5 shrink-0"
              aria-label="Hide sample data banner"
              title="Hide"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </section>
      )}

      {showChecklist && (
        <section className="mb-6 fade-up rounded-xl border border-helm-line bg-helm-card p-5 shadow-sm" data-testid="onboarding-checklist">
          <div className="flex items-center gap-3 mb-4">
            <BriefLabel>Finish setting up</BriefLabel>
            <span className="ml-auto text-xs text-helm-muted tabular-nums">{doneCount}/{stepCount}</span>
            <button
              type="button"
              data-testid="dismiss-setup-checklist"
              onClick={dismissChecklist}
              disabled={dismissBusy}
              className="text-helm-muted hover:text-helm-fg transition-colors disabled:opacity-50 p-0.5"
              aria-label="Hide setup checklist"
              title="Hide"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="h-1 rounded-full bg-helm-fg/[0.06] mb-4 overflow-hidden">
            <div
              className="h-full rounded-full bg-helm-gold/70 transition-all"
              style={{ width: stepCount ? `${(doneCount / stepCount) * 100}%` : "0%" }}
            />
          </div>
          <div className="grid sm:grid-cols-2 gap-2">
            {checklist.steps.map((s) => (
              <button
                key={s.id}
                data-testid={`setup-${s.id}`}
                onClick={() => navigate(s.route)}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors",
                  s.done
                    ? "border-helm-status-positive/35 bg-helm-status-positive/12"
                    : "border-helm-line bg-helm-fg/[0.02] hover:border-helm-fg/20"
                )}
              >
                {s.done
                  ? <CheckCircle2 className="w-4 h-4 text-helm-status-positive shrink-0" />
                  : <Circle className="w-4 h-4 text-helm-muted shrink-0" />}
                <span className={cn("text-sm", s.done ? "text-helm-muted line-through" : "text-helm-fg")}>
                  {s.label}
                </span>
                {!s.done && <ArrowUpRight className="w-3.5 h-3.5 text-helm-muted ml-auto shrink-0" />}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-helm-muted">
            Completes on its own when every step is done. Or{" "}
            <button
              type="button"
              data-testid="dismiss-setup-checklist-text"
              onClick={dismissChecklist}
              disabled={dismissBusy}
              className="underline underline-offset-2 hover:text-helm-fg transition-colors disabled:opacity-50"
            >
              hide this
            </button>
            {" "}anytime.
          </p>
        </section>
      )}

      {showIntegrationsPrompt && (
        <section className="mb-6 fade-up rounded-xl border border-helm-line bg-helm-card p-5 shadow-sm" data-testid="integrations-prompt">
          <div className="flex items-center gap-3 mb-3">
            <BriefLabel>Connect your tools</BriefLabel>
            <button
              type="button"
              data-testid="dismiss-integrations-prompt"
              onClick={dismissIntegrationsPrompt}
              disabled={integDismissBusy}
              className="ml-auto text-helm-muted hover:text-helm-fg transition-colors disabled:opacity-50 p-0.5"
              aria-label="Hide integrations prompt"
              title="Hide"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <p className="text-sm text-helm-muted leading-relaxed mb-4">
            Link Google, QuickBooks, Xero, SAP Business One, HubSpot, or Slack so Briefing and Financials stay current.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              data-testid="integrations-prompt-cta"
              onClick={() => navigate("/app/integrations")}
              className="inline-flex items-center gap-2 rounded-lg border border-helm-line bg-helm-fg/[0.02] px-3 py-2.5 text-sm text-helm-fg hover:border-helm-fg/20 transition-colors"
            >
              <Plug className="w-4 h-4 text-helm-muted shrink-0" />
              Open Integrations
              <ArrowUpRight className="w-3.5 h-3.5 text-helm-muted shrink-0" />
            </button>
            <button
              type="button"
              data-testid="dismiss-integrations-prompt-text"
              onClick={dismissIntegrationsPrompt}
              disabled={integDismissBusy}
              className="text-xs text-helm-muted underline underline-offset-2 hover:text-helm-fg transition-colors disabled:opacity-50"
            >
              not now
            </button>
          </div>
        </section>
      )}

      {metrics.length > 0 && <BentoGrid metrics={metrics} />}

      <section className="mb-6 fade-up rounded-xl border border-helm-line bg-helm-card p-5 md:p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3 mb-3">
          <BriefLabel>Today&apos;s summary</BriefLabel>
          {data.ai_summary && canGenerateAi && (
            <button
              type="button"
              data-testid="generate-briefing-btn"
              onClick={generate}
              disabled={genLoading}
              className="text-xs text-helm-muted hover:text-helm-fg transition-colors disabled:opacity-50"
            >
              {genLoading ? "Updating…" : "Refresh"}
            </button>
          )}
        </div>
        {data.ai_summary ? (
          <>
            <AiSummaryMeta
              asOf={data.data_as_of || data.ai_summary_data_as_of}
              detailHref="/app/decisions"
              detailLabel="Decisions"
              className="mb-3"
            />
            <p className="text-helm-fg leading-relaxed text-[15px] max-w-3xl">{data.ai_summary}</p>
          </>
        ) : canGenerateAi ? (
          <div>
            <p className="text-helm-muted text-sm mb-4 max-w-xl">
              Pull a short plain-language read of what changed, what needs a decision, and what to watch, from your live company data.
            </p>
            <button
              data-testid="generate-briefing-btn"
              onClick={generate}
              disabled={genLoading}
              className="inline-flex items-center gap-2 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-4 py-2 transition-colors hover:bg-helm-gold-hover disabled:opacity-60"
            >
              {genLoading ? "Writing summary…" : "Write today\u2019s summary"}
              {!genLoading && <Send className="w-3.5 h-3.5" />}
            </button>
          </div>
        ) : (
          <p className="text-sm text-helm-muted max-w-xl">
            Ask a workspace owner or executive to write today&apos;s AI summary.
          </p>
        )}
      </section>

      {(data.email_threads?.length > 0 || data.gmail_connected || data.gmail_needs_reconnect) && (
        <GlassCard className="p-5 mb-6 fade-up" data-testid="briefing-email">
          <div className="flex items-center gap-2 mb-4">
            <Mail className="w-4 h-4 text-helm-muted" />
            <BriefLabel>Email</BriefLabel>
            {data.email_threads?.length > 0 && (
              <span className="text-xs tabular-nums text-helm-muted ml-auto">{data.email_threads.length}</span>
            )}
          </div>
          {data.gmail_needs_reconnect && (
            <div className="mb-3 rounded-lg border border-helm-status-warning/35 bg-helm-status-warning/12 p-3">
              <p className="text-sm text-helm-fg leading-relaxed">
                Google is connected for Calendar. Reconnect once to enable Gmail in your briefing.
              </p>
              <button
                type="button"
                data-testid="enable-gmail-btn"
                onClick={() => navigate("/app/integrations")}
                className="mt-2 text-xs text-helm-gold hover:text-helm-gold-hover"
              >
                Enable Gmail →
              </button>
            </div>
          )}
          {data.email_threads?.length > 0 ? (
            <div className="space-y-3">
              {data.email_threads.map((t, i) => (
                <div
                  key={t.id || i}
                  data-testid={`email-thread-${i}`}
                  className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm text-helm-fg leading-snug truncate">{t.subject}</p>
                      <p className="text-xs text-helm-muted mt-1 truncate">
                        {t.sender}{t.sender_email ? ` · ${t.sender_email}` : ""}
                      </p>
                    </div>
                    <a
                      href={t.thread_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-helm-muted hover:text-helm-muted shrink-0"
                      title="Open in Gmail"
                    >
                      <ArrowUpRight className="w-4 h-4" />
                    </a>
                  </div>
                  {t.snippet && (
                    <p className="text-xs text-helm-muted mt-2 leading-relaxed line-clamp-2">{t.snippet}</p>
                  )}
                  {data.gmail_compose && (
                    <button
                      type="button"
                      data-testid={`gmail-draft-${i}`}
                      onClick={async () => {
                        try {
                          const { data: res } = await api.post("/integrations/google/gmail-draft", {
                            thread_id: t.id,
                            to_email: t.sender_email || "",
                            subject: t.subject || "",
                            snippet: t.snippet || "",
                          });
                          toastGmailDraftNote({
                            recipient: t.sender || t.sender_email,
                            url: res?.url,
                            subject: t.subject,
                          });
                        } catch (e) {
                          toastError(e, "Reconnect Google to create drafts");
                        }
                      }}
                      className="mt-2 text-xs text-helm-gold hover:text-helm-gold-hover"
                    >
                      Draft reply in Gmail
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : data.gmail_connected ? (
            <p className="text-sm text-helm-muted leading-relaxed">
              No important threads in the last two weeks. Starred or Gmail-important mail will show here.
            </p>
          ) : null}
        </GlassCard>
      )}

      <div className="grid lg:grid-cols-3 gap-4">
        <GlassCard className="p-5 fade-up">
          <BriefLabel className="mb-4">What changed</BriefLabel>
          <div className="space-y-4">
            {whatChanged.length === 0 && (
              <p className="text-sm text-helm-muted leading-relaxed">Nothing new logged yet.</p>
            )}
            {whatChanged.map((c, i) => (
              <div key={i} className="flex gap-3" data-testid={`changed-${i}`}>
                <span className={cn("mt-1.5 w-1.5 h-1.5 rounded-full shrink-0", toneDot[c.tone])} />
                <div>
                  <p className="text-sm text-helm-fg leading-snug">{c.title}</p>
                  <p className="text-xs text-helm-muted mt-1 leading-relaxed">{c.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard className="p-5 fade-up">
          <div className="flex items-center justify-between mb-4">
            <BriefLabel>What to decide</BriefLabel>
            <span className="text-xs tabular-nums text-helm-muted">{whatToDecide.length}</span>
          </div>
          <div className="space-y-3">
            {whatToDecide.length === 0 && (
              <p className="text-sm text-helm-muted leading-relaxed">No open decisions. Log one when something needs a call.</p>
            )}
            {whatToDecide.map((d) => (
              <button
                key={d.id}
                onClick={() => navigate("/app/decisions")}
                data-testid={`decide-${d.id}`}
                className="w-full text-left rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3 transition-colors hover:border-helm-fg/15 hover:bg-helm-fg/[0.04] group"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-helm-fg leading-snug">{d.title}</p>
                  <ArrowUpRight className="w-4 h-4 text-helm-muted group-hover:text-helm-muted shrink-0" />
                </div>
                <p className="text-xs text-helm-muted mt-1 leading-relaxed">{d.detail}</p>
                <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                  <span
                    className={cn(
                      "inline-block text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded",
                      d.urgency === "high" ? "text-helm-status-negative bg-helm-status-negative/12" : "text-helm-fg bg-helm-status-warning/12"
                    )}
                  >
                    {d.urgency} priority
                  </span>
                  {d.source === "ai_suggested" && (
                    <span className="inline-block text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded text-helm-muted bg-helm-fg/[0.04]">
                      {d.confidence_unavailable || d.confidence == null
                        ? "Suggested (confidence unavailable)"
                        : `Suggested · ${d.confidence}%`}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </GlassCard>

        <GlassCard className="p-5 fade-up" data-testid={hasTeam ? "briefing-handoff-column" : "briefing-later-column"}>
          <div className="flex items-center justify-between mb-4">
            <BriefLabel>{hasTeam ? "What to hand off" : "Flag for later"}</BriefLabel>
            <button
              type="button"
              onClick={() => navigate("/app/tasks")}
              className="text-[11px] font-mono uppercase tracking-wider text-helm-muted hover:text-helm-gold"
            >
              Open Tasks
            </button>
          </div>
          <div className="space-y-3">
            {whatToDelegate.length === 0 && (
              <p className="text-sm text-helm-muted leading-relaxed">
                {hasTeam
                  ? "No handoffs suggested. Overdue work will show up here."
                  : "Nothing flagged. Overdue work will show up here when you have time."}
              </p>
            )}
            {whatToDelegate.map((d, i) => (
              <div key={d.id || i} className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3" data-testid={`delegate-${d.id || i}`}>
                <button
                  type="button"
                  onClick={() => navigate("/app/tasks")}
                  className="w-full text-left group"
                >
                  <p className="text-sm text-helm-fg leading-snug group-hover:text-helm-gold">{d.title}</p>
                  <p className="text-xs text-helm-muted mt-1 leading-relaxed">{d.detail}</p>
                </button>
                {hasTeam && !d.personal && (
                  <div className="flex items-center gap-1.5 mt-2 text-helm-muted">
                    <UserCheck className="w-3.5 h-3.5" />
                    <span className="text-xs">{d.owner || d.suggested_owner_name}</span>
                  </div>
                )}
                {d.id && (
                  <div className="flex gap-2 mt-3">
                    <button
                      data-testid={hasTeam && !d.personal ? `assign-delegate-${d.id}` : `save-later-${d.id}`}
                      disabled={delegateBusy === d.id}
                      onClick={() => assignDelegate(d.id)}
                      className="flex-1 rounded-md bg-helm-gold text-helm-navy text-xs font-medium py-1.5 hover:bg-helm-gold-hover disabled:opacity-50"
                    >
                      {hasTeam && !d.personal ? "Assign as task" : "Save for later"}
                    </button>
                    <button
                      data-testid={`dismiss-delegate-${d.id}`}
                      disabled={delegateBusy === d.id}
                      onClick={() => dismissDelegate(d.id)}
                      className="rounded-md border border-helm-line text-helm-muted text-xs px-2 py-1.5 hover:bg-helm-fg/5 disabled:opacity-50"
                    >
                      Dismiss
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {data.team_updates && data.team_updates.length > 0 && (
        <GlassCard className="p-5 mt-4 fade-up" data-testid="briefing-team-updates">
          <div className="flex items-center gap-2 mb-4">
            <Users className="w-4 h-4 text-helm-muted" />
            <BriefLabel>Today&apos;s team updates</BriefLabel>
            <span className="text-xs tabular-nums text-helm-muted ml-auto">{data.team_updates.length}</span>
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            {data.team_updates.map((u, i) => (
              <div key={i} className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3" data-testid={`team-update-${i}`}>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-helm-fg">{u.user_name}</span>
                  {u.blocker && (
                    <span className="text-[10px] text-helm-fg bg-helm-status-warning/12 rounded px-1.5 py-0.5 uppercase tracking-wide">
                      Blocked
                    </span>
                  )}
                  <span className="text-[10px] text-helm-muted ml-auto">{u.ago}</span>
                </div>
                <p className="text-xs text-helm-muted mt-1.5 leading-relaxed">{u.text}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
