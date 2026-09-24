import { useState, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, PenLine, X, TrendingUp } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { api } from "@/lib/api";
import {
  PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, ConfirmDialog,
  SkeletonKPIRow, SkeletonCardList,
} from "@/components/kit";
import { FETCH_STALE_MS, fetchErrorMessage } from "@/hooks/useFetch";
import { cn } from "@/lib/utils";
import { PossiblyStaleBadge } from "@/components/AiSummaryMeta";
import SalesOrderBook from "@/components/SalesOrderBook";
import { useWorkspaceCurrency } from "@/hooks/useWorkspaceCurrency";
import { formatMoney } from "@/lib/money";

const stageStyle = {
  lead: "text-helm-fg bg-helm-fg/5",
  qualified: "text-helm-fg bg-helm-muted/12",
  proposal: "text-helm-fg bg-helm-gold/12",
  negotiation: "text-helm-gold bg-helm-gold/12",
  won: "text-helm-fg bg-helm-status-positive/12",
  lost: "text-helm-status-negative bg-helm-status-negative/12",
};
const money = (n, sym) => formatMoney(n, sym, { compact: true });
const emptyForm = (defaults = {}) => ({
  name: "",
  company: "",
  value: "",
  stage: "lead",
  owner_name: "",
  owner_user_id: "",
  close_date: "",
  next_step: "",
  next_step_date: "",
  ...defaults,
});
const PAGE_LIMIT = 200;

function ownerLabel(owner) {
  if (!owner) return "";
  return owner.name || owner.email || "Teammate";
}

