import { Trash2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Danger confirm card — Uiverse Yaya12085 (grumpy-fox-39), adapted for Trenston.
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
  icon = "alert",
  confirmHint,
  confirmValue = "",
  onConfirmValueChange,
  confirmPlaceholder,
  showConfirm = false,
  busy = false,
  disabled = false,
  onAction,
  onCancel,
  className,
  actionTestId,
  cancelTestId,
  inputTestId,
}) {
  const Icon = icon === "trash" ? Trash2 : AlertTriangle;
  const locked = busy || disabled;
  const primaryLabel = busy
    ? busyLabel
    : showConfirm
      ? (confirmingLabel || confirmLabel)
      : confirmLabel;

  return (
    <div
      id={id}
      className={cn("cir-danger scroll-mt-24", className)}
      data-testid={id || "cir-danger"}
    >
      <div className="cir-danger__header">
        <div className="cir-danger__image" aria-hidden>
          <Icon strokeWidth={1.75} />
        </div>
        <div className="cir-danger__content">
          <h3 className="cir-danger__title">{title}</h3>
          <p className="cir-danger__message">{message}</p>
        </div>
      </div>

      {showConfirm ? (
        <div className="cir-danger__confirm">
          <label className="cir-danger__label" htmlFor={inputTestId || `${id || "cir-danger"}-confirm`}>
            {confirmHint ? (
              <>
                Type <span className="cir-danger__exact">{confirmHint}</span> to confirm
              </>
            ) : (
              "Type the confirmation value to continue"
            )}
          </label>
          <input
            id={inputTestId || `${id || "cir-danger"}-confirm`}
            data-testid={inputTestId}
            value={confirmValue}
            onChange={(e) => onConfirmValueChange?.(e.target.value)}
            disabled={locked}
            className="cir-danger__input"
            placeholder={confirmPlaceholder || confirmHint || ""}
            autoComplete="off"
          />
        </div>
      ) : null}

      <div className="cir-danger__actions">
        <button
          type="button"
          data-testid={actionTestId}
          onClick={onAction}
          disabled={locked}
          className="cir-danger__desactivate"
        >
          {primaryLabel}
        </button>
        <button
          type="button"
          data-testid={cancelTestId}
          onClick={onCancel}
          disabled={locked}
          className="cir-danger__cancel"
        >
          {cancelLabel}
        </button>
      </div>
    </div>
  );
}
