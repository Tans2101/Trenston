import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useLocation, useNavigate } from "react-router-dom";
import { Plus, RefreshCw, X, Sparkles } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { AnimatePresence } from "motion/react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useDecisionActions, buildDelegateOptions, isOpenDecision } from "@/hooks/useDecisionActions";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, SkeletonCardList } from "@/components/kit";
import DecisionCard, { statusStyle } from "@/components/DecisionCard";
import SuggestionCard from "@/components/SuggestionCard";
import { cn } from "@/lib/utils";

const emptyForm = () => ({ title: "", category: "General", description: "", recommendation: "", due: "", impact: "Medium" });

export default function Decisions() {
  const { data, loading, error, reload } = useFetch("/decisions");
  const { data: membersData } = useFetch("/members");
  const { busy, act, approveSuggestion, dismissSuggestion } = useDecisionActions(reload);
  const location = useLocation();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [genBusy, setGenBusy] = useState(false);

  useEffect(() => {
    if (!location.state?.openAdd) return;
    setEditing(null);
    setForm(emptyForm());
    setShowForm(true);
    navigate(location.pathname, { replace: true, state: {} });
  }, [location.state, location.pathname, navigate]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Decision Center" subtitle="Every open decision, ranked by impact. Trenston drafts suggestions from live signals. You confirm before anything becomes a real call." />
        <SkeletonCardList count={4} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load decisions"
        message={fetchErrorMessage(error, "Decisions data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }
  const canAct = data.can_act;
  const suggestions = data.suggestions || [];
  const decisions = data.decisions || [];
  const { selfMember, delegateMembers, selfLabel, selfOptionLabel } = buildDelegateOptions(membersData);

  const openAdd = () => { setEditing(null); setForm(emptyForm()); setShowForm(true); };
  const openEdit = (d) => {
    setEditing(d.id);
    setForm({
      title: d.title,
      category: d.category,
      description: d.description || "",
      recommendation: d.recommendation || "",
      due: d.due === "—" ? "" : d.due,
      impact: d.impact,
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.title.trim()) { toast.error("Add a title"); return; }
    setSaving(true);
    // Manual decisions use Impact only — never invent a confidence %
    const payload = { ...form, confidence: null };
    try {
      if (editing) { await api.patch(`/decisions/${editing}`, payload); toast.success("Decision updated"); }
      else { await api.post("/decisions", payload); toast.success("Decision added"); }
      setShowForm(false); reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save"); }
    finally { setSaving(false); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this decision?")) return;
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
    <div className="flex items-center gap-2">
      <button
        data-testid="refresh-suggestions-btn"
        onClick={regenerate}
        disabled={genBusy}
        className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg font-medium text-sm px-3 py-2 hover:bg-helm-fg/5 disabled:opacity-60"
      >
        <RefreshCw className={cn("w-4 h-4", genBusy && "animate-spin")} />
        {genBusy ? "Scanning…" : "Refresh suggestions"}
      </button>
      <button data-testid="new-decision-btn" onClick={openAdd} className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover">
        <Plus className="w-4 h-4" /> New decision
      </button>
    </div>
  ) : null;

  const pending = decisions.filter((d) => isOpenDecision(d, selfLabel));
  const resolved = decisions.filter((d) => !isOpenDecision(d, selfLabel));

  return (
    <div>
      <PageHeader title="Decision Center" subtitle="Every open decision, ranked by impact. Trenston drafts suggestions from live signals. You confirm before anything becomes a real call." action={addBtn} />

      <div className={cn(suggestions.length > 0 && "mb-8")} data-testid="suggested-decisions">
        {suggestions.length > 0 && (
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-4 h-4 text-helm-status-warning" />
            <SectionLabel>Suggested by Trenston</SectionLabel>
            <span className="font-mono text-xs text-helm-status-warning/80">{suggestions.length}</span>
          </div>
        )}
        <div className={cn(suggestions.length > 0 && "space-y-3")}>
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
      </div>

      {decisions.length === 0 && suggestions.length === 0 ? (
        <EmptyState title="No decisions yet" body="Log the calls that need to be made, or refresh suggestions so Trenston can draft from runway, deals, tasks, and blockers."
          action={canAct ? <button data-testid="empty-new-decision-btn" onClick={openAdd} className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"><Plus className="w-4 h-4" /> Log first decision</button> : null} />
      ) : (
        <>
          {pending.length > 0 && <SectionLabel className="mb-4">Open decisions</SectionLabel>}
          <div className="space-y-4">
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
                />
              ))}
            </AnimatePresence>
          </div>

          {resolved.length > 0 && (
            <div className="mt-8">
              <SectionLabel className="mb-4">Recently resolved · outcome checks</SectionLabel>
              <div className="space-y-2">
                {resolved.map((d) => (
                  <div key={d.id} className="flex items-center gap-3 rounded-lg border border-helm-line bg-helm-fg/[0.02] px-4 py-3" data-testid={`resolved-${d.id}`}>
                    <span className={cn("text-[10px] font-mono uppercase tracking-wider rounded px-1.5 py-0.5 border", statusStyle[d.status])}>{d.status}</span>
                    <span className="text-sm text-helm-fg flex-1">{d.title}</span>
                    <span className="text-xs text-helm-muted">{d.owner ? `→ ${d.owner}` : ""}</span>
                    {canAct && <CirDeleteBtn onClick={() => del(d.id)} title="Delete decision" />}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setShowForm(false)} />
          <GlassCard className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6 max-h-[90vh] overflow-y-auto" data-testid="decision-form">
            <div className="flex items-center justify-between mb-5"><h3 className="text-lg text-helm-fg font-light">{editing ? "Edit decision" : "Log a decision"}</h3><button onClick={() => setShowForm(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button></div>
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
    </div>
  );
}
