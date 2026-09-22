import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, X, Factory } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import {
  PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, ConfirmDialog,
  SkeletonKPIRow, SkeletonCardList,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { PossiblyStaleBadge } from "@/components/AiSummaryMeta";

const STATUS_META = {
  awaiting_materials: {
    label: "Awaiting materials",
    className: "bg-helm-status-warning/12 text-helm-fg border-helm-status-warning/35",
  },
  in_production: {
    label: "In production",
    className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35",
  },
  quality_check: {
    label: "Quality check",
    className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35",
  },
  completed: {
    label: "Completed",
    className: "bg-helm-status-positive/12 text-helm-fg border-helm-status-positive/35",
  },
};

const STATUS_ORDER = ["awaiting_materials", "in_production", "quality_check", "completed"];
const CLOSED = new Set(["completed"]);

const CATEGORY_LABELS = {
  material: "Material",
  labor: "Labor",
  machine: "Machine",
  quality: "Quality",
  other: "Other",
};

const PROC_STATUS_LABELS = {
  requested: "Requested",
  approved: "Approved",
  ordered: "Ordered",
  delivered: "Delivered",
  rejected: "Rejected",
};

const MAINT_STATUS_LABELS = {
  reported: "Reported",
  diagnosed: "Diagnosed",
  in_repair: "In repair",
  resolved: "Resolved",
};

const PRIORITY_RANK = { high: 0, normal: 1, low: 2 };

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.in_production;
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide border", meta.className)}>
      {meta.label}
    </span>
  );
}

function isDueDateOverdue(dueDate, status) {
  if (CLOSED.has(status)) return false;
  const raw = (dueDate || "").trim();
  if (!raw) return false;
  const end = new Date(`${raw}T23:59:59`);
  if (Number.isNaN(end.getTime())) return false;
  return end.getTime() < Date.now();
}

function formatCycleTime(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return null;
  const s = Number(seconds);
  if (s >= 86400) {
    const days = s / 86400;
    return `${days >= 10 ? Math.round(days) : days.toFixed(1).replace(/\.0$/, "")}d`;
  }
  if (s >= 3600) {
    const hours = s / 3600;
    return `${hours >= 10 ? Math.round(hours) : hours.toFixed(1).replace(/\.0$/, "")}h`;
  }
  return `${Math.max(1, Math.round(s / 60))}m`;
}

function compareOrders(a, b) {
  const aClosed = CLOSED.has(a?.status);
  const bClosed = CLOSED.has(b?.status);
  if (aClosed !== bClosed) return aClosed ? 1 : -1;
  const pa = PRIORITY_RANK[a?.priority] ?? PRIORITY_RANK.normal;
  const pb = PRIORITY_RANK[b?.priority] ?? PRIORITY_RANK.normal;
  if (pa !== pb) return pa - pb;
  const da = (a?.due_date || "").trim();
  const db = (b?.due_date || "").trim();
  if (da && db && da !== db) return da < db ? -1 : 1;
  if (da && !db) return -1;
  if (!da && db) return 1;
  return String(a?.reference || "").localeCompare(String(b?.reference || ""));
}

const emptyForm = () => ({
  reference: "",
  product: "",
  quantity_planned: "",
  customer: "",
  priority: "normal",
  due_date: "",
  linked_procurement_request_id: "",
  linked_maintenance_ticket_id: "",
  notes: "",
  unit: "",
  yield_tracking_enabled: false,
  expected_yield_pct: "",
  input_unit: "",
});

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function emptyDailyLog(unit = "") {
  return {
    date: todayIso(),
    target_quantity: "",
    actual_quantity: "",
    unit: unit || "",
    overtime_hours: "",
    input_quantity: "",
    input_unit: "",
    notes: "",
  };
}

function formatQty(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
}

const CUSTOM_UNIT = "__custom__";

