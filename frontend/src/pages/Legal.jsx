import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Plus, X, Scale, FileText, Upload } from "lucide-react";
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
  draft: { label: "Draft", className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35" },
  internal_review: { label: "Internal review", className: "bg-helm-muted/12 text-helm-fg border-helm-muted/35" },
  counterparty_review: { label: "Counterparty review", className: "bg-helm-status-warning/12 text-helm-fg border-helm-status-warning/35" },
  signed: { label: "Signed", className: "bg-helm-gold/12 text-helm-gold border-helm-gold/35" },
  filed: { label: "Filed", className: "bg-helm-status-positive/12 text-helm-fg border-helm-status-positive/35" },
};

const MEMBER_STATUSES = new Set(["draft", "internal_review"]);
const LEAD_STATUSES = ["draft", "internal_review", "counterparty_review", "signed", "filed"];

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.draft;
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide border", meta.className)}>
      {meta.label}
    </span>
  );
}

function personLabel(p) {
  if (!p) return "—";
  return p.name || p.email || "Teammate";
}

const FILED = new Set(["filed"]);

function isDueDateOverdue(dueDate, status) {
  if (FILED.has(status)) return false;
  const raw = (dueDate || "").trim();
  if (!raw) return false;
  const end = new Date(`${raw}T23:59:59`);
  if (Number.isNaN(end.getTime())) return false;
  return end.getTime() < Date.now();
}


