import { Check, X, Sparkles, PenLine } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { motion, useReducedMotion } from "motion/react";
import { GlassCard } from "@/components/kit";
import { cn } from "@/lib/utils";

/** Match chart hover/exit timing (heatmap inactive tween). */
const LIST_MOTION = { duration: 0.22, ease: [0.4, 0, 0.2, 1] };

const statusStyle = {
  pending: "text-helm-fg bg-helm-status-warning/12 border-helm-status-warning/35",
  approved: "text-helm-fg bg-helm-status-positive/12 border-helm-status-positive/35",
  rejected: "text-helm-status-negative bg-helm-status-negative/12 border-helm-status-negative/35",
  delegated: "text-helm-fg bg-helm-muted/12 border-helm-muted/35",
};

function ConfidenceBadge({ confidence, confidenceUnavailable, ai }) {
  if (confidenceUnavailable || (ai && (confidence == null || confidence === ""))) {
    return (
      <span className={cn("ml-auto font-mono text-xs", ai ? "text-helm-status-warning" : "text-helm-muted")}>
        confidence unavailable
      </span>
    );
  }
  if (confidence == null || confidence === "") return null;
  return (
    <span className={cn("ml-auto font-mono text-xs", ai ? "text-helm-status-warning" : "text-helm-gold")}>
      {confidence}%{ai ? " AI estimate" : " confidence"}
    </span>
  );
}

export default function DecisionCard({
  d,
  canAct,
  busy,
  onApprove,
  onReject,
  onDelegate,
  delegateMembers = [],
  selfMember,
  selfLabel,
  onEdit,
  onDelete,
}) {
  const isAi = d.source === "ai_suggested";
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      layout
      initial={false}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, height: 0, marginBottom: 0, overflow: "hidden" }}
      transition={LIST_MOTION}
      className="overflow-hidden"
    >
    <GlassCard className="p-5 fade-up" data-testid={`decision-${d.id}`}>
      <div className="flex flex-col lg:flex-row lg:items-start gap-5">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="text-[10px] font-mono uppercase tracking-wider text-helm-muted border border-helm-line rounded px-1.5 py-0.5">{d.category}</span>
            <span className={cn("text-[10px] font-mono uppercase tracking-wider rounded px-1.5 py-0.5 border", statusStyle[d.status])}>{d.status}</span>
            {isAi && (
              <span className="text-[10px] font-mono uppercase tracking-wider text-helm-status-warning/90 border border-helm-status-warning/35 rounded px-1.5 py-0.5">
                From Trenston
              </span>
            )}
            <span className="text-[10px] font-mono text-helm-muted">Impact: {d.impact} · Due {d.due}</span>
            {d.owner && (
              <span className="text-[10px] font-mono text-helm-muted">Owner: {d.owner}</span>
            )}
            {canAct && (onEdit || onDelete) && (
              <span className="ml-auto flex items-center gap-1">
                {onEdit && (
                  <button onClick={() => onEdit(d)} data-testid={`edit-decision-${d.id}`} className="text-helm-muted hover:text-helm-gold p-1"><PenLine className="w-3.5 h-3.5" /></button>
                )}
                {onDelete && (
                  <CirDeleteBtn onClick={() => onDelete(d.id)} data-testid={`del-decision-${d.id}`} title="Delete decision" />
                )}
              </span>
            )}
          </div>
          <h3 className="text-lg text-helm-fg font-medium tracking-tight">{d.title}</h3>
          {d.description && <p className="text-sm text-helm-muted mt-1">{d.description}</p>}

          {d.recommendation && (
            <div className={cn(
              "mt-4 rounded-lg border border-helm-line bg-helm-card p-3 border-l-2",
              isAi ? "border-l-helm-status-warning/70" : "border-l-helm-gold/70",
            )}>
              <div className="flex items-center gap-1.5 mb-1.5">
                <Sparkles className={cn("w-3.5 h-3.5", isAi ? "text-helm-status-warning" : "text-helm-gold")} />
                <span className={cn("text-[11px] font-mono uppercase tracking-wider", isAi ? "text-helm-status-warning" : "text-helm-gold")}>
                  {isAi ? "Trenston recommendation" : "Recommendation"}
                </span>
                <ConfidenceBadge
                  confidence={d.confidence}
                  confidenceUnavailable={d.confidence_unavailable}
                  ai={isAi}
                />
              </div>
              <p className="text-sm text-helm-fg leading-relaxed">{d.recommendation}</p>
              {d.confidence != null && !d.confidence_unavailable && (
                <div className="mt-2 h-1 rounded-full bg-helm-fg/5 overflow-hidden">
                  <div className={cn("h-full rounded-full", isAi ? "bg-helm-status-warning/70" : "bg-helm-gold")} style={{ width: `${d.confidence}%` }} />
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex lg:flex-col gap-2 lg:w-40">
          {canAct ? (
            <>
              <button data-testid={`approve-${d.id}`} disabled={busy === d.id} onClick={() => onApprove(d.id)} className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-helm-gold text-helm-navy text-sm font-medium py-2 transition-colors hover:bg-helm-gold-hover disabled:opacity-50"><Check className="w-4 h-4" /> Approve</button>
              <select data-testid={`delegate-${d.id}`} disabled={busy === d.id} defaultValue="" onChange={(e) => e.target.value && onDelegate(d.id, e.target.value)} className="flex-1 rounded-md border border-helm-line text-helm-fg text-sm py-2 px-2 bg-helm-card transition-colors hover:bg-helm-fg/5 focus:outline-none focus:border-helm-gold/40 disabled:opacity-50">
                <option value="">Delegate to…</option>
                {selfMember && (
                  <option value={selfLabel}>Myself</option>
                )}
                {delegateMembers.map((m) => (
                  <option key={m.membership_id} value={m.name || m.email}>{m.name || m.email}</option>
                ))}
              </select>
              <button data-testid={`reject-${d.id}`} disabled={busy === d.id} onClick={() => onReject(d.id)} className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md border border-helm-line text-helm-muted text-sm py-2 transition-colors hover:bg-helm-fg/5 hover:text-helm-status-negative disabled:opacity-50"><X className="w-4 h-4" /> Reject</button>
            </>
          ) : (
            <p className="text-xs text-helm-muted lg:w-40 leading-relaxed">Only owners and executives can act on decisions.</p>
          )}
        </div>
      </div>
    </GlassCard>
    </motion.div>
  );
}

export { statusStyle, ConfidenceBadge };
