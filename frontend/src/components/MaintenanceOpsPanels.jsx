import { useState } from "react";
import { toast } from "sonner";
import { Plus, X } from "lucide-react";
import { useFetch } from "@/hooks/useFetch";
import { api, apiErrorMessage } from "@/lib/api";
import { GlassCard, SectionLabel, EmptyState } from "@/components/kit";
import { cn } from "@/lib/utils";

const money = (n) => `$${(Number(n) || 0).toLocaleString()}`;

/** equipment_names may be missing/legacy — never call .filter on a non-array. */
function spareEquipmentLabel(s) {
  const names = Array.isArray(s?.equipment_names)
    ? s.equipment_names
    : (s?.equipment_name ? [s.equipment_name] : []);
  const label = names.map((n) => String(n || "").trim()).filter(Boolean).join(", ");
  return label || "—";
}

/** Spares / Schedule / Contracts / Overhead panels for Maintenance. */
export default function MaintenanceOpsPanels({ ticketData, onTicketsReload }) {
  const [tab, setTab] = useState("spares");
  const sparesQ = useFetch("/maintenance/spares");
  const schedQ = useFetch("/maintenance/schedules");
  const contractsQ = useFetch("/maintenance/contracts");
  const settingsQ = useFetch("/maintenance/settings");
  const [busy, setBusy] = useState(false);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [spareForm, setSpareForm] = useState({ part_name: "", equipment_name: "", quantity_on_hand: "", minimum_threshold: "", unit: "pcs" });
  const [schedForm, setSchedForm] = useState({ equipment_name: "", task: "", frequency_days: "30" });
  const [contractForm, setContractForm] = useState({
    equipment_name: "", vendor_name: "", coverage_start: "", coverage_end: "", cost: "", scope_notes: "",
  });
  const [costForm, setCostForm] = useState({ amount: "", description: "" });
  const [showSpare, setShowSpare] = useState(false);
  const [showSched, setShowSched] = useState(false);
  const [showContract, setShowContract] = useState(false);

  const overhead = ticketData?.overhead || settingsQ.data?.overhead;
  const canManage = Boolean(
    ticketData?.is_lead || ticketData?.is_ceo || settingsQ.data?.can_manage
    || sparesQ.data?.is_lead || sparesQ.data?.is_ceo,
  );

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
      await Promise.all([settingsQ.reload?.(), onTicketsReload?.()]);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save budget"));
    } finally {
      setBusy(false);
    }
  };

  const createSpare = async () => {
    if (!spareForm.part_name.trim()) {
      toast.error("Part name required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/maintenance/spares", {
        part_name: spareForm.part_name.trim(),
        equipment_name: spareForm.equipment_name.trim(),
        quantity_on_hand: Number(spareForm.quantity_on_hand) || 0,
        minimum_threshold: Number(spareForm.minimum_threshold) || 0,
        unit: spareForm.unit.trim() || "pcs",
      });
      toast.success("Spare added");
      setShowSpare(false);
      setSpareForm({ part_name: "", equipment_name: "", quantity_on_hand: "", minimum_threshold: "", unit: "pcs" });
      await sparesQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not add spare"));
    } finally {
      setBusy(false);
    }
  };

  const createSchedule = async () => {
    if (!schedForm.equipment_name.trim() || !schedForm.task.trim()) {
      toast.error("Equipment and task required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/maintenance/schedules", {
        equipment_name: schedForm.equipment_name.trim(),
        task: schedForm.task.trim(),
        frequency_days: Number(schedForm.frequency_days) || 30,
      });
      toast.success("Schedule added");
      setShowSched(false);
      await schedQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not add schedule"));
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

  const createContract = async () => {
    if (!contractForm.equipment_name.trim() || !contractForm.vendor_name.trim()) {
      toast.error("Equipment and vendor required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/maintenance/contracts", {
        equipment_name: contractForm.equipment_name.trim(),
        vendor_name: contractForm.vendor_name.trim(),
        coverage_start: contractForm.coverage_start,
        coverage_end: contractForm.coverage_end,
        cost: contractForm.cost === "" ? null : Number(contractForm.cost),
        scope_notes: contractForm.scope_notes.trim(),
      });
      toast.success("Contract added");
      setShowContract(false);
      await contractsQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not add contract"));
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
      await settingsQ.reload();
      await onTicketsReload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not log cost"));
    } finally {
      setBusy(false);
    }
  };

  const tabs = [
    { id: "spares", label: `Spares${ticketData?.spares_below_threshold_count ? ` (${ticketData.spares_below_threshold_count})` : ""}` },
    { id: "schedule", label: `Schedule${ticketData?.overdue_schedules_count ? ` (${ticketData.overdue_schedules_count})` : ""}` },
    { id: "contracts", label: `AMCs${ticketData?.contracts_needing_renewal_count ? ` (${ticketData.contracts_needing_renewal_count})` : ""}` },
    { id: "overhead", label: "Overhead" },
  ];

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
            <button type="button" onClick={() => setShowSpare(true)} className="inline-flex items-center gap-1 text-sm text-helm-gold">
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
            <button type="button" onClick={() => setShowSched(true)} className="inline-flex items-center gap-1 text-sm text-helm-gold">
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
                          <button type="button" disabled={busy} onClick={() => markDone(s.id)} className="text-xs text-helm-gold">
                            Mark done
                          </button>
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
            <button type="button" onClick={() => setShowContract(true)} className="inline-flex items-center gap-1 text-sm text-helm-gold">
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
        </div>
      )}

      {showSpare && (
        <Modal title="Add spare" onClose={() => setShowSpare(false)}>
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
          <button type="button" disabled={busy} onClick={createSpare} className="w-full rounded-md bg-helm-gold text-helm-navy text-sm py-2 font-medium">Save</button>
        </Modal>
      )}
      {showSched && (
        <Modal title="Add schedule" onClose={() => setShowSched(false)}>
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
          <button type="button" disabled={busy} onClick={createSchedule} className="w-full rounded-md bg-helm-gold text-helm-navy text-sm py-2 font-medium">Save</button>
        </Modal>
      )}
      {showContract && (
        <Modal title="Add AMC" onClose={() => setShowContract(false)}>
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
          <button type="button" disabled={busy} onClick={createContract} className="w-full rounded-md bg-helm-gold text-helm-navy text-sm py-2 font-medium">Save</button>
        </Modal>
      )}
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