export default function Legal() {
  const [counterpartyFilterInput, setCounterpartyFilterInput] = useState("");
  const [counterpartyFilter, setCounterpartyFilter] = useState("");
  const mattersUrl = counterpartyFilter.trim()
    ? `/legal/matters?counterparty=${encodeURIComponent(counterpartyFilter.trim())}`
    : "/legal/matters";
  const { data, loading, error, reload } = useFetch(mattersUrl);
  const { data: membersData } = useFetch("/members");
  const [showFiled, setShowFiled] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [form, setForm] = useState({ title: "", matter_type: "contract", assigned_to: "", notes: "", due_date: "", recurrence: "", counterparty: "" });
  const [counterpartySuggestions, setCounterpartySuggestions] = useState([]);
  const fileRef = useRef(null);

  const allMatters = useMemo(() => data?.matters || [], [data?.matters]);
  const visible = useMemo(
    () => (showFiled ? allMatters : allMatters.filter((m) => m.status !== "filed")),
    [allMatters, showFiled],
  );
  const selected = useMemo(
    () => allMatters.find((m) => m.id === selectedId) || null,
    [allMatters, selectedId],
  );
  const workspaceMembers = (membersData?.members || []).filter((m) => m.user_id && m.status === "active");

  useEffect(() => {
    if (!selected) {
      setDraft(null);
      return;
    }
    setDraft({
      title: selected.title || "",
      matter_type: selected.matter_type || "contract",
      assigned_to: selected.assigned_to || "",
      notes: selected.notes || "",
      status: selected.status || "draft",
      due_date: selected.due_date || "",
      recurrence: selected.recurrence || "",
      counterparty: selected.counterparty || "",
    });
  }, [selected]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Legal" subtitle="Matter queue for contracts and reviews moving independently." />
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
          message="You are not a member of Legal. Ask your CEO to add you."
          onRetry={reload}
        />
      );
    }
    if (status === 404) {
      return (
        <ErrorScreen
          label="Legal not enabled"
          message="Enable Legal under Settings → Departments first."
          onRetry={reload}
        />
      );
    }
    return (
      <ErrorScreen
        label="Could not load Legal"
        message={fetchErrorMessage(error, "Legal data is unavailable.")}
        onRetry={reload}
      />
    );
  }

  const isLead = Boolean(data?.is_lead || data?.can_reassign);
  const myId = data?.my_user_id;
  const isAssignee = selected && selected.assigned_to === myId;
  const canEdit = Boolean(selected && (isLead || isAssignee));
  const statusOptions = isLead ? LEAD_STATUSES : ["draft", "internal_review"];

  const createMatter = async () => {
    if (!form.title.trim()) {
      toast.error("Title is required");
      return;
    }
    setBusy(true);
    try {
      const body = {
        title: form.title.trim(),
        matter_type: form.matter_type,
        notes: form.notes.trim(),
        due_date: form.due_date.trim(),
        counterparty: form.counterparty.trim(),
        recurrence: form.matter_type === "compliance" && form.recurrence ? form.recurrence : null,
      };
      if (form.assigned_to) body.assigned_to = form.assigned_to;
      const { data: res } = await api.post("/legal/matters", body);
      toast.success("Matter created");
      setForm({ title: "", matter_type: "contract", assigned_to: "", notes: "", due_date: "", recurrence: "", counterparty: "" });
      setCounterpartySuggestions([]);
      setAdding(false);
      await reload();
      if (res?.matter?.id) setSelectedId(res.matter.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create matter");
    } finally {
      setBusy(false);
    }
  };

  const saveMatter = async () => {
    if (!selected || !draft) return;
    const body = {};
    if (canEdit) {
      body.title = draft.title.trim();
      body.matter_type = draft.matter_type;
      body.notes = draft.notes;
      body.status = draft.status;
      body.due_date = (draft.due_date || "").trim();
      body.counterparty = (draft.counterparty || "").trim();
      body.recurrence = draft.matter_type === "compliance" ? (draft.recurrence || null) : null;
    }
    if (isLead && draft.assigned_to !== selected.assigned_to) {
      body.assigned_to = draft.assigned_to || null;
    }
    if (!isLead && !MEMBER_STATUSES.has(draft.status)) {
      toast.error("Only a lead or CEO can advance past internal review");
      return;
    }
    setBusy(true);
    try {
      const { data: res } = await api.patch(`/legal/matters/${selected.id}`, body);
      if (res?.renewal_matter?.id) {
        toast.success(`Matter filed. Next cycle created (${res.renewal_matter.due_date || "set a due date"})`);
      } else {
        toast.success("Matter updated");
      }
      await reload();
      if (res?.matter?.id) setSelectedId(res.matter.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update matter");
    } finally {
      setBusy(false);
    }
  };

  const uploadDocument = async (file) => {
    if (!selected || !file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data: res } = await api.post(`/legal/matters/${selected.id}/document`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Document attached");
      await reload();
      if (res?.matter?.id) setSelectedId(res.matter.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not upload document");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const viewDocument = async () => {
    if (!selected) return;
    setBusy(true);
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    try {
      const { data: res } = await api.get(`/legal/matters/${selected.id}/document`);
      if (res?.presigned_url) {
        if (tab) tab.location.href = res.presigned_url;
        else window.open(res.presigned_url, "_blank", "noopener,noreferrer");
      } else {
        tab?.close();
        toast.error("No download URL available");
      }
    } catch (e) {
      tab?.close();
      toast.error(e?.response?.data?.detail || "Could not open document");
    } finally {
      setBusy(false);
    }
  };

  const deleteMatter = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.delete(`/legal/matters/${selected.id}`);
      toast.success("Matter deleted");
      setConfirmDelete(false);
      setSelectedId(null);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="legal-page">
      <PageHeader
        title={data?.name || "Legal"}
        subtitle="Matter queue for contracts and reviews moving independently."
        action={(
          <button
            type="button"
            data-testid="add-legal-matter-btn"
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover"
          >
            <Plus className="w-4 h-4" /> New matter
          </button>
        )}
      />

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-helm-muted font-mono">
            {visible.length} shown · {allMatters.length} total
          </p>
          <input
            data-testid="legal-counterparty-filter"
            value={counterpartyFilterInput}
            onChange={(e) => setCounterpartyFilterInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setCounterpartyFilter(counterpartyFilterInput.trim());
            }}
            placeholder="Filter counterparty (exact)"
            className="rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1 text-xs text-helm-fg w-44"
          />
          <button
            type="button"
            data-testid="legal-counterparty-filter-apply"
            onClick={() => setCounterpartyFilter(counterpartyFilterInput.trim())}
            className="text-xs text-helm-muted hover:text-helm-fg"
          >
            Apply
          </button>
          {counterpartyFilter.trim() ? (
            <button
              type="button"
              data-testid="legal-counterparty-filter-clear"
              onClick={() => { setCounterpartyFilter(""); setCounterpartyFilterInput(""); }}
              className="text-xs text-helm-muted hover:text-helm-fg"
            >
              Clear
            </button>
          ) : null}
        </div>
        <label className="inline-flex items-center gap-2 text-xs text-helm-muted cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="legal-show-filed"
            checked={showFiled}
            onChange={(e) => setShowFiled(e.target.checked)}
            className="rounded border-helm-fg/20 bg-transparent"
          />
          Show filed
        </label>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Scale}
          title={allMatters.length ? "No open matters" : "No matters yet"}
          body={
            allMatters.length
              ? "Turn on “Show filed” to see closed matters, or create a new one."
              : "Create a matter to track contracts, compliance, and reviews."
          }
          action={(
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"
            >
              <Plus className="w-4 h-4" /> New matter
            </button>
          )}
        />
      ) : (
        <div className="overflow-x-auto rounded-md border border-helm-line mb-6">
          <table className="w-full text-left text-sm" data-testid="legal-table">
            <thead>
              <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Counterparty</th>
                <th className="px-3 py-2 font-medium">Assignee</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Due</th>
                <th className="px-3 py-2 font-medium">Doc</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((m) => {
                const overdue = isDueDateOverdue(m.due_date, m.status);
                return (
                <tr
                  key={m.id}
                  data-testid={`legal-row-${m.id}`}
                  onClick={() => setSelectedId(m.id)}
                  className={cn(
                    "border-b border-helm-line cursor-pointer transition-colors hover:bg-helm-fg/[0.03]",
                    selectedId === m.id && "bg-helm-gold/12",
                  )}
                >
                  <td className="px-3 py-2.5 text-helm-fg truncate max-w-[16rem]">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="truncate">{m.title}</span>
                      <PossiblyStaleBadge show={m.possibly_stale} />
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-helm-muted capitalize">{m.matter_type || "—"}</td>
                  <td className="px-3 py-2.5 text-helm-muted truncate max-w-[10rem]">{m.counterparty || "—"}</td>
                  <td className="px-3 py-2.5 text-helm-muted truncate max-w-[10rem]">{personLabel(m.assignee)}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={m.status} /></td>
                  <td
                    className={cn(
                      "px-3 py-2.5 font-mono text-xs",
                      overdue ? "text-helm-status-negative" : "text-helm-muted",
                    )}
                    data-testid={`legal-due-${m.id}`}
                  >
                    {m.due_date ? (overdue ? `Overdue ${m.due_date}` : m.due_date) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-helm-muted">
                    {m.has_document ? <FileText className="w-3.5 h-3.5 text-helm-gold" /> : "—"}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && draft && (
        <GlassCard className="p-5 space-y-4" data-testid="legal-detail">
          <div className="flex items-start justify-between gap-3">
            <div>
              <SectionLabel>Matter detail</SectionLabel>
              <p className="text-helm-fg text-sm mt-1">{selected.title}</p>
            </div>
            <button type="button" onClick={() => setSelectedId(null)} className="text-helm-muted hover:text-helm-fg">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="space-y-1 md:col-span-2">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Title</span>
              <input
                data-testid="legal-edit-title"
                disabled={!canEdit || busy}
                value={draft.title}
                onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Type</span>
              <select
                data-testid="legal-edit-type"
                disabled={!canEdit || busy}
                value={draft.matter_type}
                onChange={(e) => setDraft((d) => ({ ...d, matter_type: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              >
                {(data?.matter_types || ["contract", "compliance", "other"]).map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Due date</span>
              <input
                type="date"
                data-testid="legal-edit-due-date"
                disabled={!canEdit || busy}
                value={draft.due_date || ""}
                onChange={(e) => setDraft((d) => ({ ...d, due_date: e.target.value }))}
                className={cn(
                  "w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm disabled:opacity-50",
                  isDueDateOverdue(draft.due_date, draft.status)
                    ? "text-helm-status-negative"
                    : "text-helm-fg",
                )}
              />
            </label>
            <label className="space-y-1 md:col-span-2">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Counterparty</span>
              <input
                data-testid="legal-edit-counterparty"
                disabled={!canEdit || busy}
                value={draft.counterparty || ""}
                onChange={(e) => setDraft((d) => ({ ...d, counterparty: e.target.value }))}
                placeholder="Vendor, customer, or other party"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              />
            </label>
            {draft.matter_type === "compliance" && (
              <label className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Recurrence</span>
                <select
                  data-testid="legal-edit-recurrence"
                  disabled={!canEdit || busy}
                  value={draft.recurrence || ""}
                  onChange={(e) => setDraft((d) => ({ ...d, recurrence: e.target.value }))}
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
                >
                  <option value="">One-off</option>
                  {(data?.recurrence_options || ["annual", "quarterly", "monthly"]).map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </label>
            )}
            <label className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Status</span>
              <select
                data-testid="legal-edit-status"
                disabled={!canEdit || busy}
                value={draft.status}
                onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              >
                {statusOptions.map((s) => (
                  <option key={s} value={s}>{STATUS_META[s]?.label || s}</option>
                ))}
                {!isLead && LEAD_STATUSES.filter((s) => !MEMBER_STATUSES.has(s)).includes(selected.status) && (
                  <option value={selected.status}>{STATUS_META[selected.status]?.label}</option>
                )}
              </select>
            </label>
            <label className="space-y-1 md:col-span-2">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Assignee</span>
              <select
                data-testid="legal-edit-assignee"
                disabled={!isLead || busy}
                value={draft.assigned_to || ""}
                onChange={(e) => setDraft((d) => ({ ...d, assigned_to: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
              >
                <option value="">Unassigned</option>
                {workspaceMembers.map((m) => (
                  <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>
                ))}
              </select>
              {!isLead && (
                <span className="text-[10px] text-helm-muted">Only a lead or CEO can reassign</span>
              )}
            </label>
          </div>

          <label className="block space-y-1">
            <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Notes</span>
            <textarea
              data-testid="legal-edit-notes"
              disabled={!canEdit || busy}
              value={draft.notes}
              onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
              rows={3}
              className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg disabled:opacity-50"
            />
          </label>

          <div className="rounded-md border border-helm-line bg-helm-fg/[0.02] p-3 space-y-2">
            <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Document</p>
            {selected.has_document ? (
              <div className="flex flex-wrap items-center gap-2 text-sm text-helm-fg">
                <FileText className="w-4 h-4 text-helm-gold shrink-0" />
                <span className="truncate">{selected.document?.filename || "Attached file"}</span>
                <button
                  type="button"
                  disabled={busy}
                  data-testid="legal-view-doc"
                  onClick={viewDocument}
                  className="text-xs text-helm-gold hover:underline disabled:opacity-50"
                >
                  View / download
                </button>
              </div>
            ) : (
              <p className="text-xs text-helm-muted">No document attached yet.</p>
            )}
            {canEdit && (
              <div>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,image/png,image/jpeg,application/pdf"
                  className="hidden"
                  data-testid="legal-doc-input"
                  onChange={(e) => uploadDocument(e.target.files?.[0])}
                />
                <button
                  type="button"
                  disabled={busy}
                  data-testid="legal-upload-doc"
                  onClick={() => fileRef.current?.click()}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-fg/15 text-helm-fg text-sm px-3 py-1.5 hover:bg-helm-fg/5 disabled:opacity-50"
                >
                  <Upload className="w-3.5 h-3.5" />
                  {selected.has_document ? "Replace document" : "Attach document"}
                </button>
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-4 text-xs text-helm-muted">
            <span>Created by: <span className="text-helm-fg">{personLabel(selected.creator)}</span></span>
            <span>Status: <StatusBadge status={selected.status} /></span>
          </div>

          <div className="flex flex-wrap gap-2">
            {canEdit && (
              <button
                type="button"
                disabled={busy}
                data-testid="legal-save-btn"
                onClick={saveMatter}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Save changes
              </button>
            )}
            {isLead && (
              <CirDeleteBtn
                disabled={busy}
                data-testid="legal-delete-btn"
                onClick={() => setConfirmDelete(true)}
                size="md"
                title="Delete matter"
                className="ml-auto"
              />
            )}
          </div>
        </GlassCard>
      )}

      <ConfirmDialog
        open={confirmDelete && Boolean(selected)}
        title={`Delete matter “${selected?.title || ""}”?`}
        description="This permanently removes the legal matter and its documents. This can’t be undone."
        confirmLabel="Delete matter"
        busy={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={deleteMatter}
        testId="delete-legal-confirm"
      />

      {adding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && setAdding(false)} />
          <div className="relative w-full max-w-md rounded-md border border-helm-line bg-helm-card p-5 space-y-3" data-testid="legal-create-modal">
            <div className="flex items-center justify-between">
              <p className="text-sm text-helm-fg font-medium">New legal matter</p>
              <button type="button" onClick={() => setAdding(false)} className="text-helm-muted hover:text-helm-fg">
                <X className="w-4 h-4" />
              </button>
            </div>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Title</span>
              <input
                data-testid="legal-new-title"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="NDA: Acme Supplier"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                autoFocus
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Type</span>
              <select
                data-testid="legal-new-type"
                value={form.matter_type}
                onChange={(e) => setForm((f) => ({ ...f, matter_type: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              >
                {(data?.matter_types || ["contract", "compliance", "other"]).map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Due date</span>
              <input
                type="date"
                data-testid="legal-new-due-date"
                value={form.due_date}
                onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Counterparty</span>
              <input
                data-testid="legal-new-counterparty"
                value={form.counterparty}
                onChange={async (e) => {
                  const value = e.target.value;
                  setForm((f) => ({ ...f, counterparty: value }));
                  const q = value.trim();
                  if (q.length < 1) {
                    setCounterpartySuggestions([]);
                    return;
                  }
                  try {
                    const { data: res } = await api.get("/legal/counterparty-suggestions", { params: { q } });
                    setCounterpartySuggestions(res?.suggestions || []);
                  } catch {
                    setCounterpartySuggestions([]);
                  }
                }}
                placeholder="Vendor, customer, or other party"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                autoComplete="off"
              />
            </label>
            {counterpartySuggestions.length > 0 && (
              <div className="space-y-1" data-testid="legal-counterparty-suggestions">
                {counterpartySuggestions.map((s) => (
                  <button
                    key={s.counterparty}
                    type="button"
                    data-testid={`legal-counterparty-suggestion-${s.counterparty}`}
                    onClick={() => {
                      setForm((f) => ({ ...f, counterparty: s.counterparty }));
                      setCounterpartySuggestions([]);
                    }}
                    className="w-full text-left rounded-md border border-helm-line px-3 py-1.5 text-xs text-helm-fg hover:bg-helm-fg/[0.04]"
                  >
                    <span className="font-medium">{s.counterparty}</span>
                    <span className="text-helm-muted"> · {s.matter_count} · last {s.last_matter_date || "—"}</span>
                  </button>
                ))}
              </div>
            )}
            {form.matter_type === "compliance" && (
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Recurrence</span>
                <select
                  data-testid="legal-new-recurrence"
                  value={form.recurrence}
                  onChange={(e) => setForm((f) => ({ ...f, recurrence: e.target.value }))}
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                >
                  <option value="">One-off</option>
                  {(data?.recurrence_options || ["annual", "quarterly", "monthly"]).map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </label>
            )}
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Assignee</span>
              <select
                data-testid="legal-new-assignee"
                value={form.assigned_to}
                onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))}
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
              >
                <option value="">Me (default)</option>
                {workspaceMembers.map((m) => (
                  <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Notes</span>
              <textarea
                data-testid="legal-new-notes"
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
                data-testid="legal-create-submit"
                onClick={createMatter}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-50"
              >
                Create matter
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
