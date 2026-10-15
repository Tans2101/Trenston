import { useMemo, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Plus, Trash2, X, Zap } from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useAuth } from "@/context/AuthContext";
import NoAccess from "@/components/NoAccess";
import { api, apiErrorMessage } from "@/lib/api";
import {
  PageHeader, GlassCard, SectionLabel, ErrorScreen, ConfirmDialog, SkeletonCardList,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import {
  SEVERITY_LABEL, describeAction, describeTrigger, ruleBodyFromForm, timeAgo,
} from "@/lib/automationsCopy";

const INPUT = "w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg";
const LABEL = "text-[10px] font-mono uppercase tracking-wide text-helm-muted";

const SEVERITY_CLASS = {
  high: "bg-helm-status-negative/12 text-helm-fg border-helm-status-negative/35",
  medium: "bg-helm-status-warning/12 text-helm-fg border-helm-status-warning/35",
  low: "bg-helm-muted/12 text-helm-fg border-helm-muted/35",
};

function SeverityBadge({ severity }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide border",
        SEVERITY_CLASS[severity] || SEVERITY_CLASS.low,
      )}
    >
      {SEVERITY_LABEL[severity] || severity}
    </span>
  );
}

function emptyForm(catalog) {
  return {
    name: "",
    triggerKind: "signal",
    signalType: catalog?.signals?.[0]?.type || "overdue_task",
    minSeverity: "low",
    metric: catalog?.metrics?.[0]?.metric || "runway_months_below",
    metricValue: "6",
    actionType: "create_task",
    taskTitle: "Follow up: {summary}",
    priority: "Medium",
    dueDays: "2",
    assigneeId: "",
  };
}

function Switch({ checked, onChange, label, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors disabled:opacity-50",
        checked ? "bg-helm-gold border-helm-gold" : "bg-helm-fg/10 border-helm-line",
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 rounded-full bg-helm-card shadow transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-[3px]",
        )}
      />
    </button>
  );
}

