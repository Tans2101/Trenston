// Central access-pack metadata — mirrors PACK_PERMS/PACK_LABEL in backend/server.py.
import { Crown, LineChart, DollarSign, Users2, Briefcase, Wrench, Shield } from "lucide-react";

export const PACKS = [
  { id: "owner", label: "Owner", icon: Crown, style: "text-helm-gold bg-helm-gold/10 border-helm-gold/20", desc: "Full control: runs the company, billing & access." },
  { id: "exec", label: "Executive", icon: LineChart, style: "text-helm-navy bg-helm-gold/15 border-helm-gold/30", desc: "Full read + can decide, invite teammates, and manage manual reports." },
  { id: "finance", label: "Finance", icon: DollarSign, style: "text-helm-status-positive bg-helm-status-positive/10 border-helm-status-positive/20", desc: "Reads everything, writes financials." },
  { id: "hr", label: "People / HR", icon: Users2, style: "text-helm-muted bg-helm-muted/10 border-helm-muted/20", desc: "Reads everything, manages the roster & headcount." },
  { id: "sales", label: "Sales", icon: Briefcase, style: "text-helm-status-warning bg-helm-status-warning/10 border-helm-status-warning/20", desc: "Reads everything and can update the sales pipeline." },
  { id: "ops", label: "Operations", icon: Wrench, style: "text-helm-navy bg-helm-navy/10 border-helm-navy/20", desc: "Reads everything and can update ops work and Telemetry." },
  { id: "member", label: "Member", icon: Shield, style: "text-helm-fg bg-helm-fg/5 border-helm-line", desc: "Read access + works their own tasks and posts a status update." },
];

/** Packs that can be granted via invite or role edit. Owner/CEO is never assignable. */
export const ASSIGNABLE_PACKS = PACKS.filter((p) => p.id !== "owner");

export const packMeta = (id) => PACKS.find((p) => p.id === id) || PACKS[PACKS.length - 1];
export const hasPerm = (user, perm) => Array.isArray(user?.perms) && user.perms.includes(perm);

/** Who can open Billing / fix past-due — owners always, or anyone with billing:manage. */
export function canManageBilling(user) {
  if (!user) return false;
  if (user.role === "owner" || user.pack === "owner") return true;
  return hasPerm(user, "billing:manage");
}
