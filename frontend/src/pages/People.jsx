import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, PenLine, Trash2, X, AlertTriangle } from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, SkeletonKPIRow, SkeletonCardList } from "@/components/kit";
import { formatDepartmentNames } from "@/lib/departments";
import { ASSIGNABLE_PACKS, hasPerm } from "@/lib/access";
import { cn } from "@/lib/utils";

const emptyForm = () => ({
  name: "",
  role: "",
  inviteToAccess: false,
  email: "",
  pack: "member",
});

const HR_STATUS_LABEL = {
  active: "Active",
  on_leave: "On leave",
  departed: "Departed",
};

function formatHrMonth(iso) {
  if (!iso) return null;
  const raw = String(iso).slice(0, 10);
  const d = new Date(`${raw}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
}

function hrSecondaryLine(p) {
  if (!p.hr_status) return null;
  const status = HR_STATUS_LABEL[p.hr_status] || p.hr_status;
  const since = formatHrMonth(p.hr_start_date);
  const parts = [];
  if (since) parts.push(`${status} since ${since}`);
  else parts.push(status);
  if (p.hr_manager_name) parts.push(`reports to ${p.hr_manager_name}`);
  return parts.join(" · ");
}

function sortRoster(people) {
  return [...(people || [])].sort((a, b) => {
    const accessDelta = Number(Boolean(b.has_access)) - Number(Boolean(a.has_access));
    if (accessDelta) return accessDelta;
    return String(a.name || "").localeCompare(String(b.name || ""));
  });
}

export default function People() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useFetch("/people");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const roster = useMemo(() => sortRoster(data?.people), [data?.people]);

  if (loading) {
    return (
      <div>
        <PageHeader title="People" subtitle="Your team roster: who does what, and how headcount tracks over time." />
        <SkeletonKPIRow count={2} />
        <SkeletonCardList count={4} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load roster"
        message={fetchErrorMessage(error, "People data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }
  const canWrite = data.can_write;
  const canInvite = data.can_invite_to_access || hasPerm(user, "members:invite");
  const packOptions = ASSIGNABLE_PACKS;
  const editingPerson = editing ? (data.people || []).find((p) => p.id === editing) : null;
  const assignedDeptCount = new Set((data.people || []).flatMap((p) => p.departments || [])).size;
  const unassignedCount = Number(data.unassigned_count) || 0;

  const openAdd = () => { setEditing(null); setForm(emptyForm()); setShowForm(true); };
  const openEdit = (p) => {
    setEditing(p.id);
    setForm({
      name: p.name,
      role: p.role,
      inviteToAccess: false,
      email: p.email || "",
      pack: "member",
    });
    setShowForm(true);
  };

  const submit = async () => {
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    if (!editing && form.inviteToAccess) {
      if (!form.email.trim()) { toast.error("Email is required to include in Team & Access"); return; }
    }
    setBusy(true);
    const payload = { name: form.name.trim(), role: form.role.trim() };
    if (!editing && form.inviteToAccess) {
      payload.invite_to_access = true;
      payload.email = form.email.trim();
      payload.pack = form.pack;
    }
    try {
      if (editing) {
        await api.patch(`/people/${editing}`, payload);
        toast.success("Person updated");
      } else {
        const { data: res } = await api.post("/people", payload);
        if (form.inviteToAccess) {
          toast.success(res.auto_joined ? "Added to roster and Team & Access" : res.email_sent ? "Added and invitation emailed" : "Added and invited to Team & Access");
        } else {
          toast.success("Person added. Headcount synced");
        }
      }
      setShowForm(false);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save"); }
    finally { setBusy(false); }
  };

  const del = async (p) => {
    // Always ask the API — client has_access can be stale after Team & Access removal.
    // Backend blocks only when an active/invited membership still exists.
    if (p.has_access) {
      if (!window.confirm(
        `${p.name} still shows Team & Access login. If you already removed them there, continue to remove them from the People roster. Otherwise cancel and remove them from Team & Access first.`,
      )) return;
    } else if (!window.confirm(`Remove ${p.name} from the roster?`)) {
      return;
    }
    try {
      await api.delete(`/people/${p.id}`);
      reload();
      toast.success("Person removed. Headcount synced");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    }
  };

  const action = canWrite ? (
    <button data-testid="add-person-btn" onClick={openAdd}
      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 transition-colors hover:bg-helm-gold-hover">
      <Plus className="w-4 h-4" /> Add person
    </button>
  ) : null;

  if (data.people.length === 0) {
    return (
      <div>
        <PageHeader title="People" subtitle="Your team roster, linked with Team & Access for anyone who can log in." action={action} />
        <EmptyState title="No people yet" body="Add your team here. Invites from Team & Access show up automatically."
          action={canWrite ? <button data-testid="empty-add-person-btn" onClick={openAdd} className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"><Plus className="w-4 h-4" /> Add first person</button> : null} />
        {showForm && <PersonForm {...{ form, setForm, submit, busy, editing, person: editingPerson, close: () => setShowForm(false), canInvite, packOptions }} />}
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="People" subtitle="Your team roster: who does what, and how headcount tracks over time." action={action} />

      <div className="grid grid-cols-2 gap-4 mb-6">
        <GlassCard className="p-5 fade-up">
          <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">Headcount</p>
          <p className="font-mono text-3xl text-helm-fg mt-2" data-testid="people-headcount">{data.people.length}</p>
        </GlassCard>
        <GlassCard className="p-5 fade-up">
          <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">Departments</p>
          <p className="font-mono text-3xl text-helm-fg mt-2" data-testid="people-dept-count">{assignedDeptCount}</p>
        </GlassCard>
      </div>

      {unassignedCount > 0 && (
        <div
          className="mb-6 flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-helm-status-warning/40 bg-helm-status-warning/10 px-4 py-3 fade-up"
          data-testid="people-unassigned-callout"
        >
          <AlertTriangle className="w-4 h-4 text-helm-status-warning shrink-0" />
          <p className="text-sm text-helm-fg flex-1">
            {unassignedCount === 1
              ? "1 person has no department, so their work won't show up anywhere in Trenston."
              : `${unassignedCount} people have no department, so their work won't show up anywhere in Trenston.`}
          </p>
          <Link
            to="/app/settings#manage-departments"
            className="text-sm font-medium text-helm-gold hover:underline shrink-0"
            data-testid="people-unassigned-fix"
          >
            Assign in Settings
          </Link>
        </div>
      )}

      <SectionLabel className="mb-4">Roster</SectionLabel>
      <div className="grid md:grid-cols-2 gap-3">
        {roster.map((p) => {
          const hrLine = hrSecondaryLine(p);
          const departed = p.hr_status === "departed";
          const openCount = Number(p.open_item_count) || 0;
          const overdueCount = Number(p.overdue_item_count) || 0;
          const showWorkload = Boolean(p.user_id);
          return (
            <GlassCard
              key={p.id}
              className={cn(
                "p-4 fade-up transition-transform hover:-translate-y-0.5 group",
                departed && "opacity-70",
              )}
              data-testid={`person-${p.id}`}
            >
              <div className="flex items-center gap-4">
                <div
                  className={cn(
                    "w-11 h-11 rounded-full flex items-center justify-center shrink-0 text-sm font-medium",
                    p.has_access
                      ? "bg-helm-gold/12 border border-helm-gold/35 text-helm-gold"
                      : "bg-transparent border border-dashed border-helm-muted/50 text-helm-muted",
                  )}
                  title={p.has_access ? "Has Trenston login" : "Roster only, no login"}
                  data-testid={`person-avatar-${p.id}`}
                >
                  {p.name.split(" ").map((n) => n[0]).join("").slice(0, 2)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className={cn("text-helm-fg text-sm", departed && "line-through text-helm-muted")}>{p.name}</p>
                    {p.has_access && (
                      <span className="text-[10px] uppercase tracking-wider text-helm-muted border border-helm-line px-1.5 py-0.5 rounded" data-testid={`person-access-${p.id}`}>
                        Team & Access
                      </span>
                    )}
                    {!p.has_access && (
                      <span className="text-[10px] uppercase tracking-wider text-helm-muted/80" data-testid={`person-roster-only-${p.id}`}>
                        Roster only
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-helm-muted" data-testid={`person-depts-${p.id}`}>
                    {p.role || "—"} · {formatDepartmentNames(p)}
                  </p>
                  {hrLine && (
                    <p className="text-xs text-helm-muted mt-0.5" data-testid={`person-hr-${p.id}`}>
                      {hrLine}
                      {p.hr_employee_id && (
                        <>
                          {" · "}
                          <Link
                            to={`/app/departments/hr?employee=${encodeURIComponent(p.hr_employee_id)}`}
                            className="text-helm-gold hover:underline"
                          >
                            View in HR
                          </Link>
                        </>
                      )}
                    </p>
                  )}
                  {showWorkload && (
                    <p
                      className={cn(
                        "text-[11px] font-mono mt-1",
                        overdueCount > 0 ? "text-helm-status-warning" : "text-helm-muted",
                      )}
                      data-testid={`person-workload-${p.id}`}
                    >
                      {openCount} open{overdueCount > 0 ? ` · ${overdueCount} overdue` : ""}
                    </p>
                  )}
                </div>
                {canWrite && (
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => openEdit(p)} data-testid={`edit-person-${p.id}`} className="text-helm-muted hover:text-helm-gold p-1"><PenLine className="w-3.5 h-3.5" /></button>
                    <button onClick={() => del(p)} data-testid={`del-person-${p.id}`} className="text-helm-muted hover:text-helm-status-negative p-1" title={p.has_access ? "Has Team & Access login — remove there first, or confirm to try roster remove" : "Remove"}><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                )}
              </div>
            </GlassCard>
          );
        })}
      </div>

      {showForm && <PersonForm {...{ form, setForm, submit, busy, editing, person: editingPerson, close: () => setShowForm(false), canInvite, packOptions }} />}
    </div>
  );
}