export default function Automations() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner" || user?.pack === "owner";
  const { data, loading, error, reload } = useFetch(isOwner ? "/automations" : null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [building, setBuilding] = useState(false);
  const [form, setForm] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const rules = useMemo(() => data?.rules || [], [data?.rules]);
  const catalog = data?.catalog;
  const members = useMemo(() => data?.members || [], [data?.members]);
  const atLimit = rules.length >= (data?.max_rules || 25);

  const run = async (fn, failMessage) => {
    setBusy(true);
    try {
      await fn();
      await reload();
      return true;
    } catch (e) {
      toast.error(apiErrorMessage(e, failMessage));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const addTemplate = (t) => run(async () => {
    await api.post("/automations", { name: t.name, enabled: true, trigger: t.trigger, action: t.action });
    toast.success(`Added "${t.name}"`);
  }, "Could not add the rule");

  const toggle = (rule) => run(
    () => api.patch(`/automations/${rule.id}`, { enabled: !rule.enabled }),
    "Could not update the rule",
  );

  const remove = async () => {
    const rule = confirmDelete;
    const ok = await run(() => api.delete(`/automations/${rule.id}`), "Could not delete the rule");
    if (ok) {
      toast.success("Rule deleted");
      setConfirmDelete(null);
    }
  };

  const dismiss = (alert) => run(
    () => api.post(`/automations/alerts/${alert.id}/dismiss`),
    "Could not dismiss the alert",
  );

  const runNow = async () => {
    setRunning(true);
    try {
      const { data: res } = await api.post("/automations/run");
      await reload();
      const bits = [];
      if (res.tasks) bits.push(`${res.tasks} task${res.tasks === 1 ? "" : "s"} created`);
      if (res.anomalies?.new) bits.push(`${res.anomalies.new} new alert${res.anomalies.new === 1 ? "" : "s"}`);
      toast.success(bits.length ? bits.join(", ") : "Checked. Nothing new.");
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not run the checks"));
    } finally {
      setRunning(false);
    }
  };

  const openBuilder = () => {
    setForm(emptyForm(catalog));
    setBuilding(true);
  };

  const submitForm = async (e) => {
    e.preventDefault();
    const ok = await run(async () => {
      await api.post("/automations", ruleBodyFromForm(moneyRule ? { ...form, assigneeId: "" } : form));
      toast.success("Rule added");
    }, "Could not add the rule");
    if (ok) setBuilding(false);
  };

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  // Money figures can end up in a task title, so those rules stay with the owner.
  const moneyRule = Boolean(form) && (
    form.triggerKind === "metric"
    || Boolean((catalog?.signals || []).find((s) => s.type === form.signalType)?.financial)
  );

  if (!isOwner) {
    return <NoAccess title="Automations" who="Only the workspace owner sets up automations, because rules create tasks and read money signals." />;
  }
  if (loading && !data) {
    return (
      <div data-testid="automations-page">
        <PageHeader title="Automations" subtitle="Rules that watch your company for you." />
        <SkeletonCardList count={3} />
      </div>
    );
  }
  if (error && !data) {
    return <ErrorScreen label="Automations" message={fetchErrorMessage(error)} onRetry={reload} />;
  }

  const alerts = data?.alerts || [];
  const events = data?.events || [];
  const templates = data?.templates || [];

  return (
    <div data-testid="automations-page">
      <PageHeader
        title="Automations"
        subtitle="Set a rule once and Trenston watches your company for you, then creates the task or shows the alert. It only works inside your workspace and uses no AI, so results are always the same for the same data."
        action={(
          <button
            type="button"
            data-testid="automations-run-now"
            onClick={runNow}
            disabled={running}
            className="rounded-md border border-helm-line px-3 py-2 text-sm text-helm-fg hover:bg-helm-fg/[0.04] disabled:opacity-50"
          >
            {running ? "Checking…" : "Run checks now"}
          </button>
        )}
      />

      {data?.can_see_finance && (
        <section className="mb-10" data-testid="automations-alerts">
          <SectionLabel>Anomaly alerts</SectionLabel>
          {alerts.length === 0 ? (
            <GlassCard className="p-5 text-sm text-helm-muted">
              Nothing unusual found. Trenston checks your finance ledger once a day for duplicate entries,
              unusually large expenses, and revenue that drops or stops.
            </GlassCard>
          ) : (
            <div className="space-y-3">
              {alerts.map((a) => (
                <GlassCard key={a.id} className="p-4 flex items-start gap-3" data-testid={`anomaly-${a.id}`}>
                  <AlertTriangle className="w-4 h-4 mt-0.5 text-helm-gold shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm text-helm-fg font-medium">{a.title}</p>
                      <SeverityBadge severity={a.severity} />
                    </div>
                    <p className="text-sm text-helm-muted mt-1">{a.detail}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => dismiss(a)}
                    disabled={busy}
                    className="text-xs text-helm-muted hover:text-helm-fg underline shrink-0"
                  >
                    Dismiss
                  </button>
                </GlassCard>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="mb-10" data-testid="automations-rules">
        <div className="flex items-center justify-between mb-3">
          <SectionLabel>Your rules ({rules.length}/{data?.max_rules || 25})</SectionLabel>
          <button
            type="button"
            data-testid="automations-new-rule"
            onClick={openBuilder}
            disabled={atLimit}
            className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
          >
            <Plus className="w-4 h-4" /> Build your own
          </button>
        </div>
        {atLimit && (
          <p className="text-xs text-helm-muted mb-3" data-testid="automations-limit-note">
            Your plan includes up to {data?.max_rules} rules. Delete one, or upgrade under Billing, to add more.
          </p>
        )}
        {rules.length === 0 ? (
          <GlassCard className="p-5 text-sm text-helm-muted">
            No rules yet. Add one of the starter rules below, or build your own.
          </GlassCard>
        ) : (
          <div className="space-y-3">
            {rules.map((r) => (
              <GlassCard key={r.id} className={cn("p-4", !r.enabled && "opacity-60")} data-testid={`rule-${r.id}`}>
                <div className="flex items-start gap-3">
                  <Switch
                    checked={Boolean(r.enabled)}
                    onChange={() => toggle(r)}
                    disabled={busy}
                    label={`${r.enabled ? "Turn off" : "Turn on"} ${r.name}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-helm-fg font-medium">{r.name}</p>
                    <p className="text-sm text-helm-muted mt-1">
                      <span className="text-helm-fg">When</span> {describeTrigger(r.trigger, catalog).toLowerCase()}
                      <span className="text-helm-fg">, then</span> {describeAction(r.action, members).toLowerCase()}.
                    </p>
                    <p className="text-xs text-helm-muted mt-2">
                      Ran {r.fire_count || 0} time{r.fire_count === 1 ? "" : "s"} · last {timeAgo(r.last_fired_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label={`Delete ${r.name}`}
                    onClick={() => setConfirmDelete(r)}
                    className="text-helm-muted hover:text-helm-status-negative"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </section>

      <section className="mb-10" data-testid="automations-templates">
        <SectionLabel>Start with a ready-made rule</SectionLabel>
        <div className="grid gap-3 md:grid-cols-2">
          {templates.map((t) => (
            <GlassCard key={t.id} className="p-4 flex flex-col gap-3" data-testid={`template-${t.id}`}>
              <div>
                <p className="text-sm text-helm-fg font-medium flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-helm-gold" /> {t.name}
                </p>
                <p className="text-sm text-helm-muted mt-1">{t.blurb}</p>
              </div>
              <button
                type="button"
                onClick={() => addTemplate(t)}
                disabled={busy || atLimit}
                className="self-start rounded-md border border-helm-line px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-fg/[0.04] disabled:opacity-50"
              >
                Add this rule
              </button>
            </GlassCard>
          ))}
        </div>
      </section>

      <section className="mb-10" data-testid="automations-activity">
        <SectionLabel>Recent activity</SectionLabel>
        {events.length === 0 ? (
          <GlassCard className="p-5 text-sm text-helm-muted">
            When a rule fires, it shows up here. Trenston checks every 15 minutes.
          </GlassCard>
        ) : (
          <GlassCard className="divide-y divide-helm-line">
            {events.map((ev) => (
              <div key={ev.id} className="px-4 py-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-helm-fg">{ev.summary}</p>
                  <p className="text-xs text-helm-muted mt-0.5">
                    {ev.rule_name}
                    {ev.task_id ? ` · task created for ${ev.assignee_name || "a teammate"}` : " · alert"}
                  </p>
                </div>
                <span className="text-xs text-helm-muted shrink-0">{timeAgo(ev.created_at)}</span>
              </div>
            ))}
          </GlassCard>
        )}
      </section>

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="Delete this rule?"
        description={confirmDelete ? `"${confirmDelete.name}" will stop running. Tasks it already created stay.` : ""}
        confirmLabel="Delete rule"
        busy={busy}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={remove}
        testId="delete-rule-confirm"
      />

      {building && form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setBuilding(false)} />
          <form
            onSubmit={submitForm}
            role="dialog"
            aria-modal="true"
            aria-label="Build a rule"
            onKeyDown={(e) => { if (e.key === "Escape" && !busy) setBuilding(false); }}
            className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-md border border-helm-line bg-helm-card p-5 space-y-4"
            data-testid="rule-builder"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm text-helm-fg font-medium">Build a rule</p>
              <button type="button" onClick={() => setBuilding(false)} className="text-helm-muted hover:text-helm-fg" aria-label="Close">
                <X className="w-4 h-4" />
              </button>
            </div>

            <label className="block space-y-1">
              <span className={LABEL}>Name</span>
              <input
                data-testid="rule-name"
                className={INPUT}
                value={form.name}
                onChange={(e) => set({ name: e.target.value })}
                placeholder="Late supplier, make a task"
                maxLength={80}
                required
                autoFocus
              />
            </label>

            <div className="space-y-2">
              <span className={LABEL}>When</span>
              <select
                className={INPUT}
                value={form.triggerKind}
                onChange={(e) => set({ triggerKind: e.target.value })}
                aria-label="Trigger type"
              >
                <option value="signal">Something happens in the company</option>
                {(catalog?.metrics || []).length > 0 && <option value="metric">A number crosses a limit</option>}
              </select>
              {form.triggerKind === "signal" ? (
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <select
                    data-testid="rule-signal"
                    className={INPUT}
                    value={form.signalType}
                    onChange={(e) => set({ signalType: e.target.value })}
                    aria-label="What happens"
                  >
                    {(catalog?.signals || []).map((s) => (
                      <option key={s.type} value={s.type}>{s.label}</option>
                    ))}
                  </select>
                  <select
                    className={INPUT}
                    value={form.minSeverity}
                    onChange={(e) => set({ minSeverity: e.target.value })}
                    aria-label="Minimum seriousness"
                  >
                    <option value="low">Any seriousness</option>
                    <option value="medium">Medium or higher</option>
                    <option value="high">High only</option>
                  </select>
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-[1fr_8rem]">
                  <select
                    className={INPUT}
                    value={form.metric}
                    onChange={(e) => set({ metric: e.target.value })}
                    aria-label="Which number"
                  >
                    {(catalog?.metrics || []).map((m) => (
                      <option key={m.metric} value={m.metric}>{m.label}</option>
                    ))}
                  </select>
                  <input
                    data-testid="rule-metric-value"
                    className={INPUT}
                    type="number"
                    min="0"
                    step="any"
                    value={form.metricValue}
                    onChange={(e) => set({ metricValue: e.target.value })}
                    aria-label="Limit"
                    required
                  />
                </div>
              )}
            </div>

            <div className="space-y-2">
              <span className={LABEL}>Then</span>
              <select
                className={INPUT}
                value={form.actionType}
                onChange={(e) => set({ actionType: e.target.value })}
                aria-label="Action"
              >
                <option value="create_task">Create a task</option>
                <option value="alert">Just show it in Recent activity</option>
              </select>
              {form.actionType === "create_task" && (
                <div className="space-y-2">
                  <input
                    data-testid="rule-task-title"
                    className={INPUT}
                    value={form.taskTitle}
                    onChange={(e) => set({ taskTitle: e.target.value })}
                    maxLength={140}
                    aria-label="Task title"
                    required
                  />
                  <p className="text-xs text-helm-muted">
                    Use {"{summary}"} to include what Trenston found, for example "Follow up: {"{summary}"}".
                  </p>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <select className={INPUT} value={form.priority} onChange={(e) => set({ priority: e.target.value })} aria-label="Priority">
                      <option>High</option>
                      <option>Medium</option>
                      <option>Low</option>
                    </select>
                    <select
                      className={INPUT}
                      value={moneyRule ? "" : form.assigneeId}
                      onChange={(e) => set({ assigneeId: e.target.value })}
                      disabled={moneyRule}
                      title={moneyRule ? "Rules on money figures are assigned to you" : undefined}
                      aria-label="Assign to"
                    >
                      <option value="">Assign to me</option>
                      {members.map((m) => (
                        <option key={m.user_id} value={m.user_id}>{m.name}</option>
                      ))}
                    </select>
                    <label className="flex items-center gap-2 text-xs text-helm-muted">
                      Due in
                      <input
                        className={cn(INPUT, "w-16")}
                        type="number"
                        min="0"
                        max="90"
                        value={form.dueDays}
                        onChange={(e) => set({ dueDays: e.target.value })}
                        aria-label="Due in days"
                      />
                      days
                    </label>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setBuilding(false)} className="rounded-md border border-helm-line px-3 py-2 text-sm text-helm-fg">
                Cancel
              </button>
              <button
                type="submit"
                data-testid="rule-save"
                disabled={busy}
                className="rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-4 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Add rule
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
