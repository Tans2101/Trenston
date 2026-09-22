import { Trash2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Danger confirm card — Uiverse-style (Yaya12085), adapted for Trenston.
 * Use for irreversible deletes (account, workspace, etc.).
 */
export default function DangerConfirmCard({
  id,
  title,
  message,
  confirmLabel = "Delete",
  confirmingLabel,
  cancelLabel = "Cancel",
  busyLabel = "Deleting…",
  icon = "trash",
  confirmHint,
  confirmValue = "",
  onConfirmValueChange,
  confirmPlaceholder,
  showConfirm = false,
  busy = false,
  onAction,
  onCancel,
  className,
  actionTestId,
  cancelTestId,
  inputTestId,
}) {
  const Icon = icon === "alert" ? AlertTriangle : Trash2;
  const primaryLabel = busy
    ? busyLabel
    : showConfirm
      ? (confirmingLabel || `Confirm ${confirmLabel.toLowerCase()}`)
      : confirmLabel;

  return (
    <div
      id={id}
      className={cn("cir-danger scroll-mt-24", className)}
      data-testid={id || "cir-danger"}
    >
      <div className="cir-danger__header">
        <div className="cir-danger__image" aria-hidden>
          <Icon />
        </div>
        <div className="cir-danger__content">
          <h3 className="cir-danger__title">{title}</h3>
          <p className="cir-danger__message">{message}</p>
        </div>
      </div>

      {showConfirm && confirmHint ? (
        <div className="cir-danger__confirm">
          <label className="cir-danger__label">
            Type <span className="cir-danger__exact">{confirmHint}</span> to confirm
          </label>
          <input
            data-testid={inputTestId}
            value={confirmValue}
            onChange={(e) => onConfirmValueChange?.(e.target.value)}
            disabled={busy}
            className="cir-danger__input"
            placeholder={confirmPlaceholder || confirmHint}
          />
        </div>
      ) : null}

      <div className="cir-danger__actions">
        <button
          type="button"
          data-testid={actionTestId}
          onClick={onAction}
          disabled={busy}
          className="cir-danger__desactivate"
        >
          {primaryLabel}
        </button>
        {showConfirm ? (
          <button
            type="button"
            data-testid={cancelTestId}
            onClick={onCancel}
            disabled={busy}
            className="cir-danger__cancel"
          >
            {cancelLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
