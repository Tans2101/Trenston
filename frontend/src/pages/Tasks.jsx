import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { GripVertical, Plus, X } from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, ErrorScreen, EmptyState, SkeletonCardList } from "@/components/kit";
import { cn } from "@/lib/utils";
import { buildAssigneeOptions } from "@/lib/assigneeOptions";

const priorityStyle = {
  High: "text-helm-status-negative bg-helm-status-negative/12",
  Medium: "text-helm-fg bg-helm-status-warning/12",
  Low: "text-helm-muted bg-helm-fg/5",
};

const emptyTask = () => ({ title: "", priority: "Medium", tag: "General", due: "", assignee_user_id: "" });

export default function Tasks() {
  const { data, loading, error, reload, setData } = useFetch("/tasks");
  const { data: membersData } = useFetch("/members");
  const [searchParams] = useSearchParams();
  const focusTaskId = searchParams.get("task") || "";
  const [dragId, setDragId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyTask());
  const [busy, setBusy] = useState(false);
  const [clearingDone, setClearingDone] = useState(false);

  useEffect(() => {
    if (!focusTaskId || !data?.items?.length) return;
    const el = document.querySelector(`[data-testid="task-${focusTaskId}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusTaskId, data?.items]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Tasks" subtitle="Delegate, track and sync work across your team. Drag cards across the board. Your tasks are marked in gold." />
        <div className="grid md:grid-cols-3 gap-4">
          <SkeletonCardList count={3} />
          <SkeletonCardList count={2} />
          <SkeletonCardList count={2} />
        </div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load board"
        message={fetchErrorMessage(error, "Task board is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  const canCreate = data.can_create;
  const canAssign = data.can_assign;
  const taskAssigneeOptions = buildAssigneeOptions(membersData?.members || [], data.my_user_id, {
    selfUsesId: false,
  });

  const move = async (taskId, column) => {
    let snapshot = null;
    setData((prev) => {
      if (!prev) return prev;
      snapshot = prev;
      return {
        ...prev,
        items: prev.items.map((t) => (t.id === taskId ? { ...t, column } : t)),
      };
    });
    try {
      await api.patch(`/tasks/${taskId}`, { column });
    } catch (e) {
      if (snapshot) setData(snapshot);
      toast.error(e?.response?.data?.detail || "Failed to move task");
    }
  };

  const onDrop = (col) => {
    if (dragId) { move(dragId, col); setDragId(null); }
  };

  const clearDone = async () => {
    if (clearingDone) return;
    setClearingDone(true);
    let snapshot = null;
    setData((prev) => {
      if (!prev) return prev;
      snapshot = prev;
      return {
        ...prev,
        items: prev.items.filter((t) => {
          if (t.column !== "done") return true;
          if (prev.can_assign) return false;
          if (!t.assignee_user_id || t.assignee_user_id === prev.my_user_id) return false;
          return true;
        }),
      };
    });
    try {
      const res = await api.delete("/tasks/done");
      const n = res?.data?.cleared ?? 0;
      if (n === 0) {
        if (snapshot) setData(snapshot);
        toast.message("No finished tasks to clear");
      } else {
        toast.success(n === 1 ? "Cleared 1 finished task" : `Cleared ${n} finished tasks`);
        reload();
      }
    } catch (e) {
      if (snapshot) setData(snapshot);
      toast.error(e?.response?.data?.detail || "Could not clear finished tasks");
    } finally {
      setClearingDone(false);
    }
  };

  const submit = async () => {
    if (!form.title.trim()) { toast.error("Add a title"); return; }
    setBusy(true);
    try {
      const payload = { title: form.title.trim(), priority: form.priority, tag: form.tag, due: form.due };
      if (canAssign && form.assignee_user_id) payload.assignee_user_id = form.assignee_user_id;
      await api.post("/tasks", payload);
      toast.success("Task created");
      setForm(emptyTask());
      setShowForm(false);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not create"); }
    finally { setBusy(false); }
  };

  const action = canCreate ? (
    <button data-testid="new-task-btn" onClick={() => { setForm(emptyTask()); setShowForm(true); }}
      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 transition-colors hover:bg-helm-gold-hover">
      <Plus className="w-4 h-4" /> New task
    </button>
  ) : null;

  const board = (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      {data.columns.map((col) => {
        const items = data.items.filter((t) => t.column === col.id);
        return (
          <div key={col.id}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => onDrop(col.id)}
            data-testid={`column-${col.id}`}
            className="rounded-xl border border-helm-line bg-helm-fg/[0.015] p-3 min-h-[200px]">
            <div className="flex items-center justify-between gap-2 px-1 mb-3">
              <span className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">{col.name}</span>
              <div className="flex items-center gap-2">
                {col.id === "done" && items.length > 0 && (
                  <button
                    type="button"
                    data-testid="clear-done-tasks-btn"
                    onClick={clearDone}
                    disabled={clearingDone}
                    className="text-[10px] font-medium text-helm-muted hover:text-helm-fg transition-colors disabled:opacity-60"
                  >
                    {clearingDone ? "Clearing…" : "Clear finished tasks"}
                  </button>
                )}
                <span className="font-mono text-xs text-helm-muted">{items.length}</span>
              </div>
            </div>
            <div className="space-y-2">
              {items.map((t) => {
                const mine = t.assignee_user_id === data.my_user_id;
                return (
                <div key={t.id}
                  draggable
                  onDragStart={() => setDragId(t.id)}
                  data-testid={`task-${t.id}`}
                  className={cn(
                    "group rounded-lg border border-helm-line bg-helm-card p-3 cursor-grab active:cursor-grabbing transition-colors hover:border-helm-gold/35",
                    mine && "border-l-2 border-l-helm-gold/60",
                    focusTaskId === t.id && "ring-1 ring-helm-gold/35 border-helm-gold/35",
                  )}>
                  <div className="flex items-start gap-2">
                    <GripVertical className="w-3.5 h-3.5 text-helm-muted mt-0.5 group-hover:text-helm-muted" />
                    <div className="flex-1">
                      <p className="text-sm text-helm-fg leading-snug">{t.title}</p>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        <span className={cn("text-[10px] font-mono uppercase tracking-wide rounded px-1.5 py-0.5", priorityStyle[t.priority])}>{t.priority}</span>
                        <span className="text-[10px] font-mono text-helm-muted">{t.tag}</span>
                        {t.due && <span className="text-[10px] font-mono text-helm-muted ml-auto">{t.due}</span>}
                      </div>
                      {t.progress > 0 && t.progress < 100 && (
                        <div className="mt-2 h-1 rounded-full bg-helm-fg/5 overflow-hidden">
                          <div className="h-full bg-helm-gold/70 rounded-full" style={{ width: `${t.progress}%` }} />
                        </div>
                      )}
                      <div className="flex items-center gap-1.5 mt-2">
                        <span className="w-4 h-4 rounded-full bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center text-[9px] text-helm-gold">{(t.assignee || "?")[0]}</span>
                        <span className="text-[11px] text-helm-muted">{t.assignee}{mine && " · you"}</span>
                      </div>
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );

  return (
    <div>
      <PageHeader title="Tasks" subtitle="Delegate, track and sync work across your team. Drag cards across the board. Your tasks are marked in gold." action={action} />
      {data.items.length === 0 ? (
        <EmptyState title="No tasks yet" body="Create the first task, or assign work to a teammate."
          action={canCreate ? <button data-testid="empty-new-task-btn" onClick={() => { setForm(emptyTask()); setShowForm(true); }} className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"><Plus className="w-4 h-4" /> New task</button> : null} />
      ) : board}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setShowForm(false)} />
          <GlassCard className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="task-form">
            <div className="flex items-center justify-between mb-5"><h3 className="text-lg text-helm-fg font-light">New task</h3><button onClick={() => setShowForm(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button></div>
            <label className="text-xs text-helm-muted block">Title
              <input data-testid="task-title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="What needs doing?" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
            </label>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <label className="text-xs text-helm-muted">Priority
                <select data-testid="task-priority" value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40">
                  {["High", "Medium", "Low"].map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              <label className="text-xs text-helm-muted">Due date
                <input data-testid="task-due" type="date" value={form.due} onChange={(e) => setForm((f) => ({ ...f, due: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <label className="text-xs text-helm-muted col-span-2">Tag
                <input data-testid="task-tag" value={form.tag} onChange={(e) => setForm((f) => ({ ...f, tag: e.target.value }))} placeholder="Growth" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              {canAssign && (
                <label className="text-xs text-helm-muted col-span-2">Assign to
                  <select data-testid="task-assignee" value={form.assignee_user_id} onChange={(e) => setForm((f) => ({ ...f, assignee_user_id: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40">
                    {taskAssigneeOptions.map((o) => (
                      <option key={o.user_id || `task-${o.label}`} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            <button data-testid="save-task-btn" onClick={submit} disabled={busy} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm transition-colors hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Creating…" : "Create task"}</button>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
