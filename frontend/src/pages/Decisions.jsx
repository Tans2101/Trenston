import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Plus, RefreshCw, X, Sparkles } from "lucide-react";

const SUBTITLE = "Open calls, ranked by impact. Trenston drafts suggestions from your data; nothing counts until you confirm it.";
import { AnimatePresence } from "motion/react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useDecisionActions, buildDelegateOptions } from "@/hooks/useDecisionActions";
import { api } from "@/lib/api";
import { AppPageHeader, ListLabel, GlassCard, ErrorScreen, EmptyState, SkeletonCardList } from "@/components/kit";
import DecisionCard, { MetaLine } from "@/components/DecisionCard";
import SuggestionCard from "@/components/SuggestionCard";
import { highlightRecord } from "@/lib/signalRoute";
import {
  isFatalDecisionsLoad,
  isActionableDecision,
  isResolvedDecision,
  sortDecisionsByImpact,
} from "@/lib/decisionsUi";
import { cn } from "@/lib/utils";
import { confirmAction } from "@/components/ConfirmHost";
import RippleDialog from "@/components/RippleDialog";
import { useAuth } from "@/context/AuthContext";
import { baselineReady, changeTone, rippleProjection, runwayChangeLabel } from "@/lib/ripple";

const emptyForm = () => ({ title: "", category: "General", description: "", recommendation: "", due: "", impact: "Medium" });

/** Blank form merged with an optional {title, description, category} prefill from another screen. */
const prefilledForm = (prefill) => {
  const base = emptyForm();
  if (!prefill || typeof prefill !== "object") return base;
  const str = (v) => (typeof v === "string" ? v : "");
  return {
    ...base,
    title: str(prefill.title) || base.title,
    description: str(prefill.description) || base.description,
    category: str(prefill.category) || base.category,
  };
};

