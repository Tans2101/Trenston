import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

/** Shared approve / reject / delegate / suggestion actions for Decisions + My Day. */
export function useDecisionActions(reload) {
  const [busy, setBusy] = useState(null);

  const act = async (id, action, owner) => {
    setBusy(id);
    try {
      await api.post(`/decisions/${id}/action`, { action, owner });
      reload?.();
      if (action === "delegated" && owner) {
        toast.success(`Assigned to ${owner}`);
      } else {
        toast.success(`Decision ${action}`);
      }
    } catch (e) {
      toast.error("Action failed");
    } finally {
      setBusy(null);
    }
  };

  const approveSuggestion = async (id) => {
    setBusy(id);
    try {
      await api.post(`/decisions/suggestions/${id}/approve`);
      toast.success("Suggestion accepted. It is now a pending decision");
      reload?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not approve");
    } finally {
      setBusy(null);
    }
  };

  const dismissSuggestion = async (id) => {
    setBusy(id);
    try {
      await api.post(`/decisions/suggestions/${id}/dismiss`);
      toast.success("Suggestion dismissed");
      reload?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not dismiss");
    } finally {
      setBusy(null);
    }
  };

  return { busy, act, approveSuggestion, dismissSuggestion };
}

/** Build delegate dropdown lists from GET /members payload. */
export function buildDelegateOptions(membersData) {
  const allMembers = membersData?.members || [];
  const selfMember = allMembers.find((m) => m.is_self);
  const seenUsers = new Set();
  const delegateMembers = [];
  for (const m of allMembers) {
    if (m.is_self) continue;
    if (m.status === "invited" && !m.user_id) continue;
    const key = m.user_id || m.email;
    if (!key || seenUsers.has(key)) continue;
    seenUsers.add(key);
    delegateMembers.push(m);
  }
  const selfName = selfMember?.name || selfMember?.email || "Myself";
  // Stored owner value stays the real name/email so existing decisions keep matching.
  const selfLabel = selfName;
  const selfOptionLabel = selfName && selfName !== "Myself" ? `Me – ${selfName}` : "Me";
  return { selfMember, delegateMembers, selfLabel, selfOptionLabel };
}

/** True when owner label is the current user (Myself / name / email). */
export function decisionOwnerIsSelf(owner, selfLabel) {
  const o = (owner || "").trim().toLowerCase();
  if (!o) return false;
  if (o === "myself" || o === "me") return true;
  const me = (selfLabel || "").trim().toLowerCase();
  return !!me && o === me;
}

/**
 * Open decisions stay actionable. "Delegated to myself" is ownership, not a
 * final resolution — keep those in the open list so approve/reject still work.
 */
export function isOpenDecision(d, selfLabel) {
  if (!d) return false;
  if (d.status === "pending") return true;
  return d.status === "delegated" && decisionOwnerIsSelf(d.owner, selfLabel);
}
