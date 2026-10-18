import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Check, X, PenLine, ArrowUpRight, Waves, MoreHorizontal, UserRound, Trash2, ChevronDown } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, apiErrorMessage } from "@/lib/api";
import { signalRoute, taskHref } from "@/lib/signalRoute";
import { cn } from "@/lib/utils";

/** Match chart hover/exit timing (heatmap inactive tween). */
const LIST_MOTION = { duration: 0.22, ease: [0.4, 0, 0.2, 1] };

const statusStyle = {
  pending: "text-helm-fg bg-helm-status-warning/12 border-helm-status-warning/35",
  approved: "text-helm-fg bg-helm-status-positive/12 border-helm-status-positive/35",
  rejected: "text-helm-status-negative bg-helm-status-negative/12 border-helm-status-negative/35",
  delegated: "text-helm-fg bg-helm-muted/12 border-helm-muted/35",
};

/** Impact as a small dot: yellow for High, ink for Medium, hollow for Low. */
export function ImpactDot({ impact }) {
  const level = String(impact || "").toLowerCase();
  return (
    <span
      aria-label={`${impact || "Unknown"} impact`}
      title={`${impact || "Unknown"} impact`}
      className={cn(
        "mt-[7px] h-2 w-2 shrink-0 rounded-full",
        level === "high" ? "dec-dot-high" : level === "medium" ? "bg-helm-fg/60" : "border border-helm-fg/40",
      )}
    />
  );
}

function ConfidenceBadge({ confidence, confidenceUnavailable, ai }) {
  if (confidenceUnavailable || (ai && (confidence == null || confidence === ""))) {
    return <span className="ml-auto shrink-0 font-mono text-xs text-helm-muted">confidence unavailable</span>;
  }
  if (confidence == null || confidence === "") return null;
  return (
    <span className="ml-auto shrink-0 font-mono text-xs text-helm-muted tabular-nums">
      {confidence}%{ai ? " AI estimate" : ""}
    </span>
  );
}

/** One quiet line of facts under a title, separated by dots. Empty parts are left out. */
export function MetaLine({ parts, className }) {
  const shown = parts.filter(Boolean);
  if (!shown.length) return null;
  return (
    <p className={cn("mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px] text-helm-muted", className)}>
      {shown.map((p, i) => (
        <span key={i} className="inline-flex items-center gap-2">
          {i > 0 && <span aria-hidden className="text-helm-fg/25">·</span>}
          {p}
        </span>
      ))}
    </p>
  );
}

