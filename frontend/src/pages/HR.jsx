import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, X, Users, ChevronUp, ChevronDown } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useSearchParams } from "react-router-dom";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import {
  PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, ConfirmDialog,
  SkeletonKPIRow, SkeletonCardList,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { PossiblyStaleBadge } from "@/components/AiSummaryMeta";

const STEP_STATUS_META = {
  not_started: { label: "Not started", className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35" },
  in_progress: { label: "In progress", className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35" },
  done: { label: "Done", className: "bg-helm-status-positive/12 text-helm-fg border-helm-status-positive/35" },
};

const EMPLOYEE_STATUS_META = {
  active: { label: "Active", className: "text-helm-status-positive" },
  on_leave: { label: "On leave", className: "text-helm-muted" },
  departed: { label: "Departed", className: "text-helm-status-negative" },
};

function StepBadge({ status }) {
  const meta = STEP_STATUS_META[status] || STEP_STATUS_META.not_started;
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide border", meta.className)}>
      {meta.label}
    </span>
  );
}

function personLabel(p) {
  if (!p) return "Unassigned";
  return p.name || p.email || "Teammate";
}

export default function HR() {
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState("onboarding");
  const { data, loading, error, reload } = useFetch("/hr/onboarding");
  const { data: tmplData, reload: reloadTmpl } = useFetch("/hr/template");
  const { data: empData, reload: reloadEmp } = useFetch("/hr/employees");
  const { data: offData, reload: reloadOff } = useFetch("/hr/offboarding");
  const { data: offTmplData, reload: reloadOffTmpl } = useFetch("/hr/offboarding/template");
  const { data: leaveData, reload: reloadLeave } = useFetch("/hr/leave-requests");
  const { data: summaryData, reload: reloadSummary } = useFetch("/hr/summary");
  const { data: membersData } = useFetch("/members");
  const [showActive, setShowActive] = useState(false);
  const [showCompletedOff, setShowCompletedOff] = useState(false);
  const [empStatusFilter, setEmpStatusFilter] = useState("");
  const [leaveStatusFilter, setLeaveStatusFilter] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [selectedOffId, setSelectedOffId] = useState(null);
  const [selectedEmpId, setSelectedEmpId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addingLeave, setAddingLeave] = useState(false);
  const [confirmDeleteOnboarding, setConfirmDeleteOnboarding] = useState(false);
  const [confirmStartOffboarding, setConfirmStartOffboarding] = useState(null);
  const [confirmDeleteOffboarding, setConfirmDeleteOffboarding] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(false);
  const [editingOffTemplate, setEditingOffTemplate] = useState(false);
  const [form, setForm] = useState({ hire_name: "", hire_email: "" });
  const [leaveForm, setLeaveForm] = useState({
    employee_id: "", type: "vacation", start_date: "", end_date: "", note: "",
  });
  const [tmplDraft, setTmplDraft] = useState([]);
  const [offTmplDraft, setOffTmplDraft] = useState([]);

  // Deep-link from People "View in HR" → /app/departments/hr?employee=<id>
  useEffect(() => {
    const emp = searchParams.get("employee");
    if (!emp) return;
    setTab("employees");
    setSelectedEmpId(emp);
  }, [searchParams]);

  const all = useMemo(() => data?.instances || [], [data?.instances]);
  const visible = useMemo(
    () => (showActive ? all : all.filter((i) => i.overall_status !== "active")),
    [all, showActive],
  );
  const selected = all.find((i) => i.id === selectedId) || null;

  const employees = useMemo(() => {
    const rows = empData?.employees || [];
    if (!empStatusFilter) return rows;
    return rows.filter((e) => e.status === empStatusFilter);
  }, [empData?.employees, empStatusFilter]);
  const selectedEmp = (empData?.employees || []).find((e) => e.id === selectedEmpId) || null;

  const offAll = useMemo(() => offData?.instances || [], [offData?.instances]);
  const offVisible = useMemo(
    () => (showCompletedOff ? offAll : offAll.filter((i) => i.overall_status !== "active")),
    [offAll, showCompletedOff],
  );
  const selectedOff = offAll.find((i) => i.id === selectedOffId) || null;

  const workspaceMembers = (membersData?.members || []).filter((m) => m.user_id && m.status === "active");
  const isLead = Boolean(data?.is_lead || tmplData?.can_edit_template || empData?.is_lead || leaveData?.is_lead);
  const myId = data?.my_user_id || leaveData?.my_user_id;

  const leaveRequests = useMemo(() => {
    const rows = leaveData?.requests || [];
    if (!leaveStatusFilter) return rows;
    return rows.filter((r) => r.status === leaveStatusFilter);
  }, [leaveData?.requests, leaveStatusFilter]);

  const myLinkedEmployees = useMemo(() => {
    const rows = empData?.employees || [];
    if (isLead) return rows.filter((e) => e.status !== "departed");
    return rows.filter((e) => e.linked_user_id === myId && e.status !== "departed");
  }, [empData?.employees, isLead, myId]);

  const templateSteps = tmplData?.template?.steps;
  const templateUpdatedAt = tmplData?.template?.updated_at;
  const offTemplateSteps = offTmplData?.template?.steps;
  const offTemplateUpdatedAt = offTmplData?.template?.updated_at;

  useEffect(() => {
    const steps = templateSteps || [];
    setTmplDraft(steps.map((s) => ({ ...s })));
  }, [templateUpdatedAt, editingTemplate, templateSteps]);

  useEffect(() => {
    const steps = offTemplateSteps || [];
    setOffTmplDraft(steps.map((s) => ({ ...s })));
  }, [offTemplateUpdatedAt, editingOffTemplate, offTemplateSteps]);

  if (loading) {
    return (
      <div>
        <PageHeader title="HR" subtitle="Onboarding, employee records, and offboarding, with no sensitive employment data stored." />
        <SkeletonKPIRow count={4} />
        <SkeletonCardList count={4} />
      </div>
    );
  }
  if (error) {
    const status = error?.response?.status;
    if (status === 403) {
      return (
        <ErrorScreen
          label="Access denied"
          message="You are not a member of HR. Ask your CEO to add you."
          onRetry={reload}
        />
      );
    }
    if (status === 404) {
      return (
        <ErrorScreen
          label="HR not enabled"
          message="Enable HR under Settings → Departments first."
          onRetry={reload}
        />
      );
    }
    return (
      <ErrorScreen
        label="Could not load HR"
        message={fetchErrorMessage(error, "HR data is unavailable.")}
        onRetry={reload}
      />
    );
  }

  const createInstance = async () => {
    if (!form.hire_name.trim()) {
      toast.error("Hire name is required");
      return;
    }
    setBusy(true);
    try {
      const { data: res } = await api.post("/hr/onboarding", {
        hire_name: form.hire_name.trim(),
        hire_email: form.hire_email.trim(),
      });
      toast.success("Onboarding started");
      setForm({ hire_name: "", hire_email: "" });
      setAdding(false);
      await reload();
      if (res?.instance?.id) setSelectedId(res.instance.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create onboarding");
    } finally {
      setBusy(false);
    }
  };

  const patchStep = async (step, patch) => {
    if (!selected) return;
    setBusy(true);
    try {
      const { data: res } = await api.patch(`/hr/onboarding/${selected.id}`, {
        step_id: step.id,
        ...patch,
      });
      await Promise.all([reload(), reloadEmp(), reloadSummary()]);
      if (res?.instance?.id) setSelectedId(res.instance.id);
      if (res?.instance?.overall_status === "active") {
        toast.success("Onboarding complete. Employee record created");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update step");
    } finally {
      setBusy(false);
    }
  };

  const deleteInstance = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.delete(`/hr/onboarding/${selected.id}`);
      toast.success("Onboarding deleted");
      setConfirmDeleteOnboarding(false);
      setSelectedId(null);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    } finally {
      setBusy(false);
    }
  };

  const saveTemplate = async () => {
    const steps = tmplDraft
      .map((s, i) => ({ id: s.id, name: (s.name || "").trim(), order: i }))
      .filter((s) => s.name);
    if (!steps.length) {
      toast.error("Template needs at least one step");
      return;
    }
    setBusy(true);
    try {
      await api.patch("/hr/template", { steps });
      toast.success("Template updated");
      setEditingTemplate(false);
      await reloadTmpl();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save template");
    } finally {
      setBusy(false);
    }
  };

  const saveOffTemplate = async () => {
    const steps = offTmplDraft
      .map((s, i) => ({ id: s.id, name: (s.name || "").trim(), order: i }))
      .filter((s) => s.name);
    if (!steps.length) {
      toast.error("Template needs at least one step");
      return;
    }
    setBusy(true);
    try {
      await api.patch("/hr/offboarding/template", { steps });
      toast.success("Offboarding template updated");
      setEditingOffTemplate(false);
      await reloadOffTmpl();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save template");
    } finally {
      setBusy(false);
    }
  };

  const moveTmplStep = (draft, setDraft, idx, dir) => {
    const next = [...draft];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    setDraft(next);
  };

  const startOffboarding = async () => {
    const employee = confirmStartOffboarding;
    if (!employee) return;
    setBusy(true);
    try {
      const { data: res } = await api.post("/hr/offboarding", { employee_id: employee.id });
      toast.success("Offboarding started");
      setConfirmStartOffboarding(null);
      await reloadOff();
      setTab("offboarding");
      if (res?.instance?.id) setSelectedOffId(res.instance.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start offboarding");
    } finally {
      setBusy(false);
    }
  };

  const patchOffStep = async (step, patch) => {
    if (!selectedOff) return;
    setBusy(true);
    try {
      const { data: res } = await api.patch(`/hr/offboarding/${selectedOff.id}`, {
        step_id: step.id,
        ...patch,
      });
      await Promise.all([reloadOff(), reloadEmp(), reloadSummary()]);
      if (res?.instance?.id) setSelectedOffId(res.instance.id);
      if (res?.instance?.overall_status === "active") {
        toast.success("Offboarding complete. Employee marked departed");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update step");
    } finally {
      setBusy(false);
    }
  };

  const deleteOffInstance = async () => {
    if (!selectedOff) return;
    setBusy(true);
    try {
      await api.delete(`/hr/offboarding/${selectedOff.id}`);
      toast.success("Offboarding deleted");
      setConfirmDeleteOffboarding(false);
      setSelectedOffId(null);
      await reloadOff();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    } finally {
      setBusy(false);
    }
  };

  const createLeave = async () => {
    if (!leaveForm.employee_id) {
      toast.error("Select an employee");
      return;
    }
    if (!leaveForm.start_date || !leaveForm.end_date) {
      toast.error("Start and end dates are required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/hr/leave-requests", {
        employee_id: leaveForm.employee_id,
        type: leaveForm.type,
        start_date: leaveForm.start_date,
        end_date: leaveForm.end_date,
        note: leaveForm.note.trim(),
      });
      toast.success("Leave request submitted");
      setLeaveForm({ employee_id: "", type: "vacation", start_date: "", end_date: "", note: "" });
      setAddingLeave(false);
      await reloadLeave();
      await reloadSummary();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not submit leave request");
    } finally {
      setBusy(false);
    }
  };

  const decideLeave = async (req, status) => {
    setBusy(true);
    try {
      await api.patch(`/hr/leave-requests/${req.id}`, { status });
      toast.success(
        status === "approved"
          ? "Leave approved"
          : status === "canceled"
            ? "Leave request canceled"
            : "Leave denied",
      );
      await reloadLeave();
      await reloadSummary();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update leave request");
    } finally {
      setBusy(false);
    }
  };

  const tabs = [
    { id: "onboarding", label: "Onboarding" },
    { id: "employees", label: "Employees" },
    { id: "leave", label: "Leave" },
    { id: "offboarding", label: "Offboarding" },
  ];

  return (
    <div data-testid="hr-page">
      <PageHeader
        title={data?.name || "HR"}
        subtitle="Onboarding, employee records, and offboarding, with no sensitive employment data stored."
        action={(
          <div className="flex items-center gap-2">
            {isLead && tab === "onboarding" && (
              <button
                type="button"
                data-testid="hr-edit-template-btn"
                onClick={() => setEditingTemplate(true)}
                className="rounded-md border border-helm-fg/15 text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5"
              >
                Edit template
              </button>
            )}
            {isLead && tab === "offboarding" && (
              <button
                type="button"
                data-testid="hr-edit-offboarding-template-btn"
                onClick={() => setEditingOffTemplate(true)}
                className="rounded-md border border-helm-fg/15 text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5"
              >
                Edit template
              </button>
            )}
            {tab === "leave" && myLinkedEmployees.length > 0 && (
              <button
                type="button"
                data-testid="hr-add-leave-btn"
                onClick={() => setAddingLeave(true)}
                className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover"
              >
                <Plus className="w-4 h-4" /> Request leave
              </button>
            )}
            {isLead && tab === "onboarding" && (
              <button
                type="button"
                data-testid="hr-add-onboarding-btn"
                onClick={() => setAdding(true)}
                className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover"
              >
                <Plus className="w-4 h-4" /> New hire
              </button>
            )}
          </div>
        )}
      />

      {summaryData?.headcount && (
        <div
          className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5"
          data-testid="hr-summary-stats"
        >
          {[
            { key: "active", label: "Active", value: summaryData.headcount.active ?? 0 },
            { key: "on_leave", label: "On leave", value: summaryData.headcount.on_leave ?? 0 },
            { key: "departed", label: "Departed", value: summaryData.headcount.departed ?? 0 },
            {
              key: "pending_leave",
              label: "Pending leave",
              value: summaryData.pending_leave_requests ?? 0,
            },
            {
              key: "departed_90d",
              label: "Departed (90d)",
              value: summaryData.departed_last_90_days ?? 0,
            },
          ].map((s) => (
            <div
              key={s.key}
              className="rounded-md border border-helm-line bg-helm-card/40 px-3 py-2.5"
              data-testid={`hr-summary-${s.key}`}
            >
              <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-helm-muted">
                {s.label}
              </p>
              <p className="font-mono text-xl text-helm-fg mt-1">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1 mb-5 border-b border-helm-line" data-testid="hr-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            data-testid={`hr-tab-${t.id}`}
            onClick={() => setTab(t.id)}
            className={cn(
              "px-3 py-2 text-sm border-b-2 -mb-px transition-colors",
              tab === t.id
                ? "border-helm-gold text-helm-fg"
                : "border-transparent text-helm-muted hover:text-helm-fg",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "onboarding" && (
        <>
          <div className="flex items-center justify-between gap-3 mb-4">
            <p className="text-xs text-helm-muted font-mono">
              {visible.length} shown · {all.length} total
            </p>
            <label className="inline-flex items-center gap-2 text-xs text-helm-muted cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="hr-show-active"
                checked={showActive}
                onChange={(e) => setShowActive(e.target.checked)}
                className="rounded border-helm-fg/20 bg-transparent"
              />
              Show completed (active)
            </label>
          </div>

          {visible.length === 0 ? (
            <EmptyState
              icon={Users}
              title={all.length ? "No open onboardings" : "No onboardings yet"}
              body={
                all.length
                  ? "Turn on “Show completed” to see finished hires, or start a new one."
                  : isLead
                    ? "Start onboarding for a new hire. Their checklist is copied from the template."
                    : "Ask an HR lead or the CEO to start onboarding for a new hire."
              }
              action={isLead ? (
                <button
                  type="button"
                  onClick={() => setAdding(true)}
                  className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"
                >
                  <Plus className="w-4 h-4" /> New hire
                </button>
              ) : null}
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line mb-6">
              <table className="w-full text-left text-sm" data-testid="hr-table">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                    <th className="px-3 py-2 font-medium">Hire</th>
                    <th className="px-3 py-2 font-medium">Progress</th>
                    <th className="px-3 py-2 font-medium">Open steps</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((inst) => {
                    const open = (inst.steps || []).filter((s) => s.status !== "done");
                    return (
                      <tr
                        key={inst.id}
                        data-testid={`hr-row-${inst.id}`}
                        onClick={() => setSelectedId(inst.id)}
                        className={cn(
                          "border-b border-helm-line cursor-pointer transition-colors hover:bg-helm-fg/[0.03]",
                          selectedId === inst.id && "bg-helm-gold/12",
                        )}
                      >
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-2 min-w-0">
                            <p className="text-helm-fg truncate max-w-[14rem]">{inst.hire_name}</p>
                            <PossiblyStaleBadge show={inst.possibly_stale} />
                          </div>
                          {inst.hire_email && (
                            <p className="text-[11px] text-helm-muted truncate">{inst.hire_email}</p>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-helm-muted font-mono text-xs">
                          {inst.progress?.done || 0}/{inst.progress?.total || 0}
                        </td>
                        <td className="px-3 py-2.5 text-helm-muted truncate max-w-[14rem] text-xs">
                          {open.length ? open.map((s) => s.name).join(", ") : "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={cn(
                            "text-[10px] font-mono uppercase tracking-wide",
                            inst.overall_status === "active" ? "text-helm-status-positive" : "text-helm-muted",
                          )}
                          >
                            {inst.overall_status === "active" ? "Active" : "In progress"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {selected && (
            <GlassCard className="p-5 space-y-4" data-testid="hr-detail">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <SectionLabel>Onboarding checklist</SectionLabel>
                  <p className="text-helm-fg text-sm mt-1">{selected.hire_name}</p>
                  {selected.hire_email && (
                    <p className="text-xs text-helm-muted">{selected.hire_email}</p>
                  )}
                </div>
                <button type="button" onClick={() => setSelectedId(null)} className="text-helm-muted hover:text-helm-fg">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-2" data-testid="hr-steps">
                {[...(selected.steps || [])].sort((a, b) => (a.order || 0) - (b.order || 0)).map((step) => {
                  const canEditStep = isLead || step.assigned_to === myId;
                  return (
                    <div
                      key={step.id}
                      data-testid={`hr-step-${step.id}`}
                      className="rounded-md border border-helm-line bg-helm-fg/[0.02] p-3 space-y-2"
                    >
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <p className="text-sm text-helm-fg">{step.name}</p>
                        <StepBadge status={step.status} />
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <label className="space-y-1">
                          <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Status</span>
                          <select
                            disabled={!canEditStep || busy}
                            value={step.status}
                            onChange={(e) => patchStep(step, { status: e.target.value })}
                            className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg disabled:opacity-50"
                          >
                            {(data?.step_statuses || ["not_started", "in_progress", "done"]).map((s) => (
                              <option key={s} value={s}>{STEP_STATUS_META[s]?.label || s}</option>
                            ))}
                          </select>
                        </label>
                        <label className="space-y-1">
                          <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Assignee</span>
                          <select
                            disabled={!isLead || busy}
                            value={step.assigned_to || ""}
                            onChange={(e) => patchStep(step, { assigned_to: e.target.value || null })}
                            className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg disabled:opacity-50"
                          >
                            <option value="">Unassigned</option>
                            {workspaceMembers.map((m) => (
                              <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <p className="text-[11px] text-helm-muted">Assignee: {personLabel(step.assignee)}</p>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center gap-2 text-xs text-helm-muted">
                <span>
                  Overall:{" "}
                  <span className={selected.overall_status === "active" ? "text-helm-status-positive" : "text-helm-muted"}>
                    {selected.overall_status === "active" ? "Active" : "In progress"}
                  </span>
                </span>
                <span className="font-mono">
                  {selected.progress?.done || 0}/{selected.progress?.total || 0} steps done
                </span>
                {isLead && (
                  <CirDeleteBtn
                    disabled={busy}
                    data-testid="hr-delete-btn"
                    onClick={() => setConfirmDeleteOnboarding(true)}
                    size="md"
                    title="Delete onboarding"
                    className="ml-auto"
                  />
                )}
              </div>
            </GlassCard>
          )}
        </>
      )}

      {tab === "employees" && (
        <>
          <div className="flex items-center justify-between gap-3 mb-4">
            <p className="text-xs text-helm-muted font-mono">
              {employees.length} shown · {(empData?.employees || []).length} total
            </p>
            <label className="inline-flex items-center gap-2 text-xs text-helm-muted">
              <span className="font-mono uppercase tracking-wide text-[10px]">Status</span>
              <select
                data-testid="hr-employee-status-filter"
                value={empStatusFilter}
                onChange={(e) => setEmpStatusFilter(e.target.value)}
                className="rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1 text-sm text-helm-fg"
              >
                <option value="">All</option>
                {(empData?.statuses || ["active", "on_leave", "departed"]).map((s) => (
                  <option key={s} value={s}>{EMPLOYEE_STATUS_META[s]?.label || s}</option>
                ))}
              </select>
            </label>
          </div>

          {employees.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No employee records yet"
              body="Complete an onboarding checklist, which creates the employee record automatically."
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line mb-6">
              <table className="w-full text-left text-sm" data-testid="hr-employees-table">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Role</th>
                    <th className="px-3 py-2 font-medium">Start</th>
                    <th className="px-3 py-2 font-medium">Team(s)</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.map((emp) => {
                    const meta = EMPLOYEE_STATUS_META[emp.status] || EMPLOYEE_STATUS_META.active;
                    return (
                      <tr
                        key={emp.id}
                        data-testid={`hr-employee-${emp.id}`}
                        onClick={() => setSelectedEmpId(emp.id)}
                        className={cn(
                          "border-b border-helm-line cursor-pointer transition-colors hover:bg-helm-fg/[0.03]",
                          selectedEmpId === emp.id && "bg-helm-gold/12",
                        )}
                      >
                        <td className="px-3 py-2.5 text-helm-fg">{emp.name}</td>
                        <td className="px-3 py-2.5 text-helm-muted text-xs">{emp.role || "—"}</td>
                        <td className="px-3 py-2.5 text-helm-muted font-mono text-xs">{emp.start_date || "—"}</td>
                        <td className="px-3 py-2.5 text-helm-muted text-xs truncate max-w-[12rem]">{emp.department_names || "—"}</td>
                        <td className={cn("px-3 py-2.5 text-[10px] font-mono uppercase tracking-wide", meta.className)}>
                          {meta.label}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {selectedEmp && (
            <GlassCard className="p-5 space-y-3" data-testid="hr-employee-detail">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <SectionLabel>Employee</SectionLabel>
                  <p className="text-helm-fg text-sm mt-1">{selectedEmp.name}</p>
                  <p className="text-xs text-helm-muted mt-1">
                    Employment record only. Trenston never stores medical data, government IDs, compensation, or protected characteristics.
                  </p>
                </div>
                <button type="button" onClick={() => setSelectedEmpId(null)} className="text-helm-muted hover:text-helm-fg">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Role</dt>
                  <dd className="text-helm-fg">{selectedEmp.role || "—"}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Status</dt>
                  <dd className={EMPLOYEE_STATUS_META[selectedEmp.status]?.className || ""}>
                    {EMPLOYEE_STATUS_META[selectedEmp.status]?.label || selectedEmp.status}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Start date</dt>
                  <dd className="text-helm-fg font-mono text-xs">{selectedEmp.start_date || "—"}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Team(s)</dt>
                  <dd className="text-helm-fg">{selectedEmp.department_names || "—"}</dd>
                </div>
              </dl>
              {isLead && selectedEmp.status !== "departed" && (
                <button
                  type="button"
                  disabled={busy}
                  data-testid="hr-start-offboarding-btn"
                  onClick={() => setConfirmStartOffboarding(selectedEmp)}
                  className="rounded-md border border-helm-fg/15 text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5 disabled:opacity-50"
                >
                  Start offboarding
                </button>
              )}
            </GlassCard>
          )}
        </>
      )}

      {tab === "leave" && (
        <>
          <div className="flex items-center justify-between gap-3 mb-4">
            <p className="text-xs text-helm-muted font-mono">
              {leaveRequests.length} shown · {(leaveData?.requests || []).length} total
            </p>
            <label className="inline-flex items-center gap-2 text-xs text-helm-muted">
              <span className="font-mono uppercase tracking-wide text-[10px]">Status</span>
              <select
                data-testid="hr-leave-status-filter"
                value={leaveStatusFilter}
                onChange={(e) => setLeaveStatusFilter(e.target.value)}
                className="rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1 text-sm text-helm-fg"
              >
                <option value="">All</option>
                {(leaveData?.statuses || ["pending", "approved", "denied"]).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
          </div>

          {leaveRequests.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No leave requests"
              body={
                myLinkedEmployees.length
                  ? "Submit a leave request. Approved dates appear on the Calendar."
                  : isLead
                    ? "Link an employee to a Trenston user (or create records via onboarding) before requesting leave."
                    : "Ask an HR lead to link your account to an employee record, then you can request leave."
              }
              action={myLinkedEmployees.length ? (
                <button
                  type="button"
                  onClick={() => setAddingLeave(true)}
                  className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"
                >
                  <Plus className="w-4 h-4" /> Request leave
                </button>
              ) : null}
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line mb-6">
              <table className="w-full text-left text-sm" data-testid="hr-leave-table">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                    <th className="px-3 py-2 font-medium">Employee</th>
                    <th className="px-3 py-2 font-medium">Type</th>
                    <th className="px-3 py-2 font-medium">Dates</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium"> </th>
                  </tr>
                </thead>
                <tbody>
                  {leaveRequests.map((req) => (
                    <tr
                      key={req.id}
                      data-testid={`hr-leave-${req.id}`}
                      className="border-b border-helm-line"
                    >
                      <td className="px-3 py-2.5 text-helm-fg">{req.employee_name || req.title}</td>
                      <td className="px-3 py-2.5 text-helm-muted text-xs capitalize">{req.type}</td>
                      <td className="px-3 py-2.5 text-helm-muted font-mono text-xs">
                        {req.start_date}
                        {req.end_date && req.end_date !== req.start_date ? ` → ${req.end_date}` : ""}
                      </td>
                      <td className="px-3 py-2.5 text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                        {req.status}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {req.status === "pending" && (
                          <span className="inline-flex gap-2">
                            {isLead && (
                              <>
                                <button
                                  type="button"
                                  disabled={busy}
                                  data-testid={`hr-leave-approve-${req.id}`}
                                  onClick={() => decideLeave(req, "approved")}
                                  className="text-xs text-helm-status-positive hover:underline disabled:opacity-50"
                                >
                                  Approve
                                </button>
                                <button
                                  type="button"
                                  disabled={busy}
                                  data-testid={`hr-leave-deny-${req.id}`}
                                  onClick={() => decideLeave(req, "denied")}
                                  className="text-xs text-helm-status-negative hover:underline disabled:opacity-50"
                                >
                                  Deny
                                </button>
                              </>
                            )}
                            {req.requested_by === myId && (
                              <button
                                type="button"
                                disabled={busy}
                                data-testid={`hr-leave-cancel-${req.id}`}
                                onClick={() => decideLeave(req, "canceled")}
                                className="text-xs text-helm-muted hover:text-helm-fg hover:underline disabled:opacity-50"
                              >
                                Cancel request
                              </button>
                            )}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "offboarding" && (
        <>
          <div className="flex items-center justify-between gap-3 mb-4">
            <p className="text-xs text-helm-muted font-mono">
              {offVisible.length} shown · {offAll.length} total
            </p>
            <label className="inline-flex items-center gap-2 text-xs text-helm-muted cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="hr-show-completed-offboarding"
                checked={showCompletedOff}
                onChange={(e) => setShowCompletedOff(e.target.checked)}
                className="rounded border-helm-fg/20 bg-transparent"
              />
              Show completed
            </label>
          </div>

          {offVisible.length === 0 ? (
            <EmptyState
              icon={Users}
              title={offAll.length ? "No open offboardings" : "No offboardings yet"}
              body="Start offboarding from an employee record. Status becomes departed only after every step is done."
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-helm-line mb-6">
              <table className="w-full text-left text-sm" data-testid="hr-offboarding-table">
                <thead>
                  <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                    <th className="px-3 py-2 font-medium">Employee</th>
                    <th className="px-3 py-2 font-medium">Progress</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {offVisible.map((inst) => (
                    <tr
                      key={inst.id}
                      data-testid={`hr-off-row-${inst.id}`}
                      onClick={() => setSelectedOffId(inst.id)}
                      className={cn(
                        "border-b border-helm-line cursor-pointer transition-colors hover:bg-helm-fg/[0.03]",
                        selectedOffId === inst.id && "bg-helm-gold/12",
                      )}
                    >
                      <td className="px-3 py-2.5 text-helm-fg">{inst.employee_name}</td>
                      <td className="px-3 py-2.5 text-helm-muted font-mono text-xs">
                        {inst.progress?.done || 0}/{inst.progress?.total || 0}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={cn(
                          "text-[10px] font-mono uppercase tracking-wide",
                          inst.overall_status === "active" ? "text-helm-status-positive" : "text-helm-muted",
                        )}
                        >
                          {inst.overall_status === "active" ? "Complete" : "In progress"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {selectedOff && (
            <GlassCard className="p-5 space-y-4" data-testid="hr-offboarding-detail">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <SectionLabel>Offboarding checklist</SectionLabel>
                  <p className="text-helm-fg text-sm mt-1">{selectedOff.employee_name}</p>
                  <p className="text-xs text-helm-muted mt-1">
                    Employee stays active until every step is marked done.
                  </p>
                </div>
                <button type="button" onClick={() => setSelectedOffId(null)} className="text-helm-muted hover:text-helm-fg">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-2" data-testid="hr-offboarding-steps">
                {[...(selectedOff.steps || [])].sort((a, b) => (a.order || 0) - (b.order || 0)).map((step) => {
                  const canEditStep = isLead || step.assigned_to === myId;
                  return (
                    <div
                      key={step.id}
                      className="rounded-md border border-helm-line bg-helm-fg/[0.02] p-3 space-y-2"
                    >
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <p className="text-sm text-helm-fg">{step.name}</p>
                        <StepBadge status={step.status} />
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <label className="space-y-1">
                          <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Status</span>
                          <select
                            disabled={!canEditStep || busy}
                            value={step.status}
                            onChange={(e) => patchOffStep(step, { status: e.target.value })}
                            className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg disabled:opacity-50"
                          >
                            {(offData?.step_statuses || ["not_started", "in_progress", "done"]).map((s) => (
                              <option key={s} value={s}>{STEP_STATUS_META[s]?.label || s}</option>
                            ))}
                          </select>
                        </label>
                        <label className="space-y-1">
                          <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Assignee</span>
                          <select
                            disabled={!isLead || busy}
                            value={step.assigned_to || ""}
                            onChange={(e) => patchOffStep(step, { assigned_to: e.target.value || null })}
                            className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg disabled:opacity-50"
                          >
                            <option value="">Unassigned</option>
                            {workspaceMembers.map((m) => (
                              <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>
                            ))}
                          </select>
                        </label>
                      </div>
                    </div>
                  );
                })}
              </div>

              {isLead && (
                <CirDeleteBtn
                  disabled={busy}
                  data-testid="hr-delete-offboarding-btn"
                  onClick={() => setConfirmDeleteOffboarding(true)}
                  size="md"
                  title="Delete offboarding"
                />
              )}
            </GlassCard>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmDeleteOnboarding && Boolean(selected)}
        title={`Delete onboarding for “${selected?.hire_name || ""}”?`}
        description="This permanently removes the onboarding checklist. This can’t be undone."
        confirmLabel="Delete onboarding"
        busy={busy}
        onCancel={() => setConfirmDeleteOnboarding(false)}
        onConfirm={deleteInstance}
        testId="delete-hr-onboarding-confirm"
      />

      <ConfirmDialog
        open={Boolean(confirmStartOffboarding)}
        title={`Start offboarding for “${confirmStartOffboarding?.name || ""}”?`}
        description="Status becomes departed only after every offboarding step is done."
        confirmLabel="Start offboarding"
        busy={busy}
        onCancel={() => setConfirmStartOffboarding(null)}
        onConfirm={startOffboarding}
        testId="start-hr-offboarding-confirm"
      />

      <ConfirmDialog
        open={confirmDeleteOffboarding && Boolean(selectedOff)}
        title={`Delete offboarding for “${selectedOff?.employee_name || ""}”?`}
        description="This permanently removes the offboarding checklist. This can’t be undone."
        confirmLabel="Delete offboarding"
        busy={busy}
        onCancel={() => setConfirmDeleteOffboarding(false)}
        onConfirm={deleteOffInstance}
        testId="delete-hr-offboarding-confirm"
      />

      {addingLeave && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setAddingLeave(false)} />
          <div className="relative w-full max-w-md rounded-md border border-helm-line bg-helm-card p-5 space-y-3" data-testid="hr-leave-modal">
            <div className="flex items-center justify-between">
              <p className="text-sm text-helm-fg font-medium">Request leave</p>
              <button type="button" onClick={() => setAddingLeave(false)} className="text-helm-muted hover:text-helm-fg">
                <X className="w-4 h-4" />
              </button>
            </div>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Employee</span>
              <select
                data-testid="hr-leave-employee"
                value={leaveForm.employee_id}
                onChange={(e) => setLeaveForm((f) => ({ ...f, employee_id: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              >
                <option value="">Select…</option>
                {myLinkedEmployees.map((e) => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Type</span>
              <select
                data-testid="hr-leave-type"
                value={leaveForm.type}
                onChange={(e) => setLeaveForm((f) => ({ ...f, type: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              >
                {(leaveData?.types || ["vacation", "sick", "personal", "other"]).map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Start</span>
                <input
                  type="date"
                  data-testid="hr-leave-start"
                  value={leaveForm.start_date}
                  onChange={(e) => setLeaveForm((f) => ({ ...f, start_date: e.target.value }))}
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">End</span>
                <input
                  type="date"
                  data-testid="hr-leave-end"
                  value={leaveForm.end_date}
                  onChange={(e) => setLeaveForm((f) => ({ ...f, end_date: e.target.value }))}
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                />
              </label>
            </div>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Note</span>
              <input
                data-testid="hr-leave-note"
                value={leaveForm.note}
                onChange={(e) => setLeaveForm((f) => ({ ...f, note: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              />
            </label>
            <p className="text-[11px] text-helm-muted">
              Approved leave appears on the Calendar for the full date range. No leave balances are tracked yet.
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setAddingLeave(false)} className="text-sm text-helm-muted px-3 py-2">Cancel</button>
              <button
                type="button"
                disabled={busy}
                data-testid="hr-leave-submit"
                onClick={createLeave}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Submit request
              </button>
            </div>
          </div>
        </div>
      )}

      {adding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setAdding(false)} />
          <div className="relative w-full max-w-md rounded-md border border-helm-line bg-helm-card p-5 space-y-3" data-testid="hr-create-modal">
            <div className="flex items-center justify-between">
              <p className="text-sm text-helm-fg font-medium">Start onboarding</p>
              <button type="button" onClick={() => setAdding(false)} className="text-helm-muted hover:text-helm-fg">
                <X className="w-4 h-4" />
              </button>
            </div>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Hire name</span>
              <input
                data-testid="hr-new-name"
                value={form.hire_name}
                onChange={(e) => setForm((f) => ({ ...f, hire_name: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                autoFocus
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Email</span>
              <input
                data-testid="hr-new-email"
                value={form.hire_email}
                onChange={(e) => setForm((f) => ({ ...f, hire_email: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              />
            </label>
            <p className="text-[11px] text-helm-muted">
              Checklist will be copied from the current template ({(tmplData?.template?.steps || []).length} steps).
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setAdding(false)} className="text-sm text-helm-muted px-3 py-2">Cancel</button>
              <button
                type="button"
                disabled={busy}
                data-testid="hr-create-submit"
                onClick={createInstance}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Start onboarding
              </button>
            </div>
          </div>
        </div>
      )}

      {editingTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setEditingTemplate(false)} />
          <div className="relative w-full max-w-lg rounded-md border border-helm-line bg-helm-card p-5 space-y-3 max-h-[85vh] overflow-y-auto" data-testid="hr-template-modal">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-helm-fg font-medium">Onboarding template</p>
                <p className="text-[11px] text-helm-muted">Changes only affect future hires.</p>
              </div>
              <button type="button" onClick={() => setEditingTemplate(false)} className="text-helm-muted hover:text-helm-fg">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-2">
              {tmplDraft.map((step, idx) => (
                <div key={step.id || idx} className="flex items-center gap-2">
                  <input
                    value={step.name}
                    onChange={(e) => {
                      const next = [...tmplDraft];
                      next[idx] = { ...next[idx], name: e.target.value };
                      setTmplDraft(next);
                    }}
                    className="flex-1 rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                  />
                  <button type="button" disabled={idx === 0} onClick={() => moveTmplStep(tmplDraft, setTmplDraft, idx, -1)} className="p-1 text-helm-muted hover:text-helm-fg disabled:opacity-30">
                    <ChevronUp className="w-4 h-4" />
                  </button>
                  <button type="button" disabled={idx === tmplDraft.length - 1} onClick={() => moveTmplStep(tmplDraft, setTmplDraft, idx, 1)} className="p-1 text-helm-muted hover:text-helm-fg disabled:opacity-30">
                    <ChevronDown className="w-4 h-4" />
                  </button>
                  <CirDeleteBtn
                    onClick={() => setTmplDraft((d) => d.filter((_, i) => i !== idx))}
                    title="Remove step"
                  />
                </div>
              ))}
            </div>
            <button
              type="button"
              data-testid="hr-template-add-step"
              onClick={() => setTmplDraft((d) => [...d, { id: `hstep_new_${Date.now()}`, name: "New step", order: d.length }])}
              className="inline-flex items-center gap-1 text-xs text-helm-gold"
            >
              <Plus className="w-3.5 h-3.5" /> Add step
            </button>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setEditingTemplate(false)} className="text-sm text-helm-muted px-3 py-2">Cancel</button>
              <button
                type="button"
                disabled={busy}
                data-testid="hr-template-save"
                onClick={saveTemplate}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Save template
              </button>
            </div>
          </div>
        </div>
      )}

      {editingOffTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setEditingOffTemplate(false)} />
          <div className="relative w-full max-w-lg rounded-md border border-helm-line bg-helm-card p-5 space-y-3 max-h-[85vh] overflow-y-auto" data-testid="hr-offboarding-template-modal">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-helm-fg font-medium">Offboarding template</p>
                <p className="text-[11px] text-helm-muted">Changes only affect future offboardings.</p>
              </div>
              <button type="button" onClick={() => setEditingOffTemplate(false)} className="text-helm-muted hover:text-helm-fg">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-2">
              {offTmplDraft.map((step, idx) => (
                <div key={step.id || idx} className="flex items-center gap-2">
                  <input
                    value={step.name}
                    onChange={(e) => {
                      const next = [...offTmplDraft];
                      next[idx] = { ...next[idx], name: e.target.value };
                      setOffTmplDraft(next);
                    }}
                    className="flex-1 rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                  />
                  <button type="button" disabled={idx === 0} onClick={() => moveTmplStep(offTmplDraft, setOffTmplDraft, idx, -1)} className="p-1 text-helm-muted hover:text-helm-fg disabled:opacity-30">
                    <ChevronUp className="w-4 h-4" />
                  </button>
                  <button type="button" disabled={idx === offTmplDraft.length - 1} onClick={() => moveTmplStep(offTmplDraft, setOffTmplDraft, idx, 1)} className="p-1 text-helm-muted hover:text-helm-fg disabled:opacity-30">
                    <ChevronDown className="w-4 h-4" />
                  </button>
                  <CirDeleteBtn
                    onClick={() => setOffTmplDraft((d) => d.filter((_, i) => i !== idx))}
                    title="Remove step"
                  />
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setOffTmplDraft((d) => [...d, { id: `hofstep_new_${Date.now()}`, name: "New step", order: d.length }])}
              className="inline-flex items-center gap-1 text-xs text-helm-gold"
            >
              <Plus className="w-3.5 h-3.5" /> Add step
            </button>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setEditingOffTemplate(false)} className="text-sm text-helm-muted px-3 py-2">Cancel</button>
              <button
                type="button"
                disabled={busy}
                onClick={saveOffTemplate}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Save template
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
