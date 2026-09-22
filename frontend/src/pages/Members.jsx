import { useEffect, useState } from "react";
import { toast } from "sonner";
import { UserPlus, User, Mail, Copy, Link2, Shield, Check } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, GlassCard, SectionLabel, ErrorScreen, SkeletonCardList } from "@/components/kit";
import { ASSIGNABLE_PACKS, packMeta, hasPerm } from "@/lib/access";
import { formatDepartmentNames } from "@/lib/departments";
import { cn } from "@/lib/utils";

export default function Members() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useFetch("/members");
  const canInvite = hasPerm(user, "members:invite");
  const canManageOwners = hasPerm(user, "members:manage");
  const { data: codeData } = useFetch(canInvite ? "/workspaces/join-code" : null);
  const { data: accessData, reload: reloadAccess } = useFetch(canManageOwners ? "/access/sections" : null);

  const [tab, setTab] = useState("team");
  const [email, setEmail] = useState("");
  const [pack, setPack] = useState("member");
  const [busy, setBusy] = useState(false);
  /** Draft: membership_id → section_id[] (only CEO-editable grants, not pack/dept). */
  const [grantsDraft, setGrantsDraft] = useState(null);
  /** Draft: membership_id → department_id[] for enabled department lanes. */
  const [deptsDraft, setDeptsDraft] = useState(null);
  const [accessBusy, setAccessBusy] = useState(false);

  useEffect(() => {
    setGrantsDraft(null);
    setDeptsDraft(null);
  }, [accessData]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Team & Access" subtitle="Invite teammates with access packs. They also appear on the People roster." />
        <SkeletonCardList count={4} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load team"
        message={fetchErrorMessage(error, "Team data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  const packOptions = ASSIGNABLE_PACKS;
  const sections = accessData?.sections || [];
  const accessMembers = accessData?.members || [];
  const enabledDepartments = accessData?.enabled_departments || [];

  const draftFor = (membershipId, member) => {
    if (grantsDraft && Object.prototype.hasOwnProperty.call(grantsDraft, membershipId)) {
      return grantsDraft[membershipId];
    }
    return member?.section_grants || [];
  };

  const deptsFor = (membershipId, member) => {
    if (deptsDraft && Object.prototype.hasOwnProperty.call(deptsDraft, membershipId)) {
      return deptsDraft[membershipId];
    }
    return member?.department_ids || [];
  };

  const toggleGrant = (membershipId, sectionId, member) => {
    const current = draftFor(membershipId, member);
    const next = current.includes(sectionId)
      ? current.filter((id) => id !== sectionId)
      : [...current, sectionId];
    setGrantsDraft({ ...(grantsDraft || {}), [membershipId]: next });
  };

  const toggleDept = (membershipId, departmentId, member) => {
    if (!member?.user_id) {
      toast.error("They need to accept the invite before you can add department lanes");
      return;
    }
    const current = deptsFor(membershipId, member);
    const next = current.includes(departmentId)
      ? current.filter((id) => id !== departmentId)
      : [...current, departmentId];
    setDeptsDraft({ ...(deptsDraft || {}), [membershipId]: next });
  };

  const saveAccess = async () => {
    if (!grantsDraft && !deptsDraft) return;
    setAccessBusy(true);
    try {
      if (grantsDraft) {
        await api.patch("/access/member-grants", { grants: grantsDraft });
      }
      if (deptsDraft) {
        await api.patch("/access/member-departments", { assignments: deptsDraft });
      }
      toast.success("Member access saved");
      setGrantsDraft(null);
      setDeptsDraft(null);
      reloadAccess();
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally {
      setAccessBusy(false);
    }
  };

  const invite = async () => {
    if (!email.trim()) return;
    setBusy(true);
    try {
      const { data: res } = await api.post("/members/invite", { email: email.trim(), pack });
      toast.success(res.auto_joined ? "Member added instantly" : res.email_sent ? "Invitation email sent" : "Invitation created");
      setEmail("");
      reload();
      reloadAccess();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not invite");
    } finally {
      setBusy(false);
    }
  };

  const changePack = async (m, newPack) => {
    try {
      await api.patch(`/members/${m.membership_id}`, { pack: newPack });
      reload();
      reloadAccess();
      toast.success("Access updated");
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const remove = async (m) => {
    const label = m.name || m.email || "this member";
    if (!window.confirm(`Remove ${label} from this workspace?`)) return;
    try {
      await api.delete(`/members/${m.membership_id}`);
      reload();
      reloadAccess();
      toast.success("Member removed. They stay on People as roster-only until you remove them there.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const copyCode = () => {
    if (codeData?.join_code) { navigator.clipboard?.writeText(codeData.join_code); toast.success("Invite code copied"); }
  };

  return (
    <div className="max-w-3xl">
      <PageHeader title="Team & Access" subtitle="Invite teammates with access packs. They also appear on the People roster." />

      {canManageOwners && (
        <div className="flex gap-1 mb-6 p-1 rounded-lg border border-helm-line bg-helm-fg/[0.02] w-fit">
          {[{ id: "team", label: "Team" }, { id: "access", label: "Manage Access" }].map((t) => (
            <button key={t.id} type="button" data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
              className={cn("px-4 py-2 text-sm rounded-md transition-colors", tab === t.id ? "bg-helm-gold/12 text-helm-gold" : "text-helm-muted hover:text-helm-fg")}>
              {t.label}
            </button>
          ))}
        </div>
      )}

      {tab === "access" && canManageOwners && (
        <GlassCard className="p-5 mb-6 fade-up" data-testid="manage-access-panel">
          <div className="flex items-center gap-2 mb-2 text-helm-gold">
            <Shield className="w-4 h-4" />
            <SectionLabel>Member section &amp; department access</SectionLabel>
          </div>
          <p className="text-sm text-helm-muted mb-5">
            Gold means they can open that area. Items marked “via pack” come with their access pack and stay on.
            Toggle other product sections for extra access, and toggle department lanes (Production, HR, and so on)
            so they appear in that teammate&apos;s sidebar. Owners always have full access and are not listed here.
          </p>

          {!accessData ? (
            <p className="text-sm text-helm-muted">Loading access…</p>
          ) : accessMembers.length === 0 ? (
            <p className="text-sm text-helm-muted" data-testid="access-empty">No team members to manage yet. Invite someone from the Team tab.</p>
          ) : (
            <div className="space-y-6">
              {accessMembers.map((member) => {
                const meta = packMeta(member.pack);
                const grants = draftFor(member.membership_id, member);
                const fromPack = new Set(member.from_pack || []);
                const fromDept = new Set(member.from_department || []);
                const memberDepts = new Set(deptsFor(member.membership_id, member));
                return (
                  <div
                    key={member.membership_id}
                    className="border-b border-helm-line pb-5 last:border-0 last:pb-0"
                    data-testid={`access-member-${member.membership_id}`}
                  >
                    <div className="flex items-center gap-3 mb-3">
                      {member.picture ? (
                        <img src={member.picture} alt="" className="w-8 h-8 rounded-full object-cover border border-helm-line" />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-helm-fg/5 border border-helm-line flex items-center justify-center">
                          <User className="w-3.5 h-3.5 text-helm-muted" />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-helm-fg truncate">{member.name || member.email}</p>
                        <p className="text-xs text-helm-muted truncate">{member.email} · {formatDepartmentNames(member)}</p>
                      </div>
                      <span className={cn("inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wide rounded px-2 py-1 border shrink-0", meta.style)}>
                        <meta.icon className="w-3 h-3" />{meta.label}
                      </span>
                    </div>
                    <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-helm-muted mb-2">Product sections</p>
                    <div className="flex flex-wrap gap-2">
                      {sections.map((section) => {
                        const packLocked = fromPack.has(section.id);
                        const deptLocked = fromDept.has(section.id);
                        const granted = grants.includes(section.id);
                        const on = packLocked || deptLocked || granted;
                        if (packLocked || deptLocked) {
                          return (
                            <span
                              key={section.id}
                              title={
                                packLocked
                                  ? `Included with their ${meta.label} pack, so they already have access`
                                  : `Included via their ${member.legacy_department || "department"} access rule`
                              }
                              data-testid={`access-${member.membership_id}-${section.id}-${packLocked ? "pack" : "dept"}`}
                              className="inline-flex items-center gap-1.5 text-xs rounded-md px-2.5 py-1 border border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
                            >
                              <Check className="w-3 h-3" />
                              {section.label}
                              <span className="text-[10px] font-mono uppercase tracking-wide text-helm-gold/70">
                                {packLocked ? "via pack" : "via dept"}
                              </span>
                            </span>
                          );
                        }
                        return (
                          <button
                            key={section.id}
                            type="button"
                            title={section.description}
                            data-testid={`access-${member.membership_id}-${section.id}`}
                            onClick={() => toggleGrant(member.membership_id, section.id, member)}
                            className={cn(
                              "inline-flex items-center gap-1 text-xs rounded-md px-2.5 py-1 border transition-colors",
                              on ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold" : "border-helm-line text-helm-muted hover:border-helm-fg/20",
                            )}
                          >
                            {on ? <Check className="w-3 h-3" /> : null}
                            {section.label}
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-helm-muted mt-4 mb-2">Department lanes</p>
                    {enabledDepartments.length === 0 ? (
                      <p className="text-xs text-helm-muted" data-testid={`access-depts-none-${member.membership_id}`}>
                        No departments enabled yet. Turn them on under Settings → Departments.
                      </p>
                    ) : !member.user_id ? (
                      <p className="text-xs text-helm-muted" data-testid={`access-depts-pending-${member.membership_id}`}>
                        Waiting for them to accept the invite before department lanes can be assigned.
                      </p>
                    ) : (
                      <div className="flex flex-wrap gap-2" data-testid={`access-depts-${member.membership_id}`}>
                        {enabledDepartments.map((dept) => {
                          const on = memberDepts.has(dept.department_id);
                          return (
                            <button
                              key={dept.department_id}
                              type="button"
                              title={`Add or remove ${dept.name} from their sidebar`}
                              data-testid={`access-dept-${member.membership_id}-${dept.type}`}
                              onClick={() => toggleDept(member.membership_id, dept.department_id, member)}
                              className={cn(
                                "inline-flex items-center gap-1 text-xs rounded-md px-2.5 py-1 border transition-colors",
                                on ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold" : "border-helm-line text-helm-muted hover:border-helm-fg/20",
                              )}
                            >
                              {on ? <Check className="w-3 h-3" /> : null}
                              {dept.name}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {accessMembers.length > 0 && (
            <button
              data-testid="save-access-btn"
              onClick={saveAccess}
              disabled={accessBusy || (!grantsDraft && !deptsDraft)}
              className="mt-5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
            >
              {accessBusy ? "Saving…" : "Save access"}
            </button>
          )}
        </GlassCard>
      )}

      {tab === "team" && (
        <>
          {canInvite && (
            <GlassCard className="p-5 mb-4 fade-up">
              <div className="flex items-center gap-1.5 mb-3 text-helm-gold">
                <UserPlus className="w-4 h-4" />
                <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Invite a teammate</span>
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <div className="flex items-center gap-2 flex-1 rounded-md border border-helm-line bg-helm-card px-3 focus-within:border-helm-gold/35">
                  <Mail className="w-4 h-4 text-helm-muted" />
                  <input data-testid="invite-email-input" value={email} onChange={(e) => setEmail(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && invite()} placeholder="teammate@company.com"
                    className="flex-1 bg-transparent text-helm-fg text-sm placeholder:text-helm-muted focus:outline-none py-2.5" />
                </div>
                <select data-testid="invite-pack-select" value={pack} onChange={(e) => setPack(e.target.value)}
                  className="rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/40">
                  {packOptions.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
                <button data-testid="invite-submit-btn" onClick={invite} disabled={busy}
                  className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60">
                  {busy ? "Inviting…" : "Invite"}
                </button>
              </div>
              <p className="text-xs text-helm-muted mt-2.5" data-testid="pack-desc">{packMeta(pack).label}: {packMeta(pack).desc}</p>
            </GlassCard>
          )}

          {canInvite && codeData?.join_code && (
            <GlassCard className="p-4 mb-6 fade-up flex items-center gap-3" data-testid="join-code-card">
              <Link2 className="w-4 h-4 text-helm-gold shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-helm-muted">Open invite code. Share to let anyone join as a Member</p>
                <p className="font-mono text-lg text-helm-fg tracking-[0.3em] mt-0.5" data-testid="join-code-value">{codeData.join_code}</p>
              </div>
              <button data-testid="copy-join-code" onClick={copyCode} className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5"><Copy className="w-3.5 h-3.5" /> Copy</button>
            </GlassCard>
          )}

          <div className="space-y-2">
            {data.members.map((m) => {
              const meta = packMeta(m.pack || m.role);
              const targetIsOwner = (m.pack || m.role) === "owner";
              const canEditThis = canInvite && !m.is_self && (!targetIsOwner || canManageOwners);
              return (
                <GlassCard key={m.membership_id} className="p-4 fade-up" data-testid={`member-row-${m.email}`}>
                  <div className="flex items-center gap-3 flex-wrap">
                    {m.picture ? (
                      <img src={m.picture} alt="" className="w-9 h-9 rounded-full object-cover border border-helm-line" />
                    ) : (
                      <div className="w-9 h-9 rounded-full bg-helm-fg/5 border border-helm-line flex items-center justify-center">
                        <User className="w-4 h-4 text-helm-muted" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm text-helm-fg truncate">{m.name || m.email}</p>
                        {m.is_self && <span className="text-[10px] text-helm-muted">(you)</span>}
                      </div>
                      <p className="text-xs text-helm-muted truncate">{m.email} · {formatDepartmentNames(m)}</p>
                    </div>
                    {m.status === "invited" && (
                      <span className="text-[10px] font-mono uppercase tracking-wide text-helm-fg bg-helm-status-warning/12 rounded px-2 py-1">Invited</span>
                    )}
                    <span className={cn("inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wide rounded px-2 py-1 border", meta.style)}>
                      <meta.icon className="w-3 h-3" />{meta.label}
                    </span>
                    {canEditThis && (
                      <div className="flex items-center gap-1 flex-wrap">
                        <select value={targetIsOwner ? "owner" : (m.pack || m.role)} onChange={(e) => changePack(m, e.target.value)}
                          data-testid={`pack-select-${m.email}`}
                          className="text-[11px] text-helm-fg bg-helm-card border border-helm-line rounded px-2 py-1 focus:outline-none focus:border-helm-gold/40">
                          {targetIsOwner && <option value="owner" disabled>Owner</option>}
                          {ASSIGNABLE_PACKS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                        </select>
                        {canManageOwners && (
                          <CirDeleteBtn onClick={() => remove(m)} data-testid={`remove-${m.email}`} title="Remove member" />
                        )}
                      </div>
                    )}
                  </div>
                </GlassCard>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