export default function Pipeline() {
  const queryClient = useQueryClient();
  const { currency: workspaceCurrency, symbol: workspaceSymbol } = useWorkspaceCurrency();
  const [extraDeals, setExtraDeals] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [mineOnly, setMineOnly] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [busy, setBusy] = useState(false);
  const [confirmDeleteDeal, setConfirmDeleteDeal] = useState(null);
  const [productionPrompt, setProductionPrompt] = useState(null);
  const [creatingWorkOrder, setCreatingWorkOrder] = useState(false);
  const [salesTab, setSalesTab] = useState("pipeline");

  const dealsQueryKey = ["deals", "pipeline", mineOnly ? "me" : "all"];

  const dealsQuery = useQuery({
    queryKey: dealsQueryKey,
    staleTime: FETCH_STALE_MS,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
    queryFn: async () => {
      const params = { limit: PAGE_LIMIT };
      if (mineOnly) params.owner_user_id = "me";
      const { data } = await api.get("/deals", { params });
      return data;
    },
  });

  // Reset pagination extras when the primary page (or mine filter) changes.
  useEffect(() => {
    setExtraDeals([]);
    setNextCursor(dealsQuery.data?.next_cursor ?? null);
  }, [dealsQuery.data, mineOnly]);

  const pageDeals = dealsQuery.data?.items || dealsQuery.data?.deals || [];
  const deals = extraDeals.length ? [...pageDeals, ...extraDeals] : pageDeals;
  const meta = dealsQuery.data
    ? {
        can_write: dealsQuery.data.can_write,
        can_reassign_owner: Boolean(dealsQuery.data.can_reassign_owner || dealsQuery.data.is_lead),
        is_lead: Boolean(dealsQuery.data.is_lead || dealsQuery.data.can_reassign_owner),
        my_user_id: dealsQuery.data.my_user_id || null,
        sales_owners: dealsQuery.data.sales_owners || [],
        metrics: dealsQuery.data.metrics,
        stages: dealsQuery.data.stages,
        currency: dealsQuery.data.currency || workspaceCurrency,
        currency_symbol: dealsQuery.data.currency_symbol || workspaceSymbol,
      }
    : null;

  const loading = dealsQuery.isLoading;
  const loadError = dealsQuery.error ?? null;

  const reload = useCallback(async () => {
    setExtraDeals([]);
    await queryClient.invalidateQueries({ queryKey: ["deals", "pipeline"] });
  }, [queryClient]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const params = { limit: PAGE_LIMIT, before: nextCursor };
      if (mineOnly) params.owner_user_id = "me";
      const { data } = await api.get("/deals", { params });
      const page = data.items || data.deals || [];
      setExtraDeals((prev) => [...prev, ...page]);
      setNextCursor(data.next_cursor ?? null);
    } catch {
      toast.error("Could not load more deals");
    } finally {
      setLoadingMore(false);
    }
  };

  if (loading) {
    return (
      <div>
        <PageHeader title="Sales Pipeline" subtitle="Log deals and stages. Pipeline signals roll straight into the CEO Briefing." />
        <SkeletonKPIRow count={4} />
        <SkeletonCardList count={4} />
      </div>
    );
  }
  if (loadError || !meta) {
    return (
      <ErrorScreen
        label="Could not load pipeline"
        message={fetchErrorMessage(loadError, "Pipeline data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }
  const canWrite = meta.can_write;
  const canReassign = meta.can_reassign_owner;
  const myId = meta.my_user_id;
  const salesOwners = meta.sales_owners || [];
  const m = meta.metrics;
  const sym = meta.currency_symbol || workspaceSymbol;

  const maybeOfferProduction = (res) => {
    if (res?.production_prompt && res?.production_prefill) {
      setProductionPrompt(res.production_prefill);
    }
  };

  const dealPayload = (base) => ({
    name: base.name,
    company: base.company || "",
    value: typeof base.value === "number" ? base.value : (parseFloat(base.value) || 0),
    stage: base.stage,
    owner_name: base.owner_name || "",
    owner_user_id: base.owner_user_id || null,
    close_date: base.close_date || "",
    next_step: base.next_step || "",
    next_step_date: base.next_step_date || "",
  });

  const openAdd = () => {
    setEditing(null);
    setForm(emptyForm({
      owner_user_id: canReassign ? "" : (myId || ""),
      owner_name: canReassign ? "" : (salesOwners.find((o) => o.user_id === myId)?.name || ""),
    }));
    setShowForm(true);
  };
  const openEdit = (d) => {
    setEditing(d.id);
    setForm({
      name: d.name,
      company: d.company || "",
      value: d.value,
      stage: d.stage,
      owner_name: d.owner_name || "",
      owner_user_id: d.owner_user_id || "",
      close_date: d.close_date || "",
      next_step: d.next_step || "",
      next_step_date: d.next_step_date || "",
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.name.trim()) { toast.error("Deal name required"); return; }
    setBusy(true);
    const payload = dealPayload(form);
    try {
      if (editing) {
        const { data: res } = await api.patch(`/deals/${editing}`, payload);
        toast.success("Deal updated");
        maybeOfferProduction(res);
      } else {
        await api.post("/deals", payload);
        toast.success("Deal added to pipeline");
      }
      setShowForm(false); reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save"); }
    finally { setBusy(false); }
  };

  const changeStage = async (d, stage) => {
    try {
      const { data: res } = await api.patch(`/deals/${d.id}`, dealPayload({ ...d, stage }));
      maybeOfferProduction(res);
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update stage");
    }
  };
  const del = async () => {
    const d = confirmDeleteDeal;
    if (!d) return;
    setBusy(true);
    try {
      await api.delete(`/deals/${d.id}`);
      setConfirmDeleteDeal(null);
      reload();
      toast.success("Deal removed");
    } catch (e) {
      toast.error("Could not delete");
    } finally {
      setBusy(false);
    }
  };

  const confirmCreateWorkOrder = async () => {
    if (!productionPrompt) return;
    setCreatingWorkOrder(true);
    try {
      await api.post("/production/work-orders", {
        reference: productionPrompt.reference || "Won deal",
        customer: productionPrompt.customer || "",
        source_deal_id: productionPrompt.source_deal_id || null,
      });
      toast.success("Production work order created");
      setProductionPrompt(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create work order");
    } finally {
      setCreatingWorkOrder(false);
    }
  };

  const action = salesTab === "pipeline" && canWrite ? (
    <button data-testid="add-deal-btn" onClick={openAdd} className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover">
      <Plus className="w-4 h-4" /> New deal
    </button>
  ) : null;

  return (
    <div>
      <PageHeader title="Sales" subtitle="Pipeline and order book. Status rolls into the CEO Briefing." action={action} />

      <div className="flex items-center gap-1 mb-5 border-b border-helm-line" data-testid="sales-tabs">
        {[
          { id: "pipeline", label: "Pipeline" },
          { id: "order_book", label: "Order book" },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            data-testid={`sales-tab-${t.id}`}
            onClick={() => setSalesTab(t.id)}
            className={cn(
              "px-3 py-2 text-sm border-b-2 -mb-px transition-colors",
              salesTab === t.id
                ? "border-helm-gold text-helm-fg"
                : "border-transparent text-helm-muted hover:text-helm-fg",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {salesTab === "order_book" ? (
        <SalesOrderBook />
      ) : (
        <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="filter-my-deals"
          onClick={() => setMineOnly((v) => !v)}
          className={cn(
            "rounded-md border px-3 py-1.5 text-sm transition-colors",
            mineOnly
              ? "border-helm-gold/35 bg-helm-gold/12 text-helm-fg"
              : "border-helm-line bg-helm-fg/5 text-helm-muted hover:text-helm-fg",
          )}
        >
          {mineOnly ? "Showing my deals" : "My deals"}
        </button>
      </div>

      {deals.length === 0 ? (
        <EmptyState icon={TrendingUp} title={mineOnly ? "No deals assigned to you" : "No deals yet"} body={mineOnly ? "Deals you own will show up here. Ask a Sales lead to assign one, or clear the filter." : "Add your first deal. As it moves through stages, the CEO sees it in the briefing."}
          action={!mineOnly && canWrite ? <button data-testid="empty-add-deal-btn" onClick={openAdd} className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"><Plus className="w-4 h-4" /> Add first deal</button> : null} />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <GlassCard className="p-5 fade-up"><p className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">Open Pipeline</p><p className="font-mono text-2xl text-helm-fg mt-2" data-testid="metric-open">{money(m.open_value, sym)}</p></GlassCard>
            <GlassCard className="p-5 fade-up"><p className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">Won</p><p className="font-mono text-2xl text-helm-status-positive mt-2">{money(m.won_value, sym)}</p></GlassCard>
            <GlassCard className="p-5 fade-up"><p className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">Open Deals</p><p className="font-mono text-2xl text-helm-fg mt-2">{m.open_count}</p></GlassCard>
          </div>

          <div className="space-y-6">
            {m.by_stage.filter((s) => s.count > 0).map((s) => (
              <div key={s.stage}>
                <div className="flex items-center gap-2 mb-2">
                  <SectionLabel>{s.label}</SectionLabel>
                  <span className="text-xs font-mono text-helm-muted">{s.count} · {money(s.value, sym)}</span>
                </div>
                <div className="space-y-2">
                  {deals.filter((d) => d.stage === s.stage).map((d) => (
                    <GlassCard key={d.id} className="p-4 fade-up flex items-center gap-4 group" data-testid={`deal-${d.id}`}>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <p className="text-sm text-helm-fg truncate">{d.name}</p>
                          <PossiblyStaleBadge show={d.possibly_stale} />
                        </div>
                        <p className="text-xs text-helm-muted truncate">
                          {d.company || "—"}
                          {d.owner_name ? ` · Owner ${d.owner_name}` : ""}
                          {d.close_date ? ` · close ${d.close_date}` : ""}
                        </p>
                        {(d.next_step || d.next_step_date) ? (
                          <p className="text-[11px] text-helm-gold mt-0.5 truncate" data-testid={`deal-next-step-${d.id}`}>
                            Next: {d.next_step || "Follow up"}
                            {d.next_step_date ? ` · ${d.next_step_date}` : ""}
                          </p>
                        ) : null}
                        {d.created_by_name ? (
                          <p className="text-[11px] text-helm-muted mt-0.5" data-testid={`deal-added-by-${d.id}`}>
                            Added by {d.created_by_name}
                          </p>
                        ) : null}
                      </div>
                      <span className="font-mono text-sm text-helm-fg shrink-0">{money(d.value, sym)}</span>
                      {canWrite ? (
                        <select value={d.stage} onChange={(e) => changeStage(d, e.target.value)} data-testid={`deal-stage-${d.id}`}
                          className={cn("text-[11px] font-mono rounded px-2 py-1 border border-helm-line bg-helm-card focus:outline-none focus:border-helm-gold/40", stageStyle[d.stage])}>
                          {meta.stages.map((st) => <option key={st.id} value={st.id}>{st.label}</option>)}
                        </select>
                      ) : (
                        <span className={cn("text-[10px] font-mono uppercase rounded px-1.5 py-0.5", stageStyle[d.stage])}>{s.label}</span>
                      )}
                      {canWrite && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => openEdit(d)} data-testid={`edit-deal-${d.id}`} className="text-helm-muted hover:text-helm-gold p-1"><PenLine className="w-3.5 h-3.5" /></button>
                          <CirDeleteBtn onClick={() => setConfirmDeleteDeal(d)} data-testid={`del-deal-${d.id}`} title="Delete deal" />
                        </div>
                      )}
                    </GlassCard>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {nextCursor && (
            <div className="mt-8 flex justify-center">
              <button
                type="button"
                data-testid="load-more-deals-btn"
                onClick={loadMore}
                disabled={loadingMore}
                className="rounded-md border border-helm-line bg-helm-fg/5 px-4 py-2 text-sm text-helm-fg transition-colors hover:border-helm-gold/35 hover:text-helm-fg disabled:opacity-60"
              >
                {loadingMore ? "Loading…" : "Load more deals"}
              </button>
            </div>
          )}
        </>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setShowForm(false)} />
          <GlassCard className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="deal-form">
            <div className="flex items-center justify-between mb-5"><h3 className="text-lg text-helm-fg font-light">{editing ? "Edit deal" : "New deal"}</h3><button onClick={() => setShowForm(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button></div>
            <label className="text-xs text-helm-muted block">Deal name
              <input data-testid="deal-name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Acme Corp Enterprise" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
            </label>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <label className="text-xs text-helm-muted">Company
                <input data-testid="deal-company" value={form.company} onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))} placeholder="Acme" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <label className="text-xs text-helm-muted">Value ({sym})
                <input data-testid="deal-value" type="number" min="0" value={form.value} onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))} placeholder="25000" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <label className="text-xs text-helm-muted">Stage
                <select data-testid="deal-stage" value={form.stage} onChange={(e) => setForm((f) => ({ ...f, stage: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40">
                  {meta.stages.map((st) => <option key={st.id} value={st.id}>{st.label}</option>)}
                </select>
              </label>
              <label className="text-xs text-helm-muted">Expected close
                <input data-testid="deal-close" type="date" value={form.close_date} onChange={(e) => setForm((f) => ({ ...f, close_date: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <label className="text-xs text-helm-muted col-span-2">Owner
                {canReassign && salesOwners.length > 0 ? (
                  <select
                    data-testid="deal-owner"
                    value={form.owner_user_id || ""}
                    onChange={(e) => {
                      const uid = e.target.value;
                      const match = salesOwners.find((o) => o.user_id === uid);
                      setForm((f) => ({
                        ...f,
                        owner_user_id: uid,
                        owner_name: ownerLabel(match) || f.owner_name,
                      }));
                    }}
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                  >
                    <option value="">Unassigned</option>
                    {salesOwners.map((o) => (
                      <option key={o.user_id} value={o.user_id}>{ownerLabel(o)}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    data-testid="deal-owner"
                    value={form.owner_name || (salesOwners.find((o) => o.user_id === (form.owner_user_id || myId))?.name) || "You"}
                    readOnly
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card/60 text-helm-muted text-sm px-3 py-2"
                  />
                )}
              </label>
              <label className="text-xs text-helm-muted col-span-2">Next step
                <input
                  data-testid="deal-next-step"
                  value={form.next_step}
                  onChange={(e) => setForm((f) => ({ ...f, next_step: e.target.value }))}
                  placeholder="Call back Thursday"
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
              <label className="text-xs text-helm-muted col-span-2">Follow-up date
                <input
                  data-testid="deal-next-step-date"
                  type="date"
                  value={form.next_step_date}
                  onChange={(e) => setForm((f) => ({ ...f, next_step_date: e.target.value }))}
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
            </div>
            <button data-testid="save-deal-btn" onClick={save} disabled={busy} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm transition-colors hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : editing ? "Save changes" : "Add deal"}</button>
          </GlassCard>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(confirmDeleteDeal)}
        title={`Delete ${confirmDeleteDeal?.name || "deal"}?`}
        description="This permanently removes the deal from the pipeline. This can’t be undone."
        confirmLabel="Delete deal"
        busy={busy}
        onCancel={() => setConfirmDeleteDeal(null)}
        onConfirm={del}
        testId="delete-deal-confirm"
      />

      <ConfirmDialog
        open={Boolean(productionPrompt)}
        title="Create a Production work order for this?"
        description={
          productionPrompt
            ? `Pre-fill reference “${productionPrompt.reference || "Won deal"}”`
              + (productionPrompt.customer ? ` for ${productionPrompt.customer}` : "")
              + ". Decline leaves the revenue entry in place with no Production work order."
            : ""
        }
        confirmLabel="Create work order"
        cancelLabel="Not now"
        destructive={false}
        busy={creatingWorkOrder}
        onConfirm={confirmCreateWorkOrder}
        onCancel={() => setProductionPrompt(null)}
        testId="won-deal-production-prompt"
      />
        </>
      )}
    </div>
  );
}