function PersonForm({ form, setForm, submit, busy, editing, person, close, canInvite, packOptions }) {
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
      <div className="absolute inset-0 bg-helm-ink/70" onClick={close} />
      <GlassCard className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="person-form">
        <div className="flex items-center justify-between mb-5"><h3 className="text-lg text-helm-fg font-light">{editing ? "Edit person" : "Add a person"}</h3><button onClick={close} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button></div>
        <div className="grid grid-cols-2 gap-3">
          <label className="col-span-2 text-xs text-helm-muted">Name
            <input data-testid="person-name" value={form.name} onChange={set("name")} placeholder="Jane Doe" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
          </label>
          <label className="col-span-2 text-xs text-helm-muted">Role
            <input data-testid="person-role" value={form.role} onChange={set("role")} placeholder="Engineer" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
          </label>
          <div className="col-span-2 text-xs text-helm-muted">
            <p className="uppercase tracking-wide text-[10px] text-helm-muted mb-1">Departments</p>
            <p className="text-sm text-helm-fg" data-testid="person-depts-readonly">
              {editing ? formatDepartmentNames(person) : "Unassigned"}
            </p>
            <p className="mt-1 text-helm-muted">
              Assign access in{" "}
              <Link to="/app/members" className="text-helm-gold hover:underline">Team & Access</Link>
              {" "}→ department membership, not from this roster field.
            </p>
          </div>
          {!editing && canInvite && (
            <div className="col-span-2 mt-1 space-y-3 border-t border-helm-line pt-3">
              <label className="flex items-start gap-2 text-sm text-helm-fg cursor-pointer">
                <input
                  type="checkbox"
                  data-testid="person-invite-access"
                  checked={form.inviteToAccess}
                  onChange={(e) => setForm((f) => ({ ...f, inviteToAccess: e.target.checked }))}
                  className="mt-1 rounded border-helm-fg/20 bg-helm-card"
                />
                <span>
                  Also include in Team & Access
                  <span className="block text-xs text-helm-muted mt-0.5">Sends a login invite so they can sign in.</span>
                </span>
              </label>
              {form.inviteToAccess && (
                <>
                  <label className="block text-xs text-helm-muted">Email
                    <input
                      data-testid="person-email"
                      type="email"
                      value={form.email}
                      onChange={set("email")}
                      placeholder="alex@company.com"
                      className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                    />
                  </label>
                  <label className="block text-xs text-helm-muted">Access pack
                    <select
                      data-testid="person-pack"
                      value={form.pack}
                      onChange={set("pack")}
                      className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                    >
                      {packOptions.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                    </select>
                  </label>
                </>
              )}
            </div>
          )}
        </div>
        <button data-testid="submit-person-btn" onClick={submit} disabled={busy} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm transition-colors hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : editing ? "Save changes" : form.inviteToAccess ? "Add & invite" : "Add person"}</button>
      </GlassCard>
    </div>
  );
}
