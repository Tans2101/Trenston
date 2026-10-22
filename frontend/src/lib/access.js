// Central access-pack metadata — mirrors PACK_PERMS/PACK_LABEL in backend/server.py.
import { Crown, LineChart, DollarSign, Users2, Briefcase, Wrench, Shield } from "lucide-react";

export const PACKS = [
  { id: "owner", label: "Owner", icon: Crown, style: "text-helm-gold bg-helm-gold/10 border-helm-gold/20", desc: "Full control: runs the company, billing & access." },
  { id: "exec", label: "Executive", icon: LineChart, style: "text-helm-navy bg-helm-gold/15 border-helm-gold/30", desc: "Sees everything, including Financials and every department. Can decide, invite teammates, and manage reports. Does not edit the books or billing." },
  { id: "finance", label: "Finance", icon: DollarSign, style: "text-helm-status-positive bg-helm-status-positive/10 border-helm-status-positive/20", desc: "Everything a Member gets, plus sees and edits Financials." },
  { id: "hr", label: "People / HR", icon: Users2, style: "text-helm-muted bg-helm-muted/10 border-helm-muted/20", desc: "Everything a Member gets, plus edits the People roster and leads the HR department." },
  { id: "sales", label: "Sales", icon: Briefcase, style: "text-helm-status-warning bg-helm-status-warning/10 border-helm-status-warning/20", desc: "Everything a Member gets, plus updates the sales pipeline." },
  { id: "ops", label: "Operations", icon: Wrench, style: "text-helm-navy bg-helm-navy/10 border-helm-navy/20", desc: "Everything a Member gets, plus updates ops work and Metrics." },
  { id: "member", label: "Member", icon: Shield, style: "text-helm-fg bg-helm-fg/5 border-helm-line", desc: "Sees company pages, works their own tasks and posts a status update. Departments and Financials are shared separately." },
];

/** Packs that can be granted via invite or role edit. Owner/CEO is never assignable. */
export const ASSIGNABLE_PACKS = PACKS.filter((p) => p.id !== "owner");

export const packMeta = (id) => PACKS.find((p) => p.id === id) || PACKS[PACKS.length - 1];
/**
 * Leaders (owner, executive, or anyone whose landing page is the company view)
 * get the company briefing on Home; everyone else gets their own day.
 */
export function isLeader(user) {
  if (!user) return false;
  return user.role === "owner" || user.pack === "owner" || user.pack === "exec";
}

export const hasPerm = (user, perm) => Array.isArray(user?.perms) && user.perms.includes(perm);

/** Who can open Billing / fix past-due — owners always, or anyone with billing:manage. */
export function canManageBilling(user) {
  if (!user) return false;
  if (user.role === "owner" || user.pack === "owner") return true;
  return hasPerm(user, "billing:manage");
}

/**
 * Sections a pack can open without a write perm (mirrors backend FINANCIALS_VIEW_PACKS).
 * Manage Access must treat these as pack-locked so toggling does not escalate to edit.
 */
export const VIEW_SECTIONS_BY_PACK = {
  exec: ["financials"],
};

/** Pack + dept + grant union for Manage Access display (view-via-pack included). */
export function packLockedSections(member) {
  const fromPack = member?.from_pack || [];
  const viewViaPack = VIEW_SECTIONS_BY_PACK[member?.pack] || [];
  return new Set([...fromPack, ...viewViaPack]);
}