const hasDue = (due) => due && due !== "—" && due !== "-";

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
  selfOptionLabel,
  onEdit,
  onDelete,
  ripple = null,
  onRipple = null,
}) {
  const isAi = d.source === "ai_suggested";
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [followUpBusy, setFollowUpBusy] = useState(false);
  const source = signalRoute(d.signal);
  const isBusy = busy === d.id || busy === true;
  const hasDetail = Boolean(d.description || d.recommendation || source?.to || onRipple);

  const createFollowUp = async () => {
    if (followUpBusy) return;
    setFollowUpBusy(true);
    try {
      const res = await api.post("/tasks", { title: `Follow up: ${d.title || "decision"}`.slice(0, 200), tag: "Decision", column: "backlog" });
      const taskId = res?.data?.task?.id;
      toast.success("Follow-up task created", taskId
        ? { action: { label: "Open task", onClick: () => navigate(taskHref(taskId)) } }
        : undefined);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(detail == null ? "Could not create the follow-up task" : apiErrorMessage(detail, "Could not create the follow-up task"));
    } finally {
      setFollowUpBusy(false);
    }
  };

  const handleApprove = async () => {
    const ok = await onApprove?.(d.id);
    if (ok === false) return;
    // Same toast id as the action hook, so this replaces "Decision approved".
    toast.success("Decision approved", {
      id: `decision-${d.id}`,
      action: { label: "Create follow-up task", onClick: createFollowUp },
    });
  };

  const handleDelegate = async (owner) => {
    if (!owner) return;
    await onDelegate?.(d.id, owner);
  };

  const people = [
    ...(selfMember ? [{ key: "self", value: selfLabel, label: selfOptionLabel || (selfLabel ? `Me – ${selfLabel}` : "Me") }] : []),
    ...delegateMembers.map((m) => ({ key: m.membership_id, value: m.name || m.email, label: m.name || m.email })),
  ];

  const meta = [
    d.category && d.category !== "General" ? d.category : null,
    hasDue(d.due) ? `Due ${d.due}` : null,
    d.impact ? `${d.impact} impact` : null,
    d.owner ? `Owner: ${d.owner}` : null,
    isAi ? "From Trenston" : null,
    d.status && d.status !== "pending" ? <span className="capitalize">{d.status}</span> : null,
    ripple?.label ? (
      <span className={cn(ripple.tone === "worse" ? "text-helm-status-negative" : ripple.tone === "better" ? "text-helm-status-positive" : "")}>
        {ripple.label}
      </span>
    ) : null,
  ];

  return (
    <motion.div
      layout
      initial={false}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, height: 0, overflow: "hidden" }}
      transition={LIST_MOTION}
      className="dec-row border-b border-helm-line"
      data-testid={`decision-${d.id}`}
      data-deeplink={d.id}
    >
      <div className="flex items-start gap-3 px-1 py-4 sm:px-3">
        <ImpactDot impact={d.impact} />
        <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => hasDetail && setOpen((v) => !v)}
            aria-expanded={hasDetail ? open : undefined}
            className="group flex w-full items-start gap-2 text-left"
            data-testid={`decision-toggle-${d.id}`}
          >
            <h3 className="text-[15px] font-medium leading-snug tracking-tight text-helm-fg">{d.title}</h3>
            {hasDetail && (
              <ChevronDown className={cn("mt-1 h-3.5 w-3.5 shrink-0 text-helm-muted opacity-0 transition group-hover:opacity-100", open && "rotate-180 opacity-100")} aria-hidden />
            )}
          </button>
          <MetaLine parts={meta} />
          {d.recommendation && !open && (
            <p className="mt-1.5 line-clamp-1 text-[13px] text-helm-fg/80">
              <span className="text-helm-muted">{isAi ? "Trenston suggests: " : "Leaning: "}</span>
              {d.recommendation}
            </p>
          )}

          {open && (
            <div className="mt-3 space-y-3 border-l border-helm-line pl-4">
              {d.description && <p className="text-sm leading-relaxed text-helm-muted">{d.description}</p>}
              {d.recommendation && (
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-helm-muted">
                      {isAi ? "Trenston recommendation" : "Recommendation"}
                    </span>
                    <ConfidenceBadge confidence={d.confidence} confidenceUnavailable={d.confidence_unavailable} ai={isAi} />
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-helm-fg">{d.recommendation}</p>
                  {d.confidence != null && d.confidence !== "" && !d.confidence_unavailable && (
                    <div className="mt-2 h-[3px] w-40 bg-helm-line">
                      <div className="h-[3px] bg-helm-fg" style={{ width: `${d.confidence}%` }} />
                    </div>
                  )}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                {onRipple && (
                  <button
                    type="button"
                    onClick={() => onRipple(d)}
                    data-testid={`ripple-${d.id}`}
                    className="inline-flex items-center gap-1.5 text-[13px] font-medium text-helm-fg hover:underline underline-offset-4"
                  >
                    <Waves className="h-3.5 w-3.5" aria-hidden />
                    {ripple?.label ? "Change the ripple" : "See the ripple"}
                  </button>
                )}
                {source?.to && (
                  <Link
                    to={source.to}
                    data-testid={`decision-source-${d.id}`}
                    className="inline-flex items-center gap-1 text-[13px] font-medium text-helm-fg hover:underline underline-offset-4"
                  >
                    {source.label || "View source"} <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {canAct ? (
            <>
              <button
                type="button"
                data-testid={`approve-${d.id}`}
                disabled={isBusy}
                onClick={handleApprove}
                className="app-btn-primary inline-flex h-8 items-center gap-1.5 px-3 text-[13px] font-medium disabled:opacity-50"
              >
                <Check className="h-3.5 w-3.5" /> Approve
              </button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    disabled={isBusy}
                    aria-label={`More actions for ${d.title}`}
                    data-testid={`decision-more-${d.id}`}
                    className="inline-flex h-8 w-8 items-center justify-center text-helm-muted hover:bg-helm-fg/5 hover:text-helm-fg disabled:opacity-50"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52">
                  <DropdownMenuSub>
                    <DropdownMenuSubTrigger data-testid={`delegate-${d.id}`} disabled={!people.length}>
                      <UserRound className="h-4 w-4" /> Delegate to
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent className="max-h-72 overflow-y-auto">
                      {people.map((p) => (
                        <DropdownMenuItem key={p.key} onSelect={() => handleDelegate(p.value)} data-testid={`delegate-${d.id}-${p.key}`}>
                          {p.label}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>
                  <DropdownMenuItem onSelect={() => onReject(d.id)} data-testid={`reject-${d.id}`}>
                    <X className="h-4 w-4" /> Reject
                  </DropdownMenuItem>
                  {onRipple && (
                    <DropdownMenuItem onSelect={() => onRipple(d)}>
                      <Waves className="h-4 w-4" /> See the ripple
                    </DropdownMenuItem>
                  )}
                  {(onEdit || onDelete) && <DropdownMenuSeparator />}
                  {onEdit && (
                    <DropdownMenuItem onSelect={() => onEdit(d)} data-testid={`edit-decision-${d.id}`}>
                      <PenLine className="h-4 w-4" /> Edit
                    </DropdownMenuItem>
                  )}
                  {onDelete && (
                    <DropdownMenuItem onSelect={() => onDelete(d.id)} data-testid={`del-decision-${d.id}`} className="text-helm-status-negative focus:text-helm-status-negative">
                      <Trash2 className="h-4 w-4" /> Delete
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          ) : (
            <p className="text-xs leading-relaxed text-helm-muted sm:max-w-[10rem] sm:text-right">Only owners and executives can act on decisions.</p>
          )}
        </div>
        </div>
      </div>
    </motion.div>
  );
}

export { statusStyle, ConfidenceBadge };
