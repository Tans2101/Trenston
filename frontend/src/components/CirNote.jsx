import { Sparkles, X } from "lucide-react";
import { toast } from "@/lib/notify";
import { cn } from "@/lib/utils";

/**
 * cir-note toast — Uiverse-style cloud card for draft / action notifications.
 */
export function CirNoteCard({
  title,
  description,
  actionLabel = "Open",
  onAction,
  onClose,
  icon,
  className,
}) {
  return (
    <div className={cn("cir-note", className)} data-testid="cir-note" role="status">
      <div className="cir-note__ico" aria-hidden>
        {icon || <Sparkles strokeWidth={1.75} />}
      </div>
      <div className="cir-note__body">
        <p className="cir-note__t">{title}</p>
        {description ? <p className="cir-note__d">{description}</p> : null}
      </div>
      <div className="cir-note__act">
        {onAction && actionLabel ? (
          <button type="button" className="cir-note__btn" onClick={onAction} data-testid="cir-note-action">
            {actionLabel}
          </button>
        ) : null}
        <button
          type="button"
          className="cir-note__close"
          aria-label="Dismiss"
          onClick={onClose}
          data-testid="cir-note-dismiss"
        >
          <X strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}

/**
 * Show a cir-note via sonner (custom JSX toast, unstyled chrome).
 */
export function toastCirNote({
  title,
  description,
  actionLabel = "Open",
  onAction,
  duration = 12000,
  id,
} = {}) {
  const toastId = id || `cir-note-${Date.now()}`;
  return toast.custom(
    (t) => (
      <CirNoteCard
        title={title}
        description={description}
        actionLabel={actionLabel}
        onAction={() => {
          onAction?.();
          toast.dismiss(t);
        }}
        onClose={() => toast.dismiss(t)}
      />
    ),
    {
      id: toastId,
      duration,
      unstyled: true,
      className: "cir-note-toast",
    },
  );
}

/** Gmail AI draft ready — primary action opens the Gmail draft URL. */
export function toastGmailDraftNote({ recipient, url, subject } = {}) {
  const who = (recipient || "").trim() || "your contact";
  const title = `Reply drafted for ${who}`;
  // Honest product copy: drafts are short and style-matched; Trenston never sends.
  const description = subject
    ? `Short draft ready in Gmail · ${subject}`
    : "Short tone-matched draft ready in Gmail. Trenston did not send it.";
  return toastCirNote({
    id: `gmail-draft-${Date.now()}`,
    title,
    description,
    actionLabel: "Open",
    onAction: () => {
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    },
  });
}
