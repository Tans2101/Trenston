import { useState } from "react";
import { toast } from "sonner";
import { Plus, X, PenLine } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch } from "@/hooks/useFetch";
import { api, apiErrorMessage } from "@/lib/api";
import { GlassCard, SectionLabel, EmptyState, ConfirmDialog } from "@/components/kit";
import { cn } from "@/lib/utils";
import { useWorkspaceCurrency } from "@/hooks/useWorkspaceCurrency";
import { formatMoney } from "@/lib/money";


/** equipment_names may be missing/legacy — never call .filter on a non-array. */
function spareEquipmentLabel(s) {
  const names = Array.isArray(s?.equipment_names)
    ? s.equipment_names
    : (s?.equipment_name ? [s.equipment_name] : []);
  const label = names.map((n) => String(n || "").trim()).filter(Boolean).join(", ");
  return label || "—";
}

const emptySpare = { part_name: "", equipment_name: "", quantity_on_hand: "", minimum_threshold: "", unit: "pcs" };
const emptySched = { equipment_name: "", task: "", frequency_days: "30" };
const emptyContract = {
  equipment_name: "", vendor_name: "", coverage_start: "", coverage_end: "", cost: "", scope_notes: "",
};

/** Spares / Schedule / Contracts / Overhead panels for Maintenance. */
export default function MaintenanceOpsPanels({ ticketData, onTicketsReload }) {
  const [tab, setTab] = useState("spares");
  const sparesQ = useFetch("/maintenance/spares");
  const schedQ = useFetch("/maintenance/schedules");
  const contractsQ = useFetch("/maintenance/contracts");
  const costsQ = useFetch("/maintenance/costs");
  const settingsQ = useFetch("/maintenance/settings");
  const [busy, setBusy] = useState(false);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [spareForm, setSpareForm] = useState(emptySpare);
  const [schedForm, setSchedForm] = useState(emptySched);
  const [contractForm, setContractForm] = useState(emptyContract);
  const [costForm, setCostForm] = useState({ amount: "", description: "" });
  const [showSpare, setShowSpare] = useState(false);
  const [showSched, setShowSched] = useState(false);
  const [showContract, setShowContract] = useState(false);
  const [editingSpareId, setEditingSpareId] = useState(null);
  const [editingSchedId, setEditingSchedId] = useState(null);
  const [editingContractId, setEditingContractId] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);

  const overhead = ticketData?.overhead || costsQ.data?.overhead || settingsQ.data?.overhead;
  const { symbol: workspaceSymbol } = useWorkspaceCurrency();
  const symbol = ticketData?.currency_symbol || costsQ.data?.currency_symbol || workspaceSymbol;
  const money = (n) => formatMoney(n, symbol);
  const canManage = Boolean(
    ticketData?.is_lead || ticketData?.is_ceo || settingsQ.data?.can_manage
    || sparesQ.data?.is_lead || sparesQ.data?.is_ceo,
  );

  const refreshOverhead = async () => {
    await Promise.all([
      costsQ.reload?.(),
      settingsQ.reload?.(),
      onTicketsReload?.(),
    ]);
  };

  const saveBudget = async () => {
    const t = Number(budgetDraft);
    if (!Number.isFinite(t) || t < 0) {
      toast.error("Enter a non-negative budget");
      return;
    }
    setBusy(true);
    try {
      await api.put("/maintenance/settings", { monthly_budget: t });
      toast.success("Budget saved");
      await refreshOverhead();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save budget"));
    } finally {
      setBusy(false);
    }
  };

  const openAddSpare = () => {
    setEditingSpareId(null);
    setSpareForm(emptySpare);
    setShowSpare(true);
  };

  const openEditSpare = (s) => {
    setEditingSpareId(s.id);
    setSpareForm({
      part_name: s.part_name || "",
      equipment_name: spareEquipmentLabel(s) === "—" ? "" : spareEquipmentLabel(s),
      quantity_on_hand: String(s.quantity_on_hand ?? ""),
      minimum_threshold: String(s.minimum_threshold ?? ""),
      unit: s.unit || "pcs",
    });
    setShowSpare(true);
  };

  const saveSpare = async () => {
    if (!spareForm.part_name.trim()) {
      toast.error("Part name required");
      return;
    }
    setBusy(true);
    try {
      const body = {
        part_name: spareForm.part_name.trim(),
        equipment_name: spareForm.equipment_name.trim(),
        quantity_on_hand: Number(spareForm.quantity_on_hand) || 0,
        minimum_threshold: Number(spareForm.minimum_threshold) || 0,
        unit: spareForm.unit.trim() || "pcs",
      };
      if (editingSpareId) {
        await api.patch(`/maintenance/spares/${editingSpareId}`, body);
        toast.success("Spare updated");
      } else {
        await api.post("/maintenance/spares", body);
        toast.success("Spare added");
      }
      setShowSpare(false);
      setEditingSpareId(null);
      setSpareForm(emptySpare);
      await sparesQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, editingSpareId ? "Could not update spare" : "Could not add spare"));
    } finally {
      setBusy(false);
    }
  };

  const openAddSched = () => {
    setEditingSchedId(null);
    setSchedForm(emptySched);
    setShowSched(true);
  };

  const openEditSched = (s) => {
    setEditingSchedId(s.id);
    setSchedForm({
      equipment_name: s.equipment_name || "",
      task: s.task || "",
      frequency_days: String(s.frequency_days ?? "30"),
    });
    setShowSched(true);
  };

  const saveSchedule = async () => {
    if (!schedForm.equipment_name.trim() || !schedForm.task.trim()) {
      toast.error("Equipment and task required");
      return;
    }
    setBusy(true);
    try {
      const body = {
        equipment_name: schedForm.equipment_name.trim(),
        task: schedForm.task.trim(),
        frequency_days: Number(schedForm.frequency_days) || 30,
      };
      if (editingSchedId) {
        await api.patch(`/maintenance/schedules/${editingSchedId}`, body);
        toast.success("Schedule updated");
      } else {
        await api.post("/maintenance/schedules", body);
        toast.success("Schedule added");
      }
      setShowSched(false);
      setEditingSchedId(null);
      setSchedForm(emptySched);
      await schedQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, editingSchedId ? "Could not update schedule" : "Could not add schedule"));
    } finally {
      setBusy(false);
    }
  };

  const markDone = async (id) => {
    setBusy(true);
    try {
      await api.patch(`/maintenance/schedules/${id}`, { mark_done: true });
      toast.success("Marked done");
      await schedQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not update"));
    } finally {
      setBusy(false);
    }
  };

  const openAddContract = () => {
    setEditingContractId(null);
    setContractForm(emptyContract);
    setShowContract(true);
  };

  const openEditContract = (c) => {
    setEditingContractId(c.id);
    setContractForm({
      equipment_name: c.equipment_name || "",
      vendor_name: c.vendor_name || "",
      coverage_start: (c.coverage_start || "").slice(0, 10),
      coverage_end: (c.coverage_end || "").slice(0, 10),
      cost: c.cost == null ? "" : String(c.cost),
      scope_notes: c.scope_notes || "",
    });
    setShowContract(true);
  };

  const saveContract = async () => {
    if (!contractForm.equipment_name.trim() || !contractForm.vendor_name.trim()) {
      toast.error("Equipment and vendor required");
      return;
    }
    setBusy(true);
    try {
      const body = {
        equipment_name: contractForm.equipment_name.trim(),
        vendor_name: contractForm.vendor_name.trim(),
        coverage_start: contractForm.coverage_start,
        coverage_end: contractForm.coverage_end,
        cost: contractForm.cost === "" ? null : Number(contractForm.cost),
        scope_notes: contractForm.scope_notes.trim(),
      };
      if (editingContractId) {
        await api.patch(`/maintenance/contracts/${editingContractId}`, body);
        toast.success("Contract updated");
      } else {
        await api.post("/maintenance/contracts", body);
        toast.success("Contract added");
      }
      setShowContract(false);
      setEditingContractId(null);
      setContractForm(emptyContract);
      await contractsQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, editingContractId ? "Could not update contract" : "Could not add contract"));
    } finally {
      setBusy(false);
    }
  };

  const addCost = async () => {
    const amount = Number(costForm.amount);
    if (!Number.isFinite(amount) || amount < 0) {
      toast.error("Enter a valid amount");
      return;
    }
    setBusy(true);
    try {
      await api.post("/maintenance/costs", {
        amount,
        description: costForm.description.trim(),
      });
      toast.success("Cost logged");
      setCostForm({ amount: "", description: "" });
      await refreshOverhead();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not log cost"));
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const { kind, id } = pendingDelete;
    setBusy(true);
    try {
      if (kind === "spare") {
        await api.delete(`/maintenance/spares/${id}`);
        toast.success("Spare deleted");
        await sparesQ.reload();
        await onTicketsReload?.();
      } else if (kind === "schedule") {
        await api.delete(`/maintenance/schedules/${id}`);
        toast.success("Schedule deleted");
        await schedQ.reload();
        await onTicketsReload?.();
      } else if (kind === "contract") {
        await api.delete(`/maintenance/contracts/${id}`);
        toast.success("Contract deleted");
        await contractsQ.reload();
        await onTicketsReload?.();
      } else if (kind === "cost") {
        await api.delete(`/maintenance/costs/${id}`);
        toast.success("Cost entry deleted");
        await refreshOverhead();
      }
      setPendingDelete(null);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not delete"));
    } finally {
      setBusy(false);
    }
  };

  const deleteCopy = (() => {
    if (!pendingDelete) return { title: "", description: "", confirmLabel: "Delete" };
    const labels = {
      spare: { title: "Delete this spare?", description: "Removes the spare part from inventory tracking. This can’t be undone.", confirmLabel: "Delete spare" },
      schedule: { title: "Delete this schedule?", description: "Removes the preventive maintenance schedule. This can’t be undone.", confirmLabel: "Delete schedule" },
      contract: { title: "Delete this AMC?", description: "Removes the annual maintenance contract. This can’t be undone.", confirmLabel: "Delete contract" },
      cost: { title: "Delete this cost entry?", description: "Removes the logged cost from this month’s ledger. Overhead totals update automatically.", confirmLabel: "Delete cost" },
    };
    return labels[pendingDelete.kind] || { title: "Delete?", description: "This can’t be undone.", confirmLabel: "Delete" };
  })();

  const tabs = [
    { id: "spares", label: `Spares${ticketData?.spares_below_threshold_count ? ` (${ticketData.spares_below_threshold_count})` : ""}` },
    { id: "schedule", label: `Schedule${ticketData?.overdue_schedules_count ? ` (${ticketData.overdue_schedules_count})` : ""}` },
    { id: "contracts", label: `AMCs${ticketData?.contracts_needing_renewal_count ? ` (${ticketData.contracts_needing_renewal_count})` : ""}` },
    { id: "overhead", label: "Overhead" },
  ];

  const costs = costsQ.data?.costs || [];

  return (
    <div className="mt-6 space-y-4" data-testid="maintenance-ops-panels">
      {overhead && (
        <div
          className={cn(
            "rounded-md border px-3 py-2.5",
            overhead.budget_entered && (overhead.gap || 0) > 0
              ? "border-helm-status-negative/35 bg-helm-status-negative/8"
              : "border-helm-line bg-helm-card/40",
          )}
          data-testid="maintenance-overhead-card"
        >
          <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">
            Overhead this month{overhead.period_label ? ` · ${overhead.period_label}` : ""}
          </p>
          {overhead.budget_entered ? (
            <p className={cn("font-mono text-xl mt-1", (overhead.gap || 0) > 0 ? "text-helm-status-negative" : "text-helm-fg")}>
              {money(overhead.actual)} actual vs {money(overhead.budget)} budget
              {(overhead.gap || 0) > 0 ? ` · overrun ${money(overhead.gap)}` : ""}
            </p>
          ) : (
            <p className="font-mono text-xl text-helm-fg mt-1">
              {money(overhead.actual)}
              <span className="text-sm text-helm-muted ml-2">no budget set</span>
            </p>
          )}
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-helm-line" data-testid="maintenance-ops-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              "px-3 py-2 text-sm border-b-2 -mb-px",
              tab === t.id ? "border-helm-gold text-helm-fg" : "border-transparent text-helm-muted",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "spares" && (
        <div className="space-y-3">
          {canManage && (
            <button type="button" onClick={openAddSpare} className="inline-flex items-center gap-1 text-sm text-helm-gold">
              <Plus className="w-4 h-4" /> Add spare
            </button>
          )}
          {(sparesQ.data?.spares || []).length === 0 ? (
            <EmptyState title="No spares tracked" body="Add critical spare parts and minimum thresholds." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase text-helm-muted">
                    <th className="px-3 py-2">Part</th>
                    <th className="px-3 py-2">Equipment</th>
                    <th className="px-3 py-2">On hand</th>
                    <th className="px-3 py-2">Min</th>
                    <th className="px-3 py-2">Unit</th>
                    {canManage && <th className="px-3 py-2" />}
                  </tr>
                </thead>
                <tbody>
                  {(sparesQ.data?.spares || []).map((s) => (
                    <tr key={s.id} className={cn("border-b border-helm-line", s.is_below_threshold && "bg-helm-status-negative/8")}>
                      <td className="px-3 py-2 text-helm-fg">{s.part_name}</td>
                      <td className="px-3 py-2 text-helm-muted">{spareEquipmentLabel(s)}</td>
                      <td className={cn("px-3 py-2 font-mono", s.is_below_threshold && "text-helm-status-negative")}>{s.quantity_on_hand}</td>
                      <td className="px-3 py-2 font-mono text-helm-muted">{s.minimum_threshold}</td>
                      <td className="px-3 py-2 text-helm-muted">{s.unit}</td>
                      {canManage && (
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1 justify-end">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => openEditSpare(s)}
                              data-testid={`edit-spare-${s.id}`}
                              className="text-helm-muted hover:text-helm-gold p-1"
                              aria-label="Edit spare"
                            >
                              <PenLine className="w-3.5 h-3.5" />
                            </button>
                            <CirDeleteBtn
                              disabled={busy}
                              onClick={() => setPendingDelete({ kind: "spare", id: s.id })}
                              data-testid={`delete-spare-${s.id}`}
                              title="Delete spare"
                            />
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "schedule" && (
        <div className="space-y-3">
          {canManage && (
            <button type="button" onClick={openAddSched} className="inline-flex items-center gap-1 text-sm text-helm-gold">
              <Plus className="w-4 h-4" /> Add schedule
            </button>
          )}
          {(schedQ.data?.schedules || []).length === 0 ? (
            <EmptyState title="No schedules" body="Add per-machine tasks and frequency. Resolving a matching ticket auto-updates last done." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase text-helm-muted">
                    <th className="px-3 py-2">Equipment</th>
                    <th className="px-3 py-2">Task</th>
                    <th className="px-3 py-2">Every</th>
                    <th className="px-3 py-2">Next due</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {(schedQ.data?.schedules || []).map((s) => (
                    <tr key={s.id} className={cn("border-b border-helm-line", s.is_overdue && "bg-helm-status-negative/8")}>
                      <td className="px-3 py-2 text-helm-fg">{s.equipment_name}</td>
                      <td className="px-3 py-2 text-helm-muted">{s.task}</td>
                      <td className="px-3 py-2 font-mono text-xs">{s.frequency_days}d</td>
                      <td className={cn("px-3 py-2 font-mono text-xs", s.is_overdue ? "text-helm-status-negative" : "text-helm-muted")}>
                        {s.next_due_at ? String(s.next_due_at).slice(0, 10) : "Not yet established"}
                      </td>
                      <td className="px-3 py-2">
                        {canManage && (
                          <div className="flex items-center gap-2 justify-end">
                            <button type="button" disabled={busy} onClick={() => markDone(s.id)} className="text-xs text-helm-gold">
                              Mark done
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => openEditSched(s)}
                              data-testid={`edit-schedule-${s.id}`}
                              className="text-helm-muted hover:text-helm-gold p-1"
                              aria-label="Edit schedule"
                            >
                              <PenLine className="w-3.5 h-3.5" />
                            </button>
                            <CirDeleteBtn
                              disabled={busy}
                              onClick={() => setPendingDelete({ kind: "schedule", id: s.id })}
                              data-testid={`delete-schedule-${s.id}`}
                              title="Delete schedule"
                            />
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "contracts" && (
        <div className="space-y-3">
          {canManage && (
            <button type="button" onClick={openAddContract} className="inline-flex items-center gap-1 text-sm text-helm-gold">
              <Plus className="w-4 h-4" /> Add AMC
            </button>
          )}
          {(contractsQ.data?.contracts || []).length === 0 ? (
            <EmptyState title="No AMCs" body="Track annual maintenance contracts and renewal dates." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase text-helm-muted">
                    <th className="px-3 py-2">Equipment</th>
                    <th className="px-3 py-2">Vendor</th>
                    <th className="px-3 py-2">Coverage</th>
                    <th className="px-3 py-2">Renewal</th>
                    <th className="px-3 py-2">Status</th>
                    {canManage && <th className="px-3 py-2" />}
                  </tr>
                </thead>
                <tbody>
                  {(contractsQ.data?.contracts || []).map((c) => (
                    <tr key={c.id} className={cn("border-b border-helm-line", (c.expired || c.renewal_due_soon) && "bg-helm-status-warning/10")}>
                      <td className="px-3 py-2 text-helm-fg">{c.equipment_name}</td>
                      <td className="px-3 py-2 text-helm-muted">{c.vendor_name}</td>
                      <td className="px-3 py-2 font-mono text-xs text-helm-muted">{c.coverage_start} → {c.coverage_end}</td>
                      <td className="px-3 py-2 font-mono text-xs">{c.renewal_effective || "—"}</td>
                      <td className="px-3 py-2 text-xs">
                        {c.expired ? <span className="text-helm-status-negative">Expired</span>
                          : c.renewal_due_soon ? <span className="text-helm-status-warning">Due soon</span>
                            : <span className="text-helm-muted">OK</span>}
                      </td>
                      {canManage && (
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1 justify-end">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => openEditContract(c)}
                              data-testid={`edit-contract-${c.id}`}
                              className="text-helm-muted hover:text-helm-gold p-1"
                              aria-label="Edit contract"
                            >
                              <PenLine className="w-3.5 h-3.5" />
                            </button>
                            <CirDeleteBtn
                              disabled={busy}
                              onClick={() => setPendingDelete({ kind: "contract", id: c.id })}
                              data-testid={`delete-contract-${c.id}`}
                              title="Delete contract"
                            />
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "overhead" && (
        <div className="space-y-3">
          {canManage && (
            <>
              <div className="flex flex-wrap gap-2 items-end">
                <label className="text-xs text-helm-muted">
                  Monthly budget
                  <input
                    data-testid="maint-budget-input"
                    value={budgetDraft}
                    onChange={(e) => setBudgetDraft(e.target.value)}
                    placeholder={overhead?.budget_entered ? String(overhead.budget) : "e.g. 100000"}
                    className="mt-1 block w-40 rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg font-mono"
                  />
                </label>
                <button type="button" disabled={busy} onClick={saveBudget} className="rounded-md border border-helm-line text-xs px-3 py-2 text-helm-fg">
                  Save budget
                </button>
              </div>
              <div className="flex flex-wrap gap-2 items-end">
                <label className="text-xs text-helm-muted">
                  Log non-ticket cost
                  <input
                    value={costForm.amount}
                    onChange={(e) => setCostForm((f) => ({ ...f, amount: e.target.value }))}
                    placeholder="Amount"
                    className="mt-1 block w-32 rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg font-mono"
                  />
                </label>
                <input
                  value={costForm.description}
                  onChange={(e) => setCostForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder="Description"
                  className="rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
                />
                <button type="button" disabled={busy} onClick={addCost} className="rounded-md bg-helm-gold text-helm-navy text-xs px-3 py-2 font-medium">
                  Log cost
                </button>
              </div>
              <p className="text-[11px] text-helm-muted">Ticket repair costs are summed from the optional cost field when a ticket is resolved.</p>
            </>
          )}

          {costs.length === 0 ? (
            <EmptyState title="No costs logged this month" body="Non-ticket costs appear here once logged." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line" data-testid="maintenance-costs-table">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase text-helm-muted">
                    <th className="px-3 py-2">Date</th>
                    <th className="px-3 py-2">Description</th>
                    <th className="px-3 py-2">Category</th>
                    <th className="px-3 py-2">Amount</th>
                    <th className="px-3 py-2">Logged by</th>
                    {canManage && <th className="px-3 py-2" />}
                  </tr>
                </thead>
                <tbody>
                  {costs.map((c) => (
                    <tr key={c.id} className="border-b border-helm-line">
                      <td className="px-3 py-2 font-mono text-xs text-helm-muted">
                        {c.created_at ? String(c.created_at).slice(0, 10) : "—"}
                      </td>
                      <td className="px-3 py-2 text-helm-fg">{c.description || "—"}</td>
                      <td className="px-3 py-2 text-helm-muted text-xs">{c.category || "general"}</td>
                      <td className="px-3 py-2 font-mono text-helm-fg">{money(c.amount)}</td>
                      <td className="px-3 py-2 font-mono text-xs text-helm-muted truncate max-w-[10rem]" title={c.created_by || ""}>
                        {c.created_by || "—"}
                      </td>
                      {canManage && (
                        <td className="px-3 py-2">
                          <div className="flex justify-end">
                            <CirDeleteBtn
                              disabled={busy}
                              onClick={() => setPendingDelete({ kind: "cost", id: c.id })}
                              data-testid={`delete-cost-${c.id}`}
                              title="Delete cost"
                            />
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {showSpare && (
        <Modal title={editingSpareId ? "Edit spare" : "Add spare"} onClose={() => { setShowSpare(false); setEditingSpareId(null); }}>
          {["part_name", "equipment_name", "quantity_on_hand", "minimum_threshold", "unit"].map((k) => (
            <label key={k} className="block text-xs text-helm-muted mb-2 capitalize">
              {k.replace(/_/g, " ")}
              <input
                value={spareForm[k]}
                onChange={(e) => setSpareForm((f) => ({ ...f, [k]: e.target.value }))}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
              />
            </label>
          ))}
          <button type="button" disabled={busy} onClick={saveSpare} className="w-full rounded-md bg-helm-gold text-helm-navy text-sm py-2 font-medium">
            {editingSpareId ? "Save changes" : "Save"}
          </button>
        </Modal>
      )}
      {showSched && (
        <Modal title={editingSchedId ? "Edit schedule" : "Add schedule"} onClose={() => { setShowSched(false); setEditingSchedId(null); }}>
          {["equipment_name", "task", "frequency_days"].map((k) => (
            <label key={k} className="block text-xs text-helm-muted mb-2 capitalize">
              {k.replace(/_/g, " ")}
              <input
                value={schedForm[k]}
                onChange={(e) => setSchedForm((f) => ({ ...f, [k]: e.target.value }))}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
              />
            </label>
          ))}
          <button type="button" disabled={busy} onClick={saveSchedule} className="w-full rounded-md bg-helm-gold text-helm-navy text-sm py-2 font-medium">
            {editingSchedId ? "Save changes" : "Save"}
          </button>
        </Modal>
      )}
      {showContract && (
        <Modal title={editingContractId ? "Edit AMC" : "Add AMC"} onClose={() => { setShowContract(false); setEditingContractId(null); }}>
          {["equipment_name", "vendor_name", "coverage_start", "coverage_end", "cost", "scope_notes"].map((k) => (
            <label key={k} className="block text-xs text-helm-muted mb-2 capitalize">
              {k.replace(/_/g, " ")}
              <input
                type={k.includes("coverage") ? "date" : "text"}
                value={contractForm[k]}
                onChange={(e) => setContractForm((f) => ({ ...f, [k]: e.target.value }))}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg"
              />
            </label>
          ))}
          <button type="button" disabled={busy} onClick={saveContract} className="w-full rounded-md bg-helm-gold text-helm-navy text-sm py-2 font-medium">
            {editingContractId ? "Save changes" : "Save"}
          </button>
        </Modal>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={deleteCopy.title}
        description={deleteCopy.description}
        confirmLabel={deleteCopy.confirmLabel}
        busy={busy}
        onCancel={() => !busy && setPendingDelete(null)}
        onConfirm={confirmDelete}
        testId="maintenance-ops-delete-confirm"
      />
    </div>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-helm-ink/70" onClick={onClose} />
      <GlassCard className="relative w-full max-w-md p-5 space-y-2">
        <div className="flex justify-between items-center mb-2">
          <SectionLabel>{title}</SectionLabel>
          <button type="button" onClick={onClose} className="text-helm-muted"><X className="w-4 h-4" /></button>
        </div>
        {children}
      </GlassCard>
    </div>
  );
}