export default function Decisions() {
  const { data, loading, error, reload, isFetching } = useFetch("/decisions");
  // Members only needed when the viewer can act (create / delegate).
  const { data: membersData } = useFetch(data?.can_act ? "/members" : null);
  const { busy, act, approveSuggestion, dismissSuggestion } = useDecisionActions(reload);
  const { user } = useAuth();
  // Ripple uses real money figures, so only people with Financials access load it.
  const canSeeFinancials = (user?.granted_sections || []).includes("financials");
  const { data: rippleData, reload: reloadRipple } = useFetch(canSeeFinancials ? "/decisions/ripple" : null);
  const [rippleFor, setRippleFor] = useState(null);
  const rippleChip = (d) => {
    const saved = rippleData?.effects?.[d.id];
    if (!saved || !baselineReady(rippleData?.baseline).ok) return null;
    const p = rippleProjection(rippleData.baseline, saved);
    const label = runwayChangeLabel(p.base.runway, p.after.runway);
    return label ? { label, tone: changeTone(p.base.runway, p.after.runway) } : null;
  };
  const location = useLocation();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [genBusy, setGenBusy] = useState(false);
  const [searchParams] = useSearchParams();
  const focusId = searchParams.get("focus");
  const wantsNew = searchParams.get("new") === "1";
  const highlightedRef = useRef(null);
  const softRefreshToastKey = useRef(null);

  // Open the add form from another screen: state.openAdd / state.prefill, or ?new=1.
  // Waits for data so we know whether this user can log decisions at all.
  useEffect(() => {
    const st = location.state || {};
    if (!st.openAdd && !st.prefill && !wantsNew) return;
    if (!data) return;
    if (data.can_act) {
      setEditing(null);
      setForm(prefilledForm(st.prefill));
      setShowForm(true);
    } else {
      toast.info("Only owners and executives can log decisions.");
    }
    const params = new URLSearchParams(location.search);
    params.delete("new");
    const qs = params.toString();
    navigate(`${location.pathname}${qs ? `?${qs}` : ""}`, { replace: true, state: {} });
  }, [location.state, location.search, location.pathname, wantsNew, data, navigate]);

  // ?focus=<id>: scroll to and flash the decision (pending, resolved, or a suggestion).
  useEffect(() => {
    if (!focusId || !data || highlightedRef.current === focusId) return;
    const known = [...(data.decisions || []), ...(data.suggestions || [])].some((x) => String(x.id) === focusId);
    if (!known) {
      // A just-created decision may not be in the cached copy yet — wait for
      // the refetch before saying it's gone.
      if (isFetching) return;
      highlightedRef.current = focusId;
      toast.info("That decision is no longer open. It may have been resolved or removed.");
      return;
    }
    highlightedRef.current = focusId;
    highlightRecord(focusId);
  }, [focusId, data, isFetching]);

  // Only block on first load — keep cached UI when a background refetch fails.
  const showSkeleton = loading && !data;
  const fatalError = isFatalDecisionsLoad({ error, data });
  const softRefreshError = Boolean(error && data);

  useEffect(() => {
    if (!softRefreshError) {
      softRefreshToastKey.current = null;
      return;
    }
    const key = error?.message || error?.code || "soft-refresh";
    if (softRefreshToastKey.current === key) return;
    softRefreshToastKey.current = key;
    toast.error(fetchErrorMessage(error, "Could not refresh decisions. Showing last loaded data."));
  }, [softRefreshError, error]);

  if (showSkeleton) {
    return (
      <div>
        <AppPageHeader title="Decisions" subtitle={SUBTITLE} />
        <SkeletonCardList count={4} />
      </div>
    );
  }
  if (fatalError) {
    return (
      <ErrorScreen
        label="Could not load decisions"
        message={fetchErrorMessage(error, "Decisions data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }
  const canAct = data.can_act;
  const suggestions = sortDecisionsByImpact(data.suggestions || []);
  const decisions = sortDecisionsByImpact(data.decisions || []);
  const { selfMember, delegateMembers, selfLabel, selfOptionLabel } = buildDelegateOptions(membersData);

  const openAdd = () => { setEditing(null); setForm(emptyForm()); setShowForm(true); };
  const openEdit = (d) => {
    setEditing(d.id);
    setForm({
      title: d.title || "",
      category: d.category || "General",
      description: d.description || "",
      recommendation: d.recommendation || "",
      due: !d.due || d.due === "—" ? "" : d.due,
      impact: d.impact || "Medium",
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.title.trim()) { toast.error("Add a title"); return; }
    setSaving(true);
    // Manual decisions use Impact only — never invent a confidence %. On edit,
    // leave confidence out entirely so an AI estimate on the decision survives.
    const payload = editing ? { ...form } : { ...form, confidence: null };
    try {
      if (editing) { await api.patch(`/decisions/${editing}`, payload); toast.success("Decision updated"); }
      else { await api.post("/decisions", payload); toast.success("Decision added"); }
      setShowForm(false); reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save"); }
    finally { setSaving(false); }
  };

  const del = async (id) => {
    if (!(await confirmAction({ title: "Delete this decision?", confirmLabel: "Delete", destructive: true }))) return;
    try { await api.delete(`/decisions/${id}`); reload(); toast.success("Decision removed"); }
    catch (e) { toast.error("Could not delete"); }
  };

  const regenerate = async () => {
    setGenBusy(true);
    try {
      await api.post("/decisions/generate-suggestions");
      toast.success("Suggestions refreshed from live signals");
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not regenerate suggestions");
    } finally {
      setGenBusy(false);
    }
  };

  const addBtn = canAct ? (
    <>
      <button
        type="button"
        data-testid="refresh-suggestions-btn"
        onClick={regenerate}
        disabled={genBusy}
        className="app-btn-secondary inline-flex h-8 items-center gap-1.5 px-3 text-[13px] font-medium disabled:opacity-60"
      >
        <RefreshCw className={cn("h-3.5 w-3.5", genBusy && "animate-spin")} />
        {genBusy ? "Scanning…" : "Suggest decisions"}
      </button>
      <button type="button" data-testid="new-decision-btn" onClick={openAdd} className="app-btn-primary inline-flex h-8 items-center gap-1.5 px-3 text-[13px] font-medium">
        <Plus className="h-3.5 w-3.5" /> New decision
      </button>
    </>
  ) : null;

  const pending = decisions.filter(isActionableDecision);
  const resolved = decisions.filter(isResolvedDecision);

  return (
    <div>
      <AppPageHeader title="Decisions" subtitle={SUBTITLE} action={addBtn} meta={pending.length || null} />

      {softRefreshError ? (
        <div
          className="mb-4 rounded-lg border border-helm-status-warning/40 bg-helm-status-warning/10 px-4 py-3 text-sm text-helm-fg"
          data-testid="decisions-soft-refresh-error"
          role="status"
        >
          Could not refresh. Showing last loaded decisions.{" "}
          <button type="button" onClick={reload} className="text-helm-gold hover:text-helm-gold-hover font-medium underline-offset-2 hover:underline">
            Retry
          </button>
        </div>
      ) : null}

      <div className={cn(suggestions.length > 0 && "mb-10")} data-testid="suggested-decisions">
        {suggestions.length > 0 && (
          <ListLabel count={suggestions.length} icon={<Sparkles className="h-3.5 w-3.5 dec-spark" aria-hidden />}>Suggested by Trenston</ListLabel>
        )}
        <AnimatePresence mode="popLayout" initial={false}>
          {suggestions.map((s) => (
            <SuggestionCard
              key={s.id}
              s={s}
              canAct={canAct}
              busy={busy}
              onAcceptSuggestion={approveSuggestion}
              onDismissSuggestion={dismissSuggestion}
            />
          ))}
        </AnimatePresence>
      </div>

      {decisions.length === 0 && suggestions.length === 0 ? (
        <EmptyState title="What do you need to decide?" body="For example: hire a second salesperson, raise prices 10%, or switch suppliers. Log it with what you are leaning towards and it stays on your Briefing until it is decided. Or refresh suggestions and Trenston drafts some from your runway, deals, tasks and blockers."
          action={canAct ? <button type="button" data-testid="empty-new-decision-btn" onClick={openAdd} className="app-btn-primary inline-flex h-9 items-center gap-1.5 px-4 text-[13px] font-medium"><Plus className="h-3.5 w-3.5" /> Log first decision</button> : null} />
      ) : (
        <>
          {pending.length > 0 && <ListLabel count={pending.length}>Open</ListLabel>}
          <div>
            <AnimatePresence mode="popLayout" initial={false}>
              {pending.map((d) => (
                <DecisionCard
                  key={d.id}
                  d={d}
                  canAct={canAct}
                  busy={busy}
                  onApprove={(id) => act(id, "approved")}
                  onReject={(id) => act(id, "rejected")}
                  onDelegate={(id, owner) => act(id, "delegated", owner)}
                  delegateMembers={delegateMembers}
                  selfMember={selfMember}
                  selfLabel={selfLabel}
                  selfOptionLabel={selfOptionLabel}
                  onEdit={openEdit}
                  onDelete={del}
                  ripple={rippleData ? rippleChip(d) : null}
                  onRipple={rippleData ? setRippleFor : null}
                />
              ))}
            </AnimatePresence>
          </div>

          {resolved.length > 0 && (
            <div className="mt-10">
              <ListLabel count={resolved.length}>Recently decided</ListLabel>
              {resolved.map((d) => (
                <div key={d.id} className="dec-row flex items-center gap-3 border-b border-helm-line px-1 py-3 sm:px-3" data-testid={`resolved-${d.id}`} data-deeplink={d.id}>
                  <span
                    aria-hidden
                    className={cn(
                      "h-2 w-2 shrink-0 rounded-full",
                      d.status === "approved" ? "bg-helm-status-positive" : d.status === "rejected" ? "bg-helm-status-negative" : "bg-helm-fg/40",
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-helm-fg/80">{d.title}</p>
                    <MetaLine className="mt-0.5 text-xs" parts={[<span key="s" className="capitalize">{d.status}</span>, d.owner ? `to ${d.owner}` : null]} />
                  </div>
                  {canAct && (
                    <button
                      type="button"
                      onClick={() => del(d.id)}
                      aria-label={`Delete ${d.title}`}
                      title="Delete decision"
                      className="dec-row-reveal inline-flex h-7 w-7 items-center justify-center text-helm-muted hover:text-helm-status-negative"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setShowForm(false)} />
          <GlassCard role="dialog" aria-modal="true" aria-label={editing ? "Edit decision" : "Log a decision"} onKeyDown={(e) => { if (e.key === "Escape") setShowForm(false); }} className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6 max-h-[90vh] overflow-y-auto" data-testid="decision-form">
            <div className="flex items-center justify-between mb-5"><h3 className="text-lg text-helm-fg font-light">{editing ? "Edit decision" : "Log a decision"}</h3><button type="button" onClick={() => setShowForm(false)} aria-label="Close" className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button></div>
            <label className="text-xs text-helm-muted block">Title
              <input data-testid="decision-title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Approve Q3 infra budget" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
            </label>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <label className="text-xs text-helm-muted">Category
                <input data-testid="decision-category" value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} placeholder="Finance" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <label className="text-xs text-helm-muted">Impact
                <select data-testid="decision-impact" value={form.impact} onChange={(e) => setForm((f) => ({ ...f, impact: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40">
                  {["High", "Medium", "Low"].map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              <label className="text-xs text-helm-muted">Due date
                <input data-testid="decision-due" type="date" value={form.due} onChange={(e) => setForm((f) => ({ ...f, due: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
            </div>
            <label className="text-xs text-helm-muted block mt-3">Description
              <textarea data-testid="decision-description" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} rows={2} placeholder="Context for the call" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40 resize-none" />
            </label>
            <label className="text-xs text-helm-muted block mt-3">Recommendation (optional)
              <textarea data-testid="decision-recommendation" value={form.recommendation} onChange={(e) => setForm((f) => ({ ...f, recommendation: e.target.value }))} rows={2} placeholder="Your recommended course" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40 resize-none" />
            </label>
            <button data-testid="save-decision-btn" onClick={save} disabled={saving} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm transition-colors hover:bg-helm-gold-hover disabled:opacity-60">{saving ? "Saving…" : editing ? "Save changes" : "Log decision"}</button>
          </GlassCard>
        </div>
      )}
      {rippleData && (
        <RippleDialog
          open={Boolean(rippleFor)}
          onOpenChange={(v) => { if (!v) setRippleFor(null); }}
          decision={rippleFor}
          baseline={rippleData.baseline}
          saved={rippleFor ? rippleData.effects?.[rippleFor.id] || null : null}
          canEdit={Boolean(rippleData.can_edit)}
          onSaved={reloadRipple}
        />
      )}
    </div>
  );
}
