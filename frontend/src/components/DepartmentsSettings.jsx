import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Building2, UserPlus, User } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useDepartmentsQuery } from "@/hooks/useDepartmentsQuery";
import { api } from "@/lib/api";
import { GlassCard, SectionLabel, ErrorScreen, SkeletonCardList } from "@/components/kit";
import { departmentIcon } from "@/lib/departmentIcons";
import { departmentPath } from "@/lib/departmentRoutes";

/**
 * Manage departments — visible to every workspace member.
 * Enable / disable / member assignment only when GET /departments says can_manage (CEO).
 */
export default function DepartmentsSettings() {
  const { data, loading, error, reload } = useDepartmentsQuery();
  const { data: membersData } = useFetch("/members");
  const [busyType, setBusyType] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [addUserId, setAddUserId] = useState("");
  const [addRole, setAddRole] = useState("member");
  const [memberBusy, setMemberBusy] = useState(false);
  const [roster, setRoster] = useState({});

  useEffect(() => {
    setRoster({});
  }, [data]);

  useEffect(() => {
    if (window.location.hash === "#manage-departments") {
      document.getElementById("manage-departments")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [loading]);

  if (loading) {
    return (
      <div>
        <SkeletonCardList count={4} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load departments"
        message={fetchErrorMessage(error, "Department settings are unavailable.")}
        onRetry={reload}
      />
    );
  }

  const canManage = Boolean(data.can_manage || data.is_ceo);
  const departments = data.departments || [];
  const workspaceMembers = (membersData?.members || []).filter((m) => m.user_id && m.status === "active");

  const loadMembers = async (departmentId) => {
    try {
      const { data: res } = await api.get(`/departments/${departmentId}/members`);
      setRoster((r) => ({ ...r, [departmentId]: res.members || [] }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load members");
    }
  };

  const toggleExpand = async (dept) => {
    if (!dept.enabled || !dept.department_id) return;
    const next = expanded === dept.department_id ? null : dept.department_id;
    setExpanded(next);
    setAddUserId("");
    setAddRole("member");
    if (next && !roster[next]) await loadMembers(next);
  };

  const enableDept = async (dept) => {
    setBusyType(dept.type);
    try {
      await api.post("/departments", { type: dept.type });
      toast.success(`${dept.name} enabled`);
      // Full navigation so AppLayout refetches /departments and the sidebar updates.
      window.location.assign(departmentPath(dept.type));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not enable department");
      setBusyType(null);
    }
  };

  const disableDept = async (dept) => {
    const ok = window.confirm(
      `Disable ${dept.name}?\n\nThis removes its department tools data (stages, requests, tickets, onboarding, etc.) for everyone. Pipeline deals and financial entries are kept.`,
    );
    if (!ok) return;
    setBusyType(dept.type);
    try {
      await api.delete(`/departments/${dept.department_id}`);
      toast.success(`${dept.name} disabled`);
      if (expanded === dept.department_id) setExpanded(null);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not disable department");
    } finally {
      setBusyType(null);
    }
  };

  const addMember = async (departmentId) => {
    if (!addUserId) {
      toast.error("Choose a teammate");
      return;
    }
    setMemberBusy(true);
    try {
      const { data: res } = await api.post(`/departments/${departmentId}/members`, {
        user_id: addUserId,
        role: addRole,
      });
      toast.success(res?.updated ? "Role updated" : "Member added");
      setAddUserId("");
      await loadMembers(departmentId);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not add member");
    } finally {
      setMemberBusy(false);
    }
  };

  const removeMember = async (departmentId, userId) => {
    setMemberBusy(true);
    try {
      await api.delete(`/departments/${departmentId}/members/${userId}`);
      toast.success("Member removed");
      await loadMembers(departmentId);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not remove member");
    } finally {
      setMemberBusy(false);
    }
  };

  return (
    <GlassCard id="manage-departments" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="departments-settings">
      <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
        <Building2 className="w-4 h-4" />
        <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Manage departments</span>
      </div>
      <p className="text-sm text-helm-muted mb-5 leading-relaxed">
        {canManage
          ? "Enable any department for your company, independent of industry, then assign teammates. Enabled departments appear in the sidebar."
          : "Departments enabled for this company. Only the CEO can turn additional departments on."}
      </p>

      <SectionLabel className="mb-3">All departments</SectionLabel>
      <div className="space-y-2 mb-2" data-testid="department-catalog">
        {departments.map((dept) => {
          const Icon = departmentIcon(dept.icon);
          const busy = busyType === dept.type;
          const onRoster = new Set((roster[dept.department_id] || []).map((m) => m.user_id));
          const availableMembers = workspaceMembers.filter(
            (m) => m.user_id && !onRoster.has(m.user_id),
          );
          return (
            <div
              key={dept.type}
              className="rounded-md border border-helm-line bg-helm-fg/[0.02] px-3 py-3"
              data-testid={`dept-row-${dept.type}`}
            >
              <div className="flex items-center gap-3">
                <Icon className="w-4 h-4 text-helm-muted shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-helm-fg truncate">{dept.name}</p>
                  <p className="text-[11px] text-helm-muted">
                    {dept.enabled ? (
                      <span className="text-helm-status-positive">Enabled</span>
                    ) : (
                      <span>Not enabled</span>
                    )}
                    {dept.enabled && dept.is_member ? " · You’re a member" : null}
                  </p>
                </div>

                {dept.enabled ? (
                  <div className="flex items-center gap-2 shrink-0">
                    <Link
                      to={departmentPath(dept.type)}
                      data-testid={`dept-open-${dept.type}`}
                      className="text-xs text-helm-gold hover:underline"
                    >
                      Open
                    </Link>
                    {canManage && (
                      <button
                        type="button"
                        data-testid={`dept-disable-${dept.type}`}
                        disabled={busy}
                        onClick={() => disableDept(dept)}
                        className="text-xs text-helm-muted hover:text-helm-status-negative transition-colors disabled:opacity-50"
                      >
                        {busy ? "…" : "Disable"}
                      </button>
                    )}
                  </div>
                ) : canManage ? (
                  <button
                    type="button"
                    data-testid={`dept-enable-${dept.type}`}
                    disabled={busy}
                    onClick={() => enableDept(dept)}
                    className="shrink-0 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-1.5 hover:bg-helm-gold-hover disabled:opacity-60"
                  >
                    {busy ? "Enabling…" : "Enable"}
                  </button>
                ) : (
                  <span className="text-[11px] font-mono uppercase tracking-wide text-helm-muted shrink-0">
                    Ask CEO
                  </span>
                )}
              </div>

              {canManage && dept.enabled && (
                <div className="mt-3 pt-3 border-t border-helm-line">
                  <button
                    type="button"
                    data-testid={`dept-manage-${dept.type}`}
                    onClick={() => toggleExpand(dept)}
                    className="text-xs text-helm-muted hover:text-helm-gold transition-colors"
                  >
                    {expanded === dept.department_id ? "Hide members" : "Manage members"}
                  </button>

                  {expanded === dept.department_id && (
                    <div className="mt-3 space-y-3" data-testid={`dept-members-${dept.type}`}>
                      {(roster[dept.department_id] || []).length === 0 ? (
                        <p className="text-xs text-helm-muted">No members yet.</p>
                      ) : (
                        <ul className="space-y-2">
                          {(roster[dept.department_id] || []).map((m) => (
                            <li key={m.user_id} className="flex items-center gap-2 text-sm">
                              {m.picture ? (
                                <img src={m.picture} alt="" className="w-6 h-6 rounded-full object-cover border border-helm-line" />
                              ) : (
                                <div className="w-6 h-6 rounded-full bg-helm-fg/5 border border-helm-line flex items-center justify-center">
                                  <User className="w-3 h-3 text-helm-muted" />
                                </div>
                              )}
                              <span className="flex-1 truncate text-helm-fg">{m.name || m.email}</span>
                              <span className="text-[10px] font-mono uppercase text-helm-muted">{m.role}</span>
                              <CirDeleteBtn
                                data-testid={`dept-remove-${dept.type}-${m.user_id}`}
                                disabled={memberBusy}
                                onClick={() => removeMember(dept.department_id, m.user_id)}
                                title="Remove"
                              />
                            </li>
                          ))}
                        </ul>
                      )}

                      <div className="flex flex-col sm:flex-row gap-2">
                        <select
                          data-testid={`dept-add-user-${dept.type}`}
                          value={addUserId}
                          onChange={(e) => setAddUserId(e.target.value)}
                          className="flex-1 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                        >
                          <option value="">
                            {availableMembers.length ? "Select teammate…" : "Everyone is already on this department"}
                          </option>
                          {availableMembers.map((m) => (
                            <option key={m.user_id} value={m.user_id}>
                              {m.name || m.email}
                            </option>
                          ))}
                        </select>
                        <select
                          data-testid={`dept-add-role-${dept.type}`}
                          value={addRole}
                          onChange={(e) => setAddRole(e.target.value)}
                          className="rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2"
                        >
                          <option value="member">Member</option>
                          <option value="lead">Lead</option>
                        </select>
                        <button
                          type="button"
                          data-testid={`dept-add-btn-${dept.type}`}
                          disabled={memberBusy || !availableMembers.length}
                          onClick={() => addMember(dept.department_id)}
                          className="inline-flex items-center justify-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover disabled:opacity-60"
                        >
                          <UserPlus className="w-3.5 h-3.5" /> Add
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}