/** Pick-list + free-text custom unit. Never invents a default. */
function UnitField({
  value,
  onChange,
  commonUnits,
  disabled,
  testId,
  placeholder = "kg, liters, boxes…",
  required = false,
}) {
  const known = commonUnits || [];
  const knownKey = known.join("|");
  const current = (value || "").trim();
  const isKnown = known.includes(current);
  const [mode, setMode] = useState(() => {
    if (!current) return "";
    return isKnown ? current : CUSTOM_UNIT;
  });

  useEffect(() => {
    if (!current) {
      setMode("");
      return;
    }
    setMode(known.includes(current) ? current : CUSTOM_UNIT);
    // knownKey tracks list identity without re-running on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, knownKey]);

  const selectValue = mode === CUSTOM_UNIT ? CUSTOM_UNIT : (current && isKnown ? current : mode || "");

  return (
    <div className="space-y-1.5" data-testid={testId ? `${testId}-wrap` : undefined}>
      <select
        data-testid={testId}
        disabled={disabled}
        value={selectValue}
        required={required}
        onChange={(e) => {
          const v = e.target.value;
          if (v === CUSTOM_UNIT) {
            setMode(CUSTOM_UNIT);
            if (isKnown || !current) onChange("");
            return;
          }
          setMode(v);
          onChange(v);
        }}
        className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
      >
        <option value="">{required ? "Select unit…" : "No unit set"}</option>
        {known.map((u) => (
          <option key={u} value={u}>{u}</option>
        ))}
        <option value={CUSTOM_UNIT}>Custom…</option>
      </select>
      {mode === CUSTOM_UNIT && (
        <input
          data-testid={testId ? `${testId}-custom` : undefined}
          disabled={disabled}
          value={current}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
        />
      )}
    </div>
  );
}

export default function Production() {
  const { data, loading, error, reload } = useFetch("/production/work-orders");
  const { data: membersData } = useFetch("/members");
  const [showClosed, setShowClosed] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [completing, setCompleting] = useState(false);
  const [completeQty, setCompleteQty] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDeleteLogId, setConfirmDeleteLogId] = useState(null);
  const [dailyLogs, setDailyLogs] = useState([]);
  const [dailyRollup, setDailyRollup] = useState(null);
  const [logForm, setLogForm] = useState(emptyDailyLog);
  const [otRateDraft, setOtRateDraft] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);

  const allOrders = useMemo(
    () => [...(data?.work_orders || [])].sort(compareOrders),
    [data?.work_orders],
  );
  const visible = useMemo(
    () => (showClosed ? allOrders : allOrders.filter((o) => !CLOSED.has(o.status))),
    [allOrders, showClosed],
  );
  const selected = useMemo(
    () => allOrders.find((o) => o.id === selectedId) || null,
    [allOrders, selectedId],
  );
  const openProcurement = data?.open_procurement_requests || [];
  const openMaintenance = data?.open_maintenance_tickets || [];
  const priorities = data?.priorities || ["low", "normal", "high"];
  const blockedCategories = data?.blocked_categories || Object.keys(CATEGORY_LABELS);
  const statuses = data?.statuses || STATUS_ORDER;
  const commonUnits = data?.common_units || ["units", "kg", "liters", "boxes", "meters"];
  const todaySummary = data?.today_summary || null;
  const overtimeWeek = data?.overtime_week || null;
  const canManageSettings = Boolean(data?.is_lead || data?.is_ceo);
  const myId = data?.my_user_id;
  const workspaceMembers = (membersData?.members || []).filter(
    (m) => m.user_id && m.status === "active",
  );
  const cycleLabel = formatCycleTime(data?.average_cycle_time?.average_seconds);

  useEffect(() => {
    setOtRateDraft(
      data?.overtime_rate_per_hour == null ? "" : String(data.overtime_rate_per_hour),
    );
  }, [data?.overtime_rate_per_hour]);

  useEffect(() => {
    if (!selected) {
      setDraft(null);
      setCompleting(false);
      setDailyLogs([]);
      setDailyRollup(null);
      return;
    }
    setDraft({
      reference: selected.reference || "",
      product: selected.product || "",
      quantity_planned: selected.quantity_planned == null ? "" : String(selected.quantity_planned),
      quantity_produced: selected.quantity_produced == null ? "" : String(selected.quantity_produced),
      customer: selected.customer || "",
      priority: selected.priority || "normal",
      due_date: selected.due_date || "",
      status: selected.status || "in_production",
      blocked: Boolean(selected.blocked),
      blocked_category: selected.blocked_reason?.category || "",
      blocked_detail: selected.blocked_reason?.detail || "",
      linked_procurement_request_id: selected.linked_procurement_request_id || "",
      linked_maintenance_ticket_id: selected.linked_maintenance_ticket_id || "",
      assigned_user_ids: [...(selected.assigned_user_ids || [])],
      notes: selected.notes || "",
      unit: selected.unit || "",
      yield_tracking_enabled: Boolean(selected.yield_tracking_enabled),
      expected_yield_pct: selected.expected_yield_pct == null ? "" : String(selected.expected_yield_pct),
      input_unit: selected.input_unit || "",
    });
    setLogForm(emptyDailyLog(selected.unit || ""));
    setCompleting(false);
  }, [selected]);

  useEffect(() => {
    setConfirmDeleteLogId(null);
    if (!selectedId) return undefined;
    let cancelled = false;
    setLogsLoading(true);
    (async () => {
      try {
        const { data: res } = await api.get(`/production/work-orders/${selectedId}/daily-logs`);
        if (cancelled) return;
        setDailyLogs(res?.logs || []);
        setDailyRollup(res?.rollup || null);
      } catch {
        if (!cancelled) {
          setDailyLogs([]);
          setDailyRollup(null);
        }
      } finally {
        if (!cancelled) setLogsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedId]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Production" subtitle="Work order queue with fixed statuses and no pipeline setup." />
        <SkeletonKPIRow count={4} />
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
          message="You are not a member of Production. Ask your CEO to add you."
          onRetry={reload}
        />
      );
    }
    if (status === 404) {
      return (
        <ErrorScreen
          label="Production not enabled"
          message="Enable Production under Settings → Departments first."
          onRetry={reload}
        />
      );
    }
    return (
      <ErrorScreen
        label="Could not load Production"
        message={fetchErrorMessage(error, "Production data is unavailable.")}
        onRetry={reload}
      />
    );
  }

  const createOrder = async () => {
    if (!form.reference.trim()) {
      toast.error("Reference is required");
      return;
    }
    const body = {
      reference: form.reference.trim(),
      product: form.product.trim(),
      customer: form.customer.trim(),
      priority: form.priority || "normal",
      due_date: form.due_date.trim(),
      notes: form.notes.trim(),
      linked_procurement_request_id: form.linked_procurement_request_id || null,
      linked_maintenance_ticket_id: form.linked_maintenance_ticket_id || null,
      unit: (form.unit || "").trim(),
      yield_tracking_enabled: Boolean(form.yield_tracking_enabled),
      input_unit: form.yield_tracking_enabled ? (form.input_unit || "").trim() : "",
    };
    if (!body.unit) {
      toast.error("Choose a unit (kg, liters, boxes, or type your own)");
      return;
    }
    if (!body.product) {
      toast.error("What is being produced? Enter a product name");
      return;
    }
    if (form.quantity_planned !== "") {
      const q = Number(form.quantity_planned);
      if (!Number.isFinite(q)) {
        toast.error("Quantity planned must be a number");
        return;
      }
      body.quantity_planned = q;
    }
    if (form.yield_tracking_enabled && form.expected_yield_pct.trim() !== "") {
      const ey = Number(form.expected_yield_pct);
      if (!Number.isFinite(ey) || ey < 0 || ey > 100) {
        toast.error("Expected yield must be 0–100");
        return;
      }
      body.expected_yield_pct = ey;
    }
    setBusy(true);
    try {
      const { data: res } = await api.post("/production/work-orders", body);
      toast.success("Work order created");
      setForm(emptyForm());
      setAdding(false);
      await reload();
      if (res?.work_order?.id) setSelectedId(res.work_order.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create work order");
    } finally {
      setBusy(false);
    }
  };

  const saveOrder = async (overrides = {}) => {
    if (!selected || !draft) return;
    const body = { ...overrides };
    body.reference = draft.reference.trim();
    body.product = draft.product.trim();
    body.customer = draft.customer.trim();
    body.priority = draft.priority;
    body.due_date = draft.due_date.trim();
    body.notes = draft.notes;
    body.assigned_user_ids = draft.assigned_user_ids;
    body.linked_procurement_request_id = draft.linked_procurement_request_id || "";
    body.linked_maintenance_ticket_id = draft.linked_maintenance_ticket_id || "";
    body.blocked = Boolean(draft.blocked);
    body.unit = (draft.unit || "").trim();
    if (!body.unit) {
      toast.error("Choose a unit (kg, liters, boxes, or type your own)");
      return;
    }
    body.yield_tracking_enabled = Boolean(draft.yield_tracking_enabled);
    body.input_unit = draft.yield_tracking_enabled ? (draft.input_unit || "").trim() : "";
    if (!(draft.product || "").trim()) {
      toast.error("What is being produced? Enter a product name");
      return;
    }
    if (draft.yield_tracking_enabled && draft.expected_yield_pct.trim() !== "") {
      const ey = Number(draft.expected_yield_pct);
      if (!Number.isFinite(ey) || ey < 0 || ey > 100) {
        toast.error("Expected yield must be 0–100");
        return;
      }
      body.expected_yield_pct = ey;
    }
    if (draft.blocked) {
      body.blocked_reason = {
        category: draft.blocked_category,
        detail: draft.blocked_detail,
      };
    } else {
      body.blocked_reason = null;
    }
    if (draft.quantity_planned === "") body.quantity_planned = null;
    else {
      const q = Number(draft.quantity_planned);
      if (!Number.isFinite(q)) {
        toast.error("Quantity planned must be a number");
        return;
      }
      body.quantity_planned = q;
    }
    if (draft.quantity_produced !== "" && draft.quantity_produced != null) {
      const q = Number(draft.quantity_produced);
      if (!Number.isFinite(q)) {
        toast.error("Quantity produced must be a number");
        return;
      }
      body.quantity_produced = q;
    }
    if (!("status" in body)) body.status = draft.status;

    setBusy(true);
    try {
      const { data: res } = await api.patch(`/production/work-orders/${selected.id}`, body);
      toast.success("Work order updated");
      await reload();
      if (res?.work_order?.id) setSelectedId(res.work_order.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update work order");
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status) => {
    if (status === "completed") {
      const planned = selected?.quantity_planned;
      setCompleteQty(planned == null ? "" : String(planned));
      setCompleting(true);
      return;
    }
    await saveOrder({ status });
  };

  const confirmComplete = async () => {
    const q = Number(completeQty);
    if (!Number.isFinite(q)) {
      toast.error("Enter quantity produced");
      return;
    }
    setBusy(true);
    try {
      const { data: res } = await api.patch(`/production/work-orders/${selected.id}`, {
        status: "completed",
        quantity_produced: q,
      });
      toast.success("Work order completed");
      setCompleting(false);
      await reload();
      if (res?.work_order?.id) setSelectedId(res.work_order.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not complete");
    } finally {
      setBusy(false);
    }
  };

  const deleteOrder = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.delete(`/production/work-orders/${selected.id}`);
      toast.success("Work order deleted");
      setConfirmDelete(false);
      setSelectedId(null);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    } finally {
      setBusy(false);
    }
  };

  const deleteDailyLog = async () => {
    if (!confirmDeleteLogId || !selected) return;
    setBusy(true);
    try {
      await api.delete(`/production/daily-logs/${confirmDeleteLogId}`);
      toast.success("Daily log deleted");
      setConfirmDeleteLogId(null);
      const { data: res } = await api.get(`/production/work-orders/${selected.id}/daily-logs`);
      setDailyLogs(res?.logs || []);
      setDailyRollup(res?.rollup || null);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete daily log");
    } finally {
      setBusy(false);
    }
  };

  const saveOvertimeRate = async () => {
    if (!canManageSettings) return;
    const raw = otRateDraft.trim();
    if (raw === "") {
      toast.error("Enter an overtime rate per hour");
      return;
    }
    const rate = Number(raw);
    if (!Number.isFinite(rate) || rate < 0) {
      toast.error("Overtime rate must be a non-negative number");
      return;
    }
    setBusy(true);
    try {
      await api.put("/production/settings", { overtime_rate_per_hour: rate });
      toast.success("Overtime rate saved");
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save overtime rate");
    } finally {
      setBusy(false);
    }
  };

  const saveDailyLog = async () => {
    if (!selected) return;
    const date = (logForm.date || "").trim();
    if (!date) {
      toast.error("Date is required");
      return;
    }
    const body = {
      date,
      unit: (logForm.unit || draft?.unit || "").trim(),
      notes: (logForm.notes || "").trim(),
    };
    if (!body.unit) {
      toast.error("Choose a unit for today's log");
      return;
    }
    if (logForm.target_quantity.trim() === "" && logForm.actual_quantity.trim() === "") {
      toast.error("Enter today's target and/or actual quantity");
      return;
    }
    if (logForm.target_quantity.trim() !== "") {
      const t = Number(logForm.target_quantity);
      if (!Number.isFinite(t) || t < 0) {
        toast.error("Target must be a non-negative number");
        return;
      }
      body.target_quantity = t;
    }
    if (logForm.actual_quantity.trim() !== "") {
      const a = Number(logForm.actual_quantity);
      if (!Number.isFinite(a) || a < 0) {
        toast.error("Actual must be a non-negative number");
        return;
      }
      body.actual_quantity = a;
    }
    if (logForm.overtime_hours.trim() !== "") {
      const ot = Number(logForm.overtime_hours);
      if (!Number.isFinite(ot) || ot < 0) {
        toast.error("Overtime hours must be a non-negative number");
        return;
      }
      body.overtime_hours = ot;
    }
    if (draft?.yield_tracking_enabled) {
      body.input_unit = (logForm.input_unit || draft.input_unit || "").trim();
      if (logForm.input_quantity.trim() !== "") {
        const iq = Number(logForm.input_quantity);
        if (!Number.isFinite(iq) || iq < 0) {
          toast.error("Input quantity must be a non-negative number");
          return;
        }
        body.input_quantity = iq;
      }
    }
    setBusy(true);
    try {
      await api.post(`/production/work-orders/${selected.id}/daily-logs`, body);
      toast.success("Daily log saved");
      setLogForm(emptyDailyLog(draft?.unit || ""));
      const { data: res } = await api.get(`/production/work-orders/${selected.id}/daily-logs`);
      setDailyLogs(res?.logs || []);
      setDailyRollup(res?.rollup || null);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save daily log");
    } finally {
      setBusy(false);
    }
  };

  const toggleAssignee = (userId) => {
    setDraft((d) => {
      if (!d) return d;
      const has = d.assigned_user_ids.includes(userId);
      return {
        ...d,
        assigned_user_ids: has
          ? d.assigned_user_ids.filter((id) => id !== userId)
          : [...d.assigned_user_ids, userId],
      };
    });
  };

  const action = (
    <button
      type="button"
      data-testid="add-work-order-btn"
      onClick={() => setAdding(true)}
      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover"
    >
      <Plus className="w-4 h-4" /> New work order
    </button>
  );

  return (
    <div data-testid="production-page">
      <PageHeader
        title={data?.name || "Production"}
        subtitle="Work order queue with fixed statuses and no pipeline setup."
        action={action}
      />

      <div
        className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5"
        data-testid="production-ops-summary"
      >
        <div className="rounded-md border border-helm-line bg-helm-card/40 px-3 py-2.5" data-testid="production-today-output">
          <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-helm-muted">Today&apos;s output</p>
          {todaySummary?.has_data && todaySummary.mixed_units ? (
            <div className="mt-1 space-y-0.5" data-testid="production-today-by-unit">
              {(todaySummary.by_unit || []).map((row) => (
                <p key={row.unit || "none"} className="font-mono text-sm text-helm-fg">
                  {formatQty(row.total_actual)} / {formatQty(row.total_target)}
                  {row.unit ? ` ${row.unit}` : ""}
                </p>
              ))}
            </div>
          ) : (
            <p className={cn("font-mono text-xl mt-1", todaySummary?.has_data ? "text-helm-fg" : "text-helm-muted")}>
              {todaySummary?.has_data
                ? `${formatQty(todaySummary.total_actual)} / ${formatQty(todaySummary.total_target)}${todaySummary.unit ? ` ${todaySummary.unit}` : ""}`
                : "No data logged"}
            </p>
          )}
          <p className="text-[11px] text-helm-muted mt-0.5">
            {todaySummary?.has_data
              ? `${todaySummary.orders_with_log} of ${todaySummary.active_work_orders} active logged${todaySummary.mixed_units ? " · mixed units" : ""}`
              : "Log daily target vs actual on open work orders"}
          </p>
        </div>
        <div className="rounded-md border border-helm-line bg-helm-card/40 px-3 py-2.5" data-testid="production-today-shortfall">
          <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-helm-muted">Today&apos;s shortfall</p>
          {todaySummary?.has_data && todaySummary.mixed_units ? (
            <div className="mt-1 space-y-0.5">
              {(todaySummary.by_unit || []).map((row) => (
                <p
                  key={`sf-${row.unit || "none"}`}
                  className={cn(
                    "font-mono text-sm",
                    (row.shortfall || 0) > 0 ? "text-helm-status-negative" : "text-helm-fg",
                  )}
                >
                  {row.shortfall != null ? formatQty(row.shortfall) : "—"}
                  {row.unit ? ` ${row.unit}` : ""}
                </p>
              ))}
            </div>
          ) : (
            <p
              className={cn(
                "font-mono text-xl mt-1",
                !todaySummary?.has_data
                  ? "text-helm-muted"
                  : (todaySummary.shortfall || 0) > 0
                    ? "text-helm-status-negative"
                    : "text-helm-fg",
              )}
            >
              {todaySummary?.has_data && todaySummary.shortfall != null
                ? `${formatQty(todaySummary.shortfall)}${todaySummary.unit ? ` ${todaySummary.unit}` : ""}`
                : "No data logged"}
            </p>
          )}
        </div>
        <div className="rounded-md border border-helm-line bg-helm-card/40 px-3 py-2.5" data-testid="production-ot-week">
          <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-helm-muted">OT this week</p>
          <p className={cn("font-mono text-xl mt-1", overtimeWeek?.has_data ? "text-helm-fg" : "text-helm-muted")}>
            {overtimeWeek?.has_data
              ? (overtimeWeek.overtime_cost != null
                ? `$${Number(overtimeWeek.overtime_cost).toLocaleString()}`
                : `${formatQty(overtimeWeek.overtime_hours)}h`)
              : "No data logged"}
          </p>
          <p className="text-[11px] text-helm-muted mt-0.5">
            {overtimeWeek?.has_data && overtimeWeek.overtime_hours != null
              ? `${formatQty(overtimeWeek.overtime_hours)}h overtime`
              : "Set a rate below to price overtime"}
          </p>
        </div>
        <div className="rounded-md border border-helm-line bg-helm-card/40 px-3 py-2.5" data-testid="production-ot-rate">
          <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-helm-muted">OT rate / hour</p>
          {canManageSettings ? (
            <div className="flex items-center gap-2 mt-1">
              <input
                data-testid="overtime-rate-input"
                value={otRateDraft}
                onChange={(e) => setOtRateDraft(e.target.value)}
                placeholder="e.g. 25"
                className="w-full min-w-0 rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1 text-sm text-helm-fg font-mono"
              />
              <button
                type="button"
                disabled={busy}
                data-testid="overtime-rate-save"
                onClick={saveOvertimeRate}
                className="shrink-0 rounded-md border border-helm-line text-xs px-2 py-1.5 text-helm-fg hover:border-helm-gold/35 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          ) : (
            <p className={cn("font-mono text-xl mt-1", data?.overtime_rate_per_hour != null ? "text-helm-fg" : "text-helm-muted")}>
              {data?.overtime_rate_per_hour != null
                ? `$${Number(data.overtime_rate_per_hour).toLocaleString()}`
                : "Not set"}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <p className="text-xs text-helm-muted font-mono">
          {visible.length} shown · {allOrders.length} total
          {cycleLabel && data?.average_cycle_time?.sample_count ? (
            <span data-testid="average-cycle-time">
              {" "}· avg cycle {cycleLabel} ({data.average_cycle_time.sample_count} done)
            </span>
          ) : null}
        </p>
        <label className="inline-flex items-center gap-2 text-xs text-helm-muted cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="production-show-completed"
            checked={showClosed}
            onChange={(e) => setShowClosed(e.target.checked)}
            className="rounded border-helm-fg/20 bg-transparent"
          />
          Show completed
        </label>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Factory}
          title={allOrders.length ? "No open work orders" : "No work orders yet"}
          body={
            allOrders.length
              ? "Turn on “Show completed” to see finished jobs, or create a new work order."
              : "Create a work order to start the queue. No stage setup needed."
          }
          action={(
            <button
              type="button"
              data-testid="add-work-order-empty"
              onClick={() => setAdding(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"
            >
              <Plus className="w-4 h-4" /> New work order
            </button>
          )}
        />
      ) : (
        <div className="overflow-x-auto rounded-md border border-helm-line mb-6">
          <table className="w-full text-left text-sm" data-testid="production-table">
            <thead>
              <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                <th className="px-3 py-2 font-medium">Reference</th>
                <th className="px-3 py-2 font-medium">Product</th>
                <th className="px-3 py-2 font-medium">Target vs actual</th>
                <th className="px-3 py-2 font-medium">Customer</th>
                <th className="px-3 py-2 font-medium">Priority</th>
                <th className="px-3 py-2 font-medium">Due</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((order) => {
                const overdue = isDueDateOverdue(order.due_date, order.status);
                const rollup = order.daily_rollup;
                return (
                  <tr
                    key={order.id}
                    data-testid={`production-row-${order.id}`}
                    onClick={() => setSelectedId(order.id)}
                    className={cn(
                      "border-b border-helm-line cursor-pointer transition-colors hover:bg-helm-fg/[0.03]",
                      selectedId === order.id && "bg-helm-gold/12",
                    )}
                  >
                    <td className="px-3 py-2.5 text-helm-fg">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="truncate max-w-[12rem] font-medium">{order.reference}</span>
                        {order.blocked && (
                          <span
                            data-testid={`blocked-badge-${order.id}`}
                            className="shrink-0 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide border border-helm-status-negative/35 bg-helm-status-negative/12 text-helm-status-negative"
                            title={order.blocked_reason?.detail || ""}
                          >
                            Blocked
                            {order.blocked_reason?.category
                              ? ` · ${CATEGORY_LABELS[order.blocked_reason.category] || order.blocked_reason.category}`
                              : ""}
                          </span>
                        )}
                        <PossiblyStaleBadge show={order.possibly_stale} />
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-helm-muted truncate max-w-[10rem]">
                      {[
                        order.product || null,
                        order.quantity_planned != null
                          ? `plan ${order.quantity_planned}${order.unit ? ` ${order.unit}` : ""}`
                          : (order.unit || null),
                      ].filter(Boolean).join(" · ") || "—"}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs" data-testid={`wo-target-actual-${order.id}`}>
                      {rollup?.has_logs ? (
                        <span className={cn(
                          (rollup.cumulative_shortfall || 0) > 0 ? "text-helm-status-negative" : "text-helm-fg",
                        )}>
                          {formatQty(rollup.cumulative_actual)} / {formatQty(rollup.cumulative_target)}
                          {order.unit ? ` ${order.unit}` : ""}
                        </span>
                      ) : (
                        <span className="text-helm-muted">
                          {order.unit ? `No data logged · ${order.unit}` : "No data logged"}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-helm-muted truncate max-w-[8rem]">{order.customer || "—"}</td>
                    <td className="px-3 py-2.5 text-helm-muted capitalize">{order.priority || "normal"}</td>
                    <td className={cn("px-3 py-2.5 font-mono text-xs", overdue ? "text-helm-status-negative" : "text-helm-muted")}>
                      {order.due_date ? (overdue ? `Overdue ${order.due_date}` : order.due_date) : "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-col gap-1">
                        <StatusBadge status={order.status} />
                        {order.linked_procurement && (
                          <span className="text-[10px] text-helm-muted truncate max-w-[9rem]" data-testid={`linked-proc-${order.id}`}>
                            Proc: {order.linked_procurement.item || order.linked_procurement.id}
                            {" · "}
                            {PROC_STATUS_LABELS[order.linked_procurement.status] || order.linked_procurement.status}
                          </span>
                        )}
                        {order.linked_maintenance && (
                          <span className="text-[10px] text-helm-muted truncate max-w-[9rem]" data-testid={`linked-maint-${order.id}`}>
                            Maint: {order.linked_maintenance.equipment_name || order.linked_maintenance.id}
                            {" · "}
                            {MAINT_STATUS_LABELS[order.linked_maintenance.status] || order.linked_maintenance.status}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && draft && (
        <GlassCard className="p-5 space-y-4" data-testid="work-order-detail">
          <div className="flex items-start justify-between gap-3">
            <div>
              <SectionLabel>Work order</SectionLabel>
              <p className="text-helm-fg text-sm mt-1">{selected.reference}</p>
            </div>
            <button type="button" onClick={() => setSelectedId(null)} className="text-helm-muted hover:text-helm-fg">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Reference</span>
              <input
                data-testid="wo-reference-input"
                disabled={busy}
                value={draft.reference}
                onChange={(e) => setDraft((d) => ({ ...d, reference: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">What&apos;s being produced</span>
              <input
                data-testid="wo-product-input"
                disabled={busy}
                value={draft.product}
                onChange={(e) => setDraft((d) => ({ ...d, product: e.target.value }))}
                placeholder="Product / SKU / batch name"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Order qty planned</span>
              <input
                data-testid="wo-qty-planned"
                disabled={busy}
                value={draft.quantity_planned}
                onChange={(e) => setDraft((d) => ({ ...d, quantity_planned: e.target.value }))}
                placeholder="Total for this work order"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Unit</span>
              <UnitField
                testId="wo-unit-input"
                value={draft.unit}
                onChange={(v) => setDraft((d) => ({ ...d, unit: v }))}
                commonUnits={commonUnits}
                disabled={busy}
                required
              />
            </div>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Qty produced (on complete)</span>
              <input
                data-testid="wo-qty-produced"
                disabled={busy || draft.status !== "completed"}
                value={draft.quantity_produced}
                onChange={(e) => setDraft((d) => ({ ...d, quantity_produced: e.target.value }))}
                placeholder={draft.status === "completed" ? "Required" : "Set on complete"}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Customer</span>
              <input
                data-testid="wo-customer-input"
                disabled={busy}
                value={draft.customer}
                onChange={(e) => setDraft((d) => ({ ...d, customer: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Priority</span>
              <select
                data-testid="wo-priority-select"
                disabled={busy}
                value={draft.priority}
                onChange={(e) => setDraft((d) => ({ ...d, priority: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              >
                {priorities.map((p) => (
                  <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Due date</span>
              <input
                data-testid="wo-due-date-input"
                type="date"
                disabled={busy}
                value={draft.due_date}
                onChange={(e) => setDraft((d) => ({ ...d, due_date: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1 md:col-span-2">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Linked procurement</span>
              <select
                data-testid="wo-linked-procurement"
                disabled={busy}
                value={draft.linked_procurement_request_id}
                onChange={(e) => setDraft((d) => ({ ...d, linked_procurement_request_id: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              >
                <option value="">None</option>
                {openProcurement.map((r) => (
                  <option key={r.id} value={r.id}>
                    {(r.item || r.id)} · {PROC_STATUS_LABELS[r.status] || r.status}
                  </option>
                ))}
                {draft.linked_procurement_request_id
                  && !openProcurement.some((r) => r.id === draft.linked_procurement_request_id)
                  && selected.linked_procurement && (
                    <option value={draft.linked_procurement_request_id}>
                      {selected.linked_procurement.item || draft.linked_procurement_request_id}
                      {" · "}
                      {PROC_STATUS_LABELS[selected.linked_procurement.status] || selected.linked_procurement.status}
                    </option>
                )}
              </select>
            </label>
          </div>

          <label className="block space-y-1">
            <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Notes</span>
            <textarea
              data-testid="wo-notes-input"
              disabled={busy}
              value={draft.notes}
              onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
              rows={3}
              className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
            />
          </label>

          <div className="rounded-md border border-helm-line bg-helm-fg/[0.02] p-3 space-y-3" data-testid="wo-yield-settings">
            <label className="inline-flex items-center gap-2 text-sm text-helm-fg cursor-pointer">
              <input
                type="checkbox"
                data-testid="wo-yield-toggle"
                checked={draft.yield_tracking_enabled}
                disabled={busy}
                onChange={(e) => setDraft((d) => ({ ...d, yield_tracking_enabled: e.target.checked }))}
              />
              Track yield (input → output) for this work order
            </label>
            {draft.yield_tracking_enabled && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Input unit</span>
                  <UnitField
                    testId="wo-input-unit"
                    value={draft.input_unit}
                    onChange={(v) => setDraft((d) => ({ ...d, input_unit: v }))}
                    commonUnits={commonUnits}
                    disabled={busy}
                    placeholder="e.g. kg of raw material"
                  />
                </div>
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Expected yield %</span>
                  <input
                    data-testid="wo-expected-yield"
                    disabled={busy}
                    value={draft.expected_yield_pct}
                    onChange={(e) => setDraft((d) => ({ ...d, expected_yield_pct: e.target.value }))}
                    placeholder="Optional benchmark"
                    className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
                  />
                </label>
              </div>
            )}
          </div>

          <div className="rounded-md border border-helm-line p-3 space-y-3" data-testid="wo-daily-log-section">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div>
                <SectionLabel>Daily production log</SectionLabel>
                <p className="text-[11px] text-helm-muted mt-0.5">
                  Each day&apos;s target is set here for this work order only — not shared with other orders of the same product.
                </p>
              </div>
              {(dailyRollup || selected.daily_rollup) && (
                <p className="text-[11px] text-helm-muted font-mono" data-testid="wo-daily-rollup">
                  {(dailyRollup || selected.daily_rollup)?.has_logs
                    ? `Cum. ${formatQty((dailyRollup || selected.daily_rollup).cumulative_actual)} / ${formatQty((dailyRollup || selected.daily_rollup).cumulative_target)} ${(draft.unit || "").trim()}`
                    : "No data logged"}
                  {(dailyRollup || selected.daily_rollup)?.overtime_cost != null
                    ? ` · OT $${Number((dailyRollup || selected.daily_rollup).overtime_cost).toLocaleString()}`
                    : (dailyRollup || selected.daily_rollup)?.overtime_hours != null
                      ? ` · OT ${formatQty((dailyRollup || selected.daily_rollup).overtime_hours)}h`
                      : ""}
                  {(dailyRollup || selected.daily_rollup)?.avg_actual_yield_pct != null
                    ? ` · yield ${(dailyRollup || selected.daily_rollup).avg_actual_yield_pct}%`
                    : ""}
                </p>
              )}
            </div>

            {selected.status !== "completed" && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Date</span>
                  <input
                    type="date"
                    data-testid="daily-log-date"
                    disabled={busy}
                    value={logForm.date}
                    onChange={(e) => setLogForm((f) => ({ ...f, date: e.target.value }))}
                    className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">This day&apos;s target</span>
                  <input
                    data-testid="daily-log-target"
                    disabled={busy}
                    value={logForm.target_quantity}
                    onChange={(e) => setLogForm((f) => ({ ...f, target_quantity: e.target.value }))}
                    placeholder="Set independently each day"
                    className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">This day&apos;s actual</span>
                  <input
                    data-testid="daily-log-actual"
                    disabled={busy}
                    value={logForm.actual_quantity}
                    onChange={(e) => setLogForm((f) => ({ ...f, actual_quantity: e.target.value }))}
                    placeholder="What was produced today"
                    className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
                  />
                </label>
                <div className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Unit</span>
                  <UnitField
                    testId="daily-log-unit"
                    value={logForm.unit}
                    onChange={(v) => setLogForm((f) => ({ ...f, unit: v }))}
                    commonUnits={commonUnits}
                    disabled={busy}
                    required
                  />
                </div>
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">OT hours</span>
                  <input
                    data-testid="daily-log-overtime"
                    disabled={busy}
                    value={logForm.overtime_hours}
                    onChange={(e) => setLogForm((f) => ({ ...f, overtime_hours: e.target.value }))}
                    placeholder="Optional"
                    className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
                  />
                </label>
                {draft.yield_tracking_enabled && (
                  <>
                    <label className="space-y-1">
                      <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Input qty</span>
                      <input
                        data-testid="daily-log-input-qty"
                        disabled={busy}
                        value={logForm.input_quantity}
                        onChange={(e) => setLogForm((f) => ({ ...f, input_quantity: e.target.value }))}
                        className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
                      />
                    </label>
                    <div className="space-y-1">
                      <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Input unit</span>
                      <UnitField
                        testId="daily-log-input-unit"
                        value={logForm.input_unit || draft.input_unit}
                        onChange={(v) => setLogForm((f) => ({ ...f, input_unit: v }))}
                        commonUnits={commonUnits}
                        disabled={busy}
                      />
                    </div>
                  </>
                )}
                <div className="col-span-2 md:col-span-3">
                  <button
                    type="button"
                    disabled={busy}
                    data-testid="daily-log-save"
                    onClick={saveDailyLog}
                    className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
                  >
                    Save daily log
                  </button>
                </div>
              </div>
            )}

            {logsLoading ? (
              <p className="text-xs text-helm-muted">Loading logs…</p>
            ) : dailyLogs.length === 0 ? (
              <p className="text-xs text-helm-muted" data-testid="daily-logs-empty">No data logged yet for this work order.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs" data-testid="daily-logs-table">
                  <thead>
                    <tr className="text-[10px] font-mono uppercase tracking-wide text-helm-muted border-b border-helm-line">
                      <th className="py-1.5 pr-2 font-medium">Date</th>
                      <th className="py-1.5 pr-2 font-medium">Target</th>
                      <th className="py-1.5 pr-2 font-medium">Actual</th>
                      <th className="py-1.5 pr-2 font-medium">OT</th>
                      {draft.yield_tracking_enabled && <th className="py-1.5 pr-2 font-medium">Yield</th>}
                      <th className="py-1.5 pl-2 font-medium text-right w-10"><span className="sr-only">Delete</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyLogs.map((log) => (
                      <tr key={log.id || log.date} className="border-b border-helm-line/60">
                        <td className="py-1.5 pr-2 font-mono text-helm-muted">{log.date}</td>
                        <td className="py-1.5 pr-2 text-helm-fg">
                          {log.target_logged ? `${formatQty(log.target_quantity)} ${log.unit || ""}` : "—"}
                        </td>
                        <td className="py-1.5 pr-2 text-helm-fg">
                          {log.actual_logged ? `${formatQty(log.actual_quantity)} ${log.unit || ""}` : "—"}
                          {log.shortfall != null && log.shortfall > 0 ? (
                            <span className="text-helm-status-negative ml-1">(-{formatQty(log.shortfall)})</span>
                          ) : null}
                        </td>
                        <td className="py-1.5 pr-2 text-helm-muted">
                          {log.overtime_hours != null
                            ? `${formatQty(log.overtime_hours)}h${log.overtime_cost != null ? ` · $${log.overtime_cost}` : ""}`
                            : "—"}
                        </td>
                        {draft.yield_tracking_enabled && (
                          <td className="py-1.5 pr-2">
                            {log.actual_yield_pct != null ? (
                              <span className={log.yield_below_benchmark ? "text-helm-status-negative" : "text-helm-fg"}>
                                {log.actual_yield_pct}%
                                {log.yield_below_benchmark ? " below bench" : ""}
                              </span>
                            ) : log.yield_raw ? (
                              <span className="text-helm-muted">
                                {formatQty(log.yield_raw.output_quantity)} {log.yield_raw.output_unit || ""}
                                {" / "}
                                {formatQty(log.yield_raw.input_quantity)} {log.yield_raw.input_unit || ""}
                              </span>
                            ) : (
                              <span className="text-helm-muted">Not logged</span>
                            )}
                          </td>
                        )}
                        <td className="py-1.5 pl-2 text-right">
                          {log.id ? (
                            <CirDeleteBtn
                              disabled={busy}
                              data-testid={`delete-daily-log-${log.id}`}
                              onClick={() => setConfirmDeleteLogId(log.id)}
                              title="Delete daily log"
                              aria-label={`Delete daily log for ${log.date}`}
                            />
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="inline-flex items-center gap-2 text-sm text-helm-fg cursor-pointer">
              <input
                type="checkbox"
                data-testid="wo-blocked-toggle"
                checked={draft.blocked}
                disabled={busy}
                onChange={(e) => setDraft((d) => ({ ...d, blocked: e.target.checked }))}
              />
              Blocked
            </label>
            {draft.blocked && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Reason</span>
                  <select
                    data-testid="wo-blocked-category"
                    disabled={busy}
                    value={draft.blocked_category}
                    onChange={(e) => setDraft((d) => ({ ...d, blocked_category: e.target.value }))}
                    className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                  >
                    <option value="">Select…</option>
                    {blockedCategories.map((c) => (
                      <option key={c} value={c}>{CATEGORY_LABELS[c] || c}</option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Detail</span>
                  <input
                    data-testid="wo-blocked-detail"
                    disabled={busy}
                    value={draft.blocked_detail}
                    onChange={(e) => setDraft((d) => ({ ...d, blocked_detail: e.target.value }))}
                    className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                  />
                </label>
                {(draft.blocked_category === "machine" || draft.linked_maintenance_ticket_id) && (
                  <label className="space-y-1 md:col-span-2">
                    <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Linked maintenance ticket</span>
                    <select
                      data-testid="wo-linked-maintenance"
                      disabled={busy}
                      value={draft.linked_maintenance_ticket_id}
                      onChange={(e) => setDraft((d) => ({ ...d, linked_maintenance_ticket_id: e.target.value }))}
                      className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
                    >
                      <option value="">None</option>
                      {openMaintenance.map((t) => (
                        <option key={t.id} value={t.id}>
                          {(t.equipment_name || t.id)} · {MAINT_STATUS_LABELS[t.status] || t.status}
                        </option>
                      ))}
                      {draft.linked_maintenance_ticket_id
                        && !openMaintenance.some((t) => t.id === draft.linked_maintenance_ticket_id)
                        && selected.linked_maintenance && (
                          <option value={draft.linked_maintenance_ticket_id}>
                            {selected.linked_maintenance.equipment_name || draft.linked_maintenance_ticket_id}
                            {" · "}
                            {MAINT_STATUS_LABELS[selected.linked_maintenance.status] || selected.linked_maintenance.status}
                          </option>
                      )}
                    </select>
                  </label>
                )}
              </div>
            )}
          </div>

          <div>
            <SectionLabel className="mb-2">Assignees</SectionLabel>
            <div className="max-h-32 overflow-y-auto space-y-1.5 rounded-md border border-helm-line p-2">
              {workspaceMembers.length === 0 ? (
                <p className="text-xs text-helm-muted px-1">No workspace members to assign.</p>
              ) : workspaceMembers.map((m) => {
                const checked = draft.assigned_user_ids.includes(m.user_id);
                return (
                  <label key={m.user_id} className="flex items-center gap-2 text-sm text-helm-fg px-1 py-1 cursor-pointer hover:bg-helm-fg/[0.03] rounded">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleAssignee(m.user_id)}
                      data-testid={`wo-assign-${m.user_id}`}
                    />
                    <span className="truncate">{m.is_self || m.user_id === myId
                      ? `Me – ${m.name || m.email || "You"}`
                      : (m.name || m.email)}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted mr-1">Move to</span>
            {STATUS_ORDER.filter((s) => statuses.includes(s)).map((st) => (
              <button
                key={st}
                type="button"
                disabled={busy || draft.status === st}
                data-testid={`wo-status-${st}`}
                onClick={() => setStatus(st)}
                className={cn(
                  "rounded-md border text-xs px-2.5 py-1.5 disabled:opacity-40",
                  draft.status === st
                    ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
                    : "border-helm-line text-helm-fg hover:border-helm-gold/35",
                )}
              >
                {STATUS_META[st]?.label || st}
              </button>
            ))}
          </div>

          {completing && (
            <div className="rounded-md border border-helm-line bg-helm-fg/[0.02] p-3 space-y-2" data-testid="complete-prompt">
              <p className="text-sm text-helm-fg">Quantity produced</p>
              <input
                data-testid="complete-qty-input"
                value={completeQty}
                onChange={(e) => setCompleteQty(e.target.value)}
                className="w-full max-w-xs rounded-md border border-helm-line bg-helm-card px-3 py-2 text-sm text-helm-fg"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  data-testid="confirm-complete-btn"
                  onClick={confirmComplete}
                  className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
                >
                  Complete
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setCompleting(false)}
                  className="rounded-md border border-helm-line text-sm px-3 py-2 text-helm-fg"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              data-testid="save-work-order-btn"
              onClick={() => saveOrder()}
              className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
            >
              Save changes
            </button>
            <StatusBadge status={selected.status} />
            <CirDeleteBtn
              disabled={busy}
              data-testid="delete-work-order-btn"
              onClick={() => setConfirmDelete(true)}
              size="md"
              title="Delete work order"
              className="ml-auto"
            />
          </div>
        </GlassCard>
      )}

      <ConfirmDialog
        open={confirmDelete && Boolean(selected)}
        title={`Delete work order “${selected?.reference || ""}”?`}
        description="This permanently removes the work order from the queue. This can’t be undone."
        confirmLabel="Delete work order"
        busy={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={deleteOrder}
        testId="delete-work-order-confirm"
      />

      <ConfirmDialog
        open={Boolean(confirmDeleteLogId)}
        title="Delete daily log?"
        description="This removes the logged target, actual, overtime, and yield for that day."
        confirmLabel="Delete daily log"
        busy={busy}
        onCancel={() => setConfirmDeleteLogId(null)}
        onConfirm={deleteDailyLog}
        testId="delete-daily-log-confirm"
      />

      {adding && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setAdding(false)} />
          <GlassCard className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="add-work-order-form">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg text-helm-fg font-light">New work order</h3>
              <button type="button" onClick={() => setAdding(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <label className="block text-xs text-helm-muted">Reference
                <input
                  data-testid="new-wo-reference"
                  value={form.reference}
                  onChange={(e) => setForm((o) => ({ ...o, reference: e.target.value }))}
                  placeholder="Order #245"
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-helm-muted">What&apos;s being produced
                  <input
                    data-testid="new-wo-product"
                    value={form.product}
                    onChange={(e) => setForm((o) => ({ ...o, product: e.target.value }))}
                    placeholder="Product / SKU / batch"
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                  />
                </label>
                <label className="block text-xs text-helm-muted">Order qty planned
                  <input
                    data-testid="new-wo-qty-planned"
                    type="number"
                    value={form.quantity_planned}
                    onChange={(e) => setForm((o) => ({ ...o, quantity_planned: e.target.value }))}
                    placeholder="Total for this order"
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                  />
                </label>
              </div>
              <div className="block text-xs text-helm-muted">Unit
                <div className="mt-1">
                  <UnitField
                    testId="new-wo-unit"
                    value={form.unit}
                    onChange={(v) => setForm((o) => ({ ...o, unit: v }))}
                    commonUnits={commonUnits}
                    required
                  />
                </div>
              </div>
              <label className="block text-xs text-helm-muted">Customer
                <input
                  data-testid="new-wo-customer"
                  value={form.customer}
                  onChange={(e) => setForm((o) => ({ ...o, customer: e.target.value }))}
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                />
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-helm-fg cursor-pointer">
                <input
                  type="checkbox"
                  data-testid="new-wo-yield-toggle"
                  checked={form.yield_tracking_enabled}
                  onChange={(e) => setForm((o) => ({ ...o, yield_tracking_enabled: e.target.checked }))}
                />
                Track yield for this work order
              </label>
              {form.yield_tracking_enabled && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="block text-xs text-helm-muted">Input unit
                    <div className="mt-1">
                      <UnitField
                        testId="new-wo-input-unit"
                        value={form.input_unit}
                        onChange={(v) => setForm((o) => ({ ...o, input_unit: v }))}
                        commonUnits={commonUnits}
                      />
                    </div>
                  </div>
                  <label className="block text-xs text-helm-muted">Expected yield %
                    <input
                      data-testid="new-wo-expected-yield"
                      value={form.expected_yield_pct}
                      onChange={(e) => setForm((o) => ({ ...o, expected_yield_pct: e.target.value }))}
                      className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                    />
                  </label>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-helm-muted">Priority
                  <select
                    data-testid="new-wo-priority"
                    value={form.priority}
                    onChange={(e) => setForm((o) => ({ ...o, priority: e.target.value }))}
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                  >
                    {priorities.map((p) => (
                      <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs text-helm-muted">Due date
                  <input
                    data-testid="new-wo-due-date"
                    type="date"
                    value={form.due_date}
                    onChange={(e) => setForm((o) => ({ ...o, due_date: e.target.value }))}
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                  />
                </label>
              </div>
              <label className="block text-xs text-helm-muted">Link open procurement (optional)
                <select
                  data-testid="new-wo-linked-procurement"
                  value={form.linked_procurement_request_id}
                  onChange={(e) => setForm((o) => ({ ...o, linked_procurement_request_id: e.target.value }))}
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                >
                  <option value="">None</option>
                  {openProcurement.map((r) => (
                    <option key={r.id} value={r.id}>
                      {(r.item || r.id)} · {PROC_STATUS_LABELS[r.status] || r.status}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <button
              type="button"
              data-testid="submit-new-work-order"
              disabled={busy}
              onClick={createOrder}
              className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm hover:bg-helm-gold-hover disabled:opacity-60"
            >
              {busy ? "Creating…" : "Create work order"}
            </button>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
