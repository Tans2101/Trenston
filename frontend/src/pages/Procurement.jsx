import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, X, Package } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api, apiErrorMessage } from "@/lib/api";
import {
  PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, ConfirmDialog,
  SkeletonKPIRow, SkeletonCardList,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { PossiblyStaleBadge } from "@/components/AiSummaryMeta";

const STATUS_META = {
  requested: { label: "Requested", className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35" },
  approved: { label: "Approved", className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35" },
  ordered: { label: "Ordered", className: "bg-helm-status-warning/12 text-helm-fg border-helm-status-warning/35" },
  delivered: { label: "Delivered", className: "bg-helm-status-positive/12 text-helm-fg border-helm-status-positive/35" },
  rejected: { label: "Rejected", className: "bg-helm-status-negative/12 text-helm-status-negative border-helm-status-negative/35" },
};

const CLOSED = new Set(["delivered", "rejected"]);

function isExpectedDeliveryOverdue(dateStr, status) {
  // Match Decision Center / backend: only ordered requests with a past date are overdue.
  if (status !== "ordered") return false;
  const raw = (dateStr || "").trim();
  if (!raw) return false;
  const end = new Date(`${raw}T23:59:59`);
  if (Number.isNaN(end.getTime())) return false;
  return end.getTime() < Date.now();
}

function PriorityBadge({ priority }) {
  const p = priority || "normal";
  if (p !== "high") {
    return <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted capitalize">{p}</span>;
  }
  return (
    <span
      data-testid="priority-high-badge"
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide border border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
    >
      High
    </span>
  );
}

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.requested;
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide border", meta.className)}>
      {meta.label}
    </span>
  );
}

/**
 * Prefer selecting a previous vendor name so spend rollups stay consistent.
 * "New vendor…" opens a free-text field; that name joins the list on later requests.
 */
function VendorPicker({
  value,
  onChange,
  knownVendors = [],
  disabled = false,
  testId,
  customTestId,
}) {
  const valueInList = knownVendors.includes(value);
  const [customMode, setCustomMode] = useState(() => Boolean(value) && !valueInList);

  useEffect(() => {
    if (valueInList) setCustomMode(false);
    else if (value) setCustomMode(true);
  }, [value, valueInList]);

  const fieldClass =
    "w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50";

  if (knownVendors.length === 0) {
    return (
      <input
        data-testid={testId}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Vendor name"
        className={fieldClass}
      />
    );
  }

  return (
    <div className="space-y-2">
      <select
        data-testid={testId}
        disabled={disabled}
        value={customMode ? "__new__" : value}
        onChange={(e) => {
          const next = e.target.value;
          if (next === "__new__") {
            setCustomMode(true);
            onChange("");
            return;
          }
          setCustomMode(false);
          onChange(next);
        }}
        className={fieldClass}
      >
        <option value="">Select vendor…</option>
        {knownVendors.map((name) => (
          <option key={name} value={name}>{name}</option>
        ))}
        <option value="__new__">New vendor…</option>
      </select>
      {customMode ? (
        <input
          data-testid={customTestId || `${testId}-custom`}
          disabled={disabled}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Type new vendor name"
          className={fieldClass}
          autoFocus
        />
      ) : null}
      <p className="text-[11px] text-helm-muted leading-relaxed">
        Reuse a previous vendor when you can — spelling variants split spend. New names show up here next time.
      </p>
    </div>
  );
}

function formatDays(value) {
  if (value == null || Number.isNaN(Number(value))) return null;
  const n = Number(value);
  if (n === Math.trunc(n)) return `${n}d`;
  return `${n.toFixed(1).replace(/\.0$/, "")}d`;
}

function formatLeadMetric(tracked, days, { signed = false } = {}) {
  if (!tracked || days == null) return "Not tracked";
  const n = Number(days);
  const label = formatDays(Math.abs(n)) || "0d";
  if (!signed) return label;
  if (n > 0) return `${label} late`;
  if (n < 0) return `${label} early`;
  return "On time";
}

function personLabel(p) {
  if (!p) return "—";
  return p.name || p.email || "Teammate";
}

function formatBlockingOrders(orders) {
  if (!orders?.length) return "";
  return orders.map((o) => {
    const ref = o.reference || o.work_order_id || "work order";
    const due = o.due_date || "";
    return due ? `${ref} (due ${due})` : ref;
  }).join(", ");
}

function BlockingProductionBadge({ orders, requestId }) {
  if (!orders?.length) return null;
  const label = formatBlockingOrders(orders);
  return (
    <span
      data-testid={`blocking-production-badge-${requestId}`}
      title={label}
      className="inline-flex max-w-full items-center truncate rounded px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide border border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
    >
      Blocking: {label}
    </span>
  );
}

export default function Procurement() {
  const { data, loading, error, reload } = useFetch("/procurement/requests");
  const [showClosed, setShowClosed] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [orderDatePrompt, setOrderDatePrompt] = useState(null);
  const [vendorSuggestions, setVendorSuggestions] = useState([]);
  const [vendorNote, setVendorNote] = useState("");
  const [form, setForm] = useState({ item: "", quantity: "1", vendor_name: "", cost: "", notes: "", expected_delivery_date: "", priority: "normal" });

  const allRequests = useMemo(() => data?.requests || [], [data?.requests]);
  const leadSummary = data?.lead_time_summary || null;
  const spend = data?.spend || null;
  const knownVendors = useMemo(() => {
    const names = new Set();
    for (const r of allRequests) {
      const v = (r.vendor_name || "").trim();
      if (v) names.add(v);
    }
    for (const row of spend?.by_vendor || []) {
      const v = (row.vendor_name || "").trim();
      if (v && v !== "(no vendor)") names.add(v);
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [allRequests, spend?.by_vendor]);
  const canManageBudget = Boolean(data?.is_lead || data?.is_ceo || data?.can_approve);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [budgetBusy, setBudgetBusy] = useState(false);

  useEffect(() => {
    if (spend?.budget_entered && spend.budget != null) setBudgetDraft(String(spend.budget));
    else if (data?.monthly_budget_entered && data?.monthly_budget != null) {
      setBudgetDraft(String(data.monthly_budget));
    } else {
      setBudgetDraft("");
    }
  }, [spend?.budget, spend?.budget_entered, data?.monthly_budget, data?.monthly_budget_entered]);

  const visible = useMemo(() => {
    // Backend owns queue order; only filter closed locally.
    return showClosed ? allRequests : allRequests.filter((r) => !CLOSED.has(r.status));
  }, [allRequests, showClosed]);
  const selected = useMemo(
    () => allRequests.find((r) => r.id === selectedId) || null,
    [allRequests, selectedId],
  );

  useEffect(() => {
    if (!adding) {
      setVendorSuggestions([]);
      setVendorNote("");
      return undefined;
    }
    const q = (form.item || "").trim();
    if (q.length < 2) {
      setVendorSuggestions([]);
      setVendorNote("");
      return undefined;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const { data: res } = await api.get("/procurement/vendor-suggestions", { params: { item: q } });
        if (!cancelled) setVendorSuggestions(res?.suggestions || []);
      } catch {
        if (!cancelled) setVendorSuggestions([]);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [adding, form.item]);

  useEffect(() => {
    if (!selected) {
      setDraft(null);
      return;
    }
    setDraft({
      item: selected.item || "",
      quantity: String(selected.quantity ?? 1),
      vendor_name: selected.vendor_name || "",
      cost: selected.cost == null ? "" : String(selected.cost),
      notes: selected.notes || "",
      expected_delivery_date: selected.expected_delivery_date || "",
      priority: selected.priority || "normal",
      status: selected.status || "requested",
    });
  }, [selected]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Procurement" subtitle="Purchase request queue. Each request moves independently." />
        <SkeletonKPIRow count={3} className="lg:grid-cols-3" />
        <SkeletonCardList count={5} />
      </div>
    );
  }
  if (error) {
    const status = error?.response?.status;
    if (status === 403) {
      return (
        <ErrorScreen
          label="Access denied"
          message="You are not a member of Procurement. Ask your CEO to add you."
          onRetry={reload}
        />
      );
    }
    if (status === 404) {
      return (
        <ErrorScreen
          label="Procurement not enabled"
          message="Enable Procurement under Settings → Departments first."
          onRetry={reload}
        />
      );
    }
    return (
      <ErrorScreen
        label="Could not load Procurement"
        message={fetchErrorMessage(error, "Procurement data is unavailable.")}
        onRetry={reload}
      />
    );
  }

  const canApprove = Boolean(data?.can_approve);
  const myId = data?.my_user_id;
  const isOwner = selected && selected.requested_by === myId;
  const canEditContent = Boolean(
    selected && (canApprove || (isOwner && selected.status === "requested")),
  );
  const canDeleteSelected = Boolean(
    selected && (canApprove || (isOwner && selected.status === "requested")),
  );

  const createRequest = async () => {
    if (!form.item.trim()) {
      toast.error("Item is required");
      return;
    }
    const quantity = Number(form.quantity);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      toast.error("Quantity must be a positive number");
      return;
    }
    let cost = null;
    if (form.cost.trim() !== "") {
      cost = Number(form.cost);
      if (!Number.isFinite(cost) || cost < 0) {
        toast.error("Cost must be a non-negative number");
        return;
      }
    }
    setBusy(true);
    try {
      const { data: res } = await api.post("/procurement/requests", {
        item: form.item.trim(),
        quantity,
        vendor_name: form.vendor_name.trim(),
        cost,
        notes: form.notes.trim(),
        expected_delivery_date: form.expected_delivery_date.trim(),
        priority: form.priority || "normal",
      });
      toast.success("Request submitted");
      setForm({ item: "", quantity: "1", vendor_name: "", cost: "", notes: "", expected_delivery_date: "", priority: "normal" });
      setAdding(false);
      await reload();
      if (res?.request?.id) setSelectedId(res.request.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create request");
    } finally {
      setBusy(false);
    }
  };

  const saveRequest = async (overrides = {}) => {
    if (!selected || !draft) return;
    const body = { ...overrides };
    if (canEditContent) {
      const quantity = Number(draft.quantity);
      if (!Number.isFinite(quantity) || quantity <= 0) {
        toast.error("Quantity must be a positive number");
        return;
      }
      body.item = draft.item.trim();
      body.quantity = quantity;
      body.vendor_name = draft.vendor_name.trim();
      body.notes = draft.notes;
      if (draft.cost.trim() === "") {
        // omit cost if cleared — leave existing unless lead clears via 0
      } else {
        const cost = Number(draft.cost);
        if (!Number.isFinite(cost) || cost < 0) {
          toast.error("Cost must be a non-negative number");
          return;
        }
        body.cost = cost;
      }
    }
    if (canEditContent || canApprove) {
      body.expected_delivery_date = (draft.expected_delivery_date || "").trim();
      body.priority = draft.priority || "normal";
    }
    if (!Object.keys(body).length) return;
    setBusy(true);
    try {
      const { data: res } = await api.patch(`/procurement/requests/${selected.id}`, body);
      if (res?.financial_entry) {
        toast.success("Request updated · expense logged to Financials");
      } else {
        toast.success("Request updated");
      }
      await reload();
      if (res?.request?.id) setSelectedId(res.request.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update request");
    } finally {
      setBusy(false);
    }
  };

  const applyStatus = async (status, extra = {}) => {
    setBusy(true);
    try {
      const { data: res } = await api.patch(`/procurement/requests/${selected.id}`, { status, ...extra });
      if (res?.financial_entry) {
        toast.success(`Marked ${STATUS_META[status]?.label || status} · expense logged to Financials`);
      } else {
        toast.success(`Marked ${STATUS_META[status]?.label || status}`);
      }
      await reload();
      if (res?.request?.id) setSelectedId(res.request.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update status");
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status) => {
    if (
      status === "ordered"
      && !(draft?.expected_delivery_date || selected?.expected_delivery_date || "").trim()
    ) {
      setOrderDatePrompt({ status, date: "" });
      return;
    }
    await applyStatus(status);
  };

  const confirmOrderDatePrompt = async ({ skip } = {}) => {
    if (!orderDatePrompt) return;
    const { status } = orderDatePrompt;
    const date = (orderDatePrompt.date || "").trim();
    setOrderDatePrompt(null);
    if (skip || !date) {
      await applyStatus(status);
      return;
    }
    setDraft((d) => (d ? { ...d, expected_delivery_date: date } : d));
    await applyStatus(status, { expected_delivery_date: date });
  };

  const deleteRequest = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.delete(`/procurement/requests/${selected.id}`);
      toast.success("Request deleted");
      setConfirmDelete(false);
      setSelectedId(null);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    } finally {
      setBusy(false);
    }
  };

  const saveProcurementBudget = async () => {
    const t = Number(budgetDraft);
    if (!Number.isFinite(t) || t < 0) {
      toast.error("Enter a non-negative budget");
      return;
    }
    setBudgetBusy(true);
    try {
      await api.put("/procurement/settings", { monthly_budget: t });
      toast.success("Procurement budget saved");
      await reload();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save budget"));
    } finally {
      setBudgetBusy(false);
    }
  };

  const clearProcurementBudget = async () => {
    setBudgetBusy(true);
    try {
      await api.put("/procurement/settings", { clear_budget: true });
      toast.success("Budget cleared");
      setBudgetDraft("");
      await reload();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not clear budget"));
    } finally {
      setBudgetBusy(false);
    }
  };

  const action = (
    <button
      type="button"
      data-testid="add-procurement-request-btn"
      onClick={() => setAdding(true)}
      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover"
    >
      <Plus className="w-4 h-4" /> New request
    </button>
  );

  return (
    <div data-testid="procurement-page">
      <PageHeader
        title={data?.name || "Procurement"}
        subtitle="Purchase request queue. Each request moves independently."
        action={action}
      />

      {leadSummary && (
        <div
          className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5"
          data-testid="procurement-lead-time-summary"
        >
          {[
            {
              key: "sourcing",
              label: "Avg sourcing time",
              value: leadSummary.sourcing_sample_count
                ? formatDays(leadSummary.avg_sourcing_days)
                : "Not tracked",
              muted: !leadSummary.sourcing_sample_count,
              detail: leadSummary.sourcing_sample_count
                ? `${leadSummary.sourcing_sample_count} tracked`
                : "No vendor lock-in dates yet",
            },
            {
              key: "delay",
              label: "Avg fulfillment delay",
              value: leadSummary.delay_sample_count
                ? formatLeadMetric(true, leadSummary.avg_fulfillment_delay_days, { signed: true })
                : "Not tracked",
              muted: !leadSummary.delay_sample_count,
              detail: leadSummary.delay_sample_count
                ? `${leadSummary.delay_sample_count} delivered`
                : "No actual delivery dates yet",
            },
            {
              key: "late",
              label: "Currently late",
              value: String(leadSummary.currently_late_count ?? 0),
              muted: false,
              detail: (leadSummary.currently_late_count ?? 0)
                ? "Ordered past expected date"
                : "None overdue",
              warn: (leadSummary.currently_late_count ?? 0) > 0,
            },
          ].map((s) => (
            <div
              key={s.key}
              className="rounded-md border border-helm-line bg-helm-card/40 px-3 py-2.5"
              data-testid={`procurement-summary-${s.key}`}
            >
              <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-helm-muted">
                {s.label}
              </p>
              <p
                className={cn(
                  "font-mono text-xl mt-1",
                  s.warn ? "text-helm-status-negative" : s.muted ? "text-helm-muted" : "text-helm-fg",
                )}
              >
                {s.value}
              </p>
              <p className="text-[11px] text-helm-muted mt-0.5">{s.detail}</p>
            </div>
          ))}
        </div>
      )}

      {(leadSummary?.currently_late || []).length > 0 && (
        <div
          className="rounded-md border border-helm-status-negative/35 bg-helm-status-negative/8 px-3 py-2.5 mb-5 space-y-1"
          data-testid="procurement-late-list"
        >
          <p className="text-[10px] font-mono uppercase tracking-wide text-helm-status-negative">
            Late orders
          </p>
          {leadSummary.currently_late.slice(0, 5).map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelectedId(r.id)}
              className="block w-full text-left text-xs text-helm-fg hover:text-helm-gold truncate"
            >
              {r.item || "Request"}
              {r.vendor_name ? ` · ${r.vendor_name}` : ""}
              {r.expected_delivery_date ? ` · due ${r.expected_delivery_date}` : ""}
            </button>
          ))}
        </div>
      )}

      {spend && (
        <div
          className={cn(
            "rounded-md border px-3 py-3 mb-5 space-y-3",
            spend.budget_entered && (spend.gap || 0) > 0
              ? "border-helm-status-negative/35 bg-helm-status-negative/8"
              : "border-helm-line bg-helm-card/40",
          )}
          data-testid="procurement-spend-card"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                Spend this month{spend.period_label ? ` · ${spend.period_label}` : ""}
              </p>
              {spend.budget_entered ? (
                <p
                  className={cn(
                    "font-mono text-xl mt-1",
                    (spend.gap || 0) > 0 ? "text-helm-status-negative" : "text-helm-fg",
                  )}
                >
                  ${Number(spend.actual || 0).toLocaleString()} actual vs $
                  {Number(spend.budget || 0).toLocaleString()} budget
                  {(spend.gap || 0) > 0
                    ? ` · overrun $${Number(spend.gap).toLocaleString()}`
                    : ""}
                </p>
              ) : (
                <p className="font-mono text-xl text-helm-fg mt-1">
                  ${Number(spend.actual || 0).toLocaleString()}
                  <span className="text-sm text-helm-muted ml-2">no budget set</span>
                </p>
              )}
              {(spend.unpriced_count || 0) > 0 && (
                <p className="text-xs text-helm-status-warning mt-1" data-testid="procurement-unpriced-count">
                  {spend.unpriced_count} request{spend.unpriced_count === 1 ? "" : "s"} have no cost
                  recorded — total above may be incomplete
                </p>
              )}
              <p className="text-[11px] text-helm-muted mt-1.5">
                Delivered requests with a cost also post as Procurement expenses in Financials (burn).
              </p>
            </div>
            {canManageBudget && (
              <div className="flex flex-wrap items-end gap-2" data-testid="procurement-budget-controls">
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase text-helm-muted">Monthly budget</span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={budgetDraft}
                    onChange={(e) => setBudgetDraft(e.target.value)}
                    placeholder="Optional"
                    className="w-36 rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
                    data-testid="procurement-budget-input"
                  />
                </label>
                <button
                  type="button"
                  disabled={budgetBusy}
                  onClick={saveProcurementBudget}
                  className="rounded-md bg-helm-gold text-helm-navy text-xs font-medium px-2.5 py-1.5 disabled:opacity-50"
                  data-testid="procurement-budget-save"
                >
                  Save
                </button>
                {spend.budget_entered && (
                  <button
                    type="button"
                    disabled={budgetBusy}
                    onClick={clearProcurementBudget}
                    className="rounded-md border border-helm-line text-helm-muted text-xs px-2.5 py-1.5 disabled:opacity-50"
                    data-testid="procurement-budget-clear"
                  >
                    Clear
                  </button>
                )}
              </div>
            )}
          </div>
          {((spend.by_vendor || []).length > 0 || (spend.by_item || []).length > 0) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 border-t border-helm-line/60">
              <div data-testid="procurement-spend-by-vendor">
                <p className="text-[10px] font-mono uppercase text-helm-muted mb-1">By vendor</p>
                <ul className="space-y-0.5 text-xs font-mono text-helm-muted">
                  {(spend.by_vendor || []).slice(0, 6).map((v) => (
                    <li key={v.vendor_name}>
                      <span className="text-helm-fg">{v.vendor_name}</span>
                      {": $"}
                      {Number(v.total || 0).toLocaleString()}
                      {" · "}
                      {v.count}
                    </li>
                  ))}
                </ul>
              </div>
              <div data-testid="procurement-spend-by-item">
                <p className="text-[10px] font-mono uppercase text-helm-muted mb-1">By item</p>
                <ul className="space-y-0.5 text-xs font-mono text-helm-muted">
                  {(spend.by_item || []).slice(0, 6).map((v) => (
                    <li key={v.item}>
                      <span className="text-helm-fg">{v.item}</span>
                      {": $"}
                      {Number(v.total || 0).toLocaleString()}
                      {" · "}
                      {v.count}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-3 mb-4">
        <p className="text-xs text-helm-muted font-mono">
          {visible.length} shown · {allRequests.length} total
        </p>
        <label className="inline-flex items-center gap-2 text-xs text-helm-muted cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="procurement-show-closed"
            checked={showClosed}
            onChange={(e) => setShowClosed(e.target.checked)}
            className="rounded border-helm-fg/20 bg-transparent"
          />
          Show delivered &amp; rejected
        </label>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Package}
          title={allRequests.length ? "No open requests" : "No requests yet"}
          body={
            allRequests.length
              ? "Turn on “Show delivered & rejected” to see closed items, or submit a new request."
              : "Submit a purchase request to start the queue."
          }
          action={(
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"
            >
              <Plus className="w-4 h-4" /> New request
            </button>
          )}
        />
      ) : (
        <div className="overflow-x-auto rounded-md border border-helm-line mb-6">
          <table className="w-full text-left text-sm" data-testid="procurement-table">
            <thead>
              <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                <th className="px-3 py-2 font-medium">Item</th>
                <th className="px-3 py-2 font-medium">Qty</th>
                <th className="px-3 py-2 font-medium">Vendor</th>
                <th className="px-3 py-2 font-medium">Requester</th>
                <th className="px-3 py-2 font-medium">Expected</th>
                <th className="px-3 py-2 font-medium">Priority</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((req) => (
                <tr
                  key={req.id}
                  data-testid={`procurement-row-${req.id}`}
                  onClick={() => setSelectedId(req.id)}
                  className={cn(
                    "border-b border-helm-line cursor-pointer transition-colors hover:bg-helm-fg/[0.03]",
                    selectedId === req.id && "bg-helm-gold/12",
                  )}
                >
                  <td className="px-3 py-2.5 text-helm-fg max-w-[14rem]">
                    <div className="flex flex-col gap-1 min-w-0">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="truncate">{req.item}</span>
                        <PossiblyStaleBadge show={req.possibly_stale} />
                      </div>
                      <BlockingProductionBadge
                        orders={req.blocking_production_orders}
                        requestId={req.id}
                      />
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-helm-fg font-mono text-xs">{req.quantity}</td>
                  <td className="px-3 py-2.5 text-helm-muted truncate max-w-[10rem]">{req.vendor_name || "—"}</td>
                  <td className="px-3 py-2.5 text-helm-muted truncate max-w-[10rem]">{personLabel(req.requester)}</td>
                  <td
                    className={cn(
                      "px-3 py-2.5 font-mono text-xs",
                      isExpectedDeliveryOverdue(req.expected_delivery_date, req.status)
                        ? "text-helm-status-negative"
                        : "text-helm-muted",
                    )}
                  >
                    {req.expected_delivery_date
                      ? (isExpectedDeliveryOverdue(req.expected_delivery_date, req.status)
                        ? `Overdue ${req.expected_delivery_date}`
                        : req.expected_delivery_date)
                      : "—"}
                  </td>
                  <td className="px-3 py-2.5"><PriorityBadge priority={req.priority} /></td>
                  <td className="px-3 py-2.5"><StatusBadge status={req.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && draft && (
        <GlassCard className="p-5 space-y-4" data-testid="procurement-detail">
          <div className="flex items-start justify-between gap-3">
            <div>
              <SectionLabel>Request detail</SectionLabel>
              <p className="text-helm-fg text-sm mt-1">{selected.item}</p>
              {(selected.blocking_production_orders || []).length > 0 && (
                <div className="mt-2">
                  <BlockingProductionBadge
                    orders={selected.blocking_production_orders}
                    requestId={selected.id}
                  />
                </div>
              )}
            </div>
            <button type="button" onClick={() => setSelectedId(null)} className="text-helm-muted hover:text-helm-fg">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Item</span>
              <input
                data-testid="procurement-edit-item"
                disabled={!canEditContent || busy}
                value={draft.item}
                onChange={(e) => setDraft((d) => ({ ...d, item: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Quantity</span>
              <input
                data-testid="procurement-edit-qty"
                disabled={!canEditContent || busy}
                value={draft.quantity}
                onChange={(e) => setDraft((d) => ({ ...d, quantity: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Vendor</span>
              <VendorPicker
                testId="procurement-edit-vendor"
                customTestId="procurement-edit-vendor-custom"
                disabled={!canEditContent || busy}
                value={draft.vendor_name}
                onChange={(vendor_name) => setDraft((d) => ({ ...d, vendor_name }))}
                knownVendors={knownVendors}
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Cost</span>
              <input
                data-testid="procurement-edit-cost"
                disabled={!canEditContent || busy}
                value={draft.cost}
                onChange={(e) => setDraft((d) => ({ ...d, cost: e.target.value }))}
                placeholder="Optional"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Priority</span>
              <select
                data-testid="procurement-edit-priority"
                disabled={busy || !(canEditContent || canApprove)}
                value={draft.priority || "normal"}
                onChange={(e) => setDraft((d) => ({ ...d, priority: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Expected delivery</span>
              <input
                data-testid="procurement-edit-expected-delivery"
                type="date"
                disabled={busy || !(canEditContent || canApprove)}
                value={draft.expected_delivery_date || ""}
                onChange={(e) => setDraft((d) => ({ ...d, expected_delivery_date: e.target.value }))}
                className={cn(
                  "w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm disabled:opacity-50",
                  isExpectedDeliveryOverdue(draft.expected_delivery_date, selected.status)
                    ? "text-helm-status-negative"
                    : "text-helm-fg",
                )}
              />
            </label>
          </div>

          <label className="block space-y-1">
            <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Notes</span>
            <textarea
              data-testid="procurement-edit-notes"
              disabled={!canEditContent || busy}
              value={draft.notes}
              onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
              rows={3}
              className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
            />
          </label>

          <div className="flex flex-wrap gap-4 text-xs text-helm-muted">
            <span>Requester: <span className="text-helm-fg">{personLabel(selected.requester)}</span></span>
            <span>Approver: <span className="text-helm-fg">{personLabel(selected.approver)}</span></span>
            <span>Status: <StatusBadge status={selected.status} /></span>
          </div>

          <div
            className="grid grid-cols-1 sm:grid-cols-3 gap-3 rounded-md border border-helm-line bg-helm-fg/[0.02] p-3"
            data-testid="procurement-lead-time-detail"
          >
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Sourcing time</p>
              <p className={cn("text-sm mt-0.5", selected.lead_time?.sourcing_tracked ? "text-helm-fg" : "text-helm-muted")}>
                {formatLeadMetric(selected.lead_time?.sourcing_tracked, selected.lead_time?.sourcing_days)}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Fulfillment time</p>
              <p className={cn("text-sm mt-0.5", selected.lead_time?.fulfillment_tracked ? "text-helm-fg" : "text-helm-muted")}>
                {formatLeadMetric(selected.lead_time?.fulfillment_tracked, selected.lead_time?.fulfillment_days)}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Fulfillment delay</p>
              <p
                className={cn(
                  "text-sm mt-0.5",
                  !selected.lead_time?.delay_tracked
                    ? "text-helm-muted"
                    : (selected.lead_time?.fulfillment_delay_days || 0) > 0
                      ? "text-helm-status-negative"
                      : "text-helm-fg",
                )}
              >
                {formatLeadMetric(
                  selected.lead_time?.delay_tracked,
                  selected.lead_time?.fulfillment_delay_days,
                  { signed: true },
                )}
              </p>
            </div>
            {selected.actual_delivery_date && (
              <p className="sm:col-span-3 text-[11px] text-helm-muted">
                Delivered {selected.actual_delivery_date}
                {selected.ordered_at ? ` · ordered ${String(selected.ordered_at).slice(0, 10)}` : ""}
                {selected.vendor_selected_at ? ` · vendor locked ${String(selected.vendor_selected_at).slice(0, 10)}` : ""}
              </p>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            {(canEditContent || canApprove) && (
              <button
                type="button"
                disabled={busy}
                data-testid="procurement-save-btn"
                onClick={() => saveRequest()}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Save changes
              </button>
            )}
            {canApprove && selected.status === "requested" && (
              <>
                <button
                  type="button"
                  disabled={busy}
                  data-testid="procurement-approve-btn"
                  onClick={() => setStatus("approved")}
                  className="rounded-md border border-helm-muted/35 text-helm-muted text-sm px-3 py-2 hover:bg-helm-muted/10 disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  type="button"
                  disabled={busy}
                  data-testid="procurement-reject-btn"
                  onClick={() => setStatus("rejected")}
                  className="rounded-md border border-helm-status-negative/35 text-helm-status-negative text-sm px-3 py-2 hover:bg-helm-status-negative/10 disabled:opacity-50"
                >
                  Reject
                </button>
              </>
            )}
            {selected.status === "approved" && (
              <button
                type="button"
                disabled={busy}
                data-testid="procurement-ordered-btn"
                onClick={() => setStatus("ordered")}
                className="rounded-md border border-helm-status-warning/35 text-helm-status-warning text-sm px-3 py-2 hover:bg-helm-status-warning/10 disabled:opacity-50"
              >
                Mark ordered
              </button>
            )}
            {selected.status === "ordered" && (
              <button
                type="button"
                disabled={busy}
                data-testid="procurement-delivered-btn"
                onClick={() => setStatus("delivered")}
                className="rounded-md border border-helm-status-positive/35 text-helm-status-positive text-sm px-3 py-2 hover:bg-helm-status-positive/10 disabled:opacity-50"
              >
                Mark delivered
              </button>
            )}
            {canDeleteSelected && (
              <CirDeleteBtn
                disabled={busy}
                data-testid="procurement-delete-btn"
                onClick={() => setConfirmDelete(true)}
                size="md"
                title="Delete request"
                className="ml-auto"
              />
            )}
          </div>
        </GlassCard>
      )}

      {orderDatePrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="order-date-prompt">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setOrderDatePrompt(null)} />
          <div className="relative w-full max-w-sm rounded-md border border-helm-line bg-helm-card p-5 space-y-3">
            <p className="text-sm font-medium text-helm-fg">Expected delivery date?</p>
            <p className="text-sm text-helm-muted leading-relaxed">
              Optional: add a vendor delivery date so Trenston can flag this request if it runs late.
            </p>
            <input
              type="date"
              data-testid="order-date-prompt-input"
              value={orderDatePrompt.date}
              onChange={(e) => setOrderDatePrompt((s) => ({ ...s, date: e.target.value }))}
              className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
            />
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                disabled={busy}
                data-testid="order-date-prompt-skip"
                onClick={() => confirmOrderDatePrompt({ skip: true })}
                className="rounded-md border border-helm-line text-sm px-3 py-2 text-helm-fg"
              >
                Skip
              </button>
              <button
                type="button"
                disabled={busy}
                data-testid="order-date-prompt-confirm"
                onClick={() => confirmOrderDatePrompt()}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover"
              >
                Save &amp; mark ordered
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete && Boolean(selected)}
        title={`Delete request “${selected?.item || ""}”?`}
        description="This permanently removes the purchase request. This can’t be undone."
        confirmLabel="Delete request"
        busy={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={deleteRequest}
        testId="delete-procurement-confirm"
      />

      {adding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setAdding(false)} />
          <div className="relative w-full max-w-md rounded-md border border-helm-line bg-helm-card p-5 space-y-3" data-testid="procurement-create-modal">
            <div className="flex items-center justify-between">
              <p className="text-sm text-helm-fg font-medium">New purchase request</p>
              <button type="button" onClick={() => setAdding(false)} className="text-helm-muted hover:text-helm-fg">
                <X className="w-4 h-4" />
              </button>
            </div>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Item</span>
              <input
                data-testid="procurement-new-item"
                value={form.item}
                onChange={(e) => setForm((f) => ({ ...f, item: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                autoFocus
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Quantity</span>
                <input
                  data-testid="procurement-new-qty"
                  value={form.quantity}
                  onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Cost</span>
                <input
                  data-testid="procurement-new-cost"
                  value={form.cost}
                  onChange={(e) => setForm((f) => ({ ...f, cost: e.target.value }))}
                  placeholder="Optional"
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                />
              </label>
            </div>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Vendor</span>
              <VendorPicker
                testId="procurement-new-vendor"
                customTestId="procurement-new-vendor-custom"
                value={form.vendor_name}
                onChange={(vendor_name) => setForm((f) => ({ ...f, vendor_name }))}
                knownVendors={knownVendors}
              />
            </label>

            {vendorSuggestions.length > 0 && (
              <div className="space-y-1" data-testid="vendor-suggestions">
                <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Suggested from history</p>
                {vendorSuggestions.map((s) => (
                  <button
                    key={s.vendor_name}
                    type="button"
                    data-testid={`vendor-suggestion-${s.vendor_name}`}
                    onClick={() => {
                      setForm((f) => ({
                        ...f,
                        vendor_name: s.vendor_name,
                        cost: s.last_cost == null ? f.cost : String(s.last_cost),
                      }));
                      setVendorNote(s.price_changed ? "Price has changed since last order" : "");
                    }}
                    className="w-full text-left rounded-md border border-helm-line px-3 py-2 text-xs text-helm-fg hover:border-helm-gold/35 hover:bg-helm-gold/10"
                  >
                    <span className="font-medium">{s.vendor_name}</span>
                    <span className="text-helm-muted">
                      {" · "}
                      {s.last_cost != null ? `last paid $${Number(s.last_cost).toFixed(2)}` : "no cost on file"}
                      {`, ordered ${s.times_used}x`}
                      {s.last_ordered_at ? `, most recently ${String(s.last_ordered_at).slice(0, 10)}` : ""}
                    </span>
                    <span className="block text-helm-muted mt-0.5">
                      {s.delay_sample_count
                        ? `Avg delay ${formatLeadMetric(true, s.avg_fulfillment_delay_days, { signed: true })}`
                        : "Delay not tracked"}
                      {" · "}
                      {s.fulfillment_sample_count
                        ? `Avg fulfillment ${formatDays(s.avg_fulfillment_days)}`
                        : "Fulfillment not tracked"}
                    </span>
                  </button>
                ))}
                {vendorNote ? (
                  <p className="text-[11px] text-helm-status-warning" data-testid="vendor-price-changed-note">{vendorNote}</p>
                ) : null}
              </div>
            )}
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Priority</span>
              <select
                data-testid="procurement-new-priority"
                value={form.priority || "normal"}
                onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Expected delivery</span>
              <input
                data-testid="procurement-new-expected-delivery"
                type="date"
                value={form.expected_delivery_date}
                onChange={(e) => setForm((f) => ({ ...f, expected_delivery_date: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Notes</span>
              <textarea
                data-testid="procurement-new-notes"
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                rows={2}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              />
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setAdding(false)} className="text-sm text-helm-muted px-3 py-2">Cancel</button>
              <button
                type="button"
                disabled={busy}
                data-testid="procurement-create-submit"
                onClick={createRequest}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Submit request
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
