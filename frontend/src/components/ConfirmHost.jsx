import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

/**
 * Promise-based replacement for window.confirm, rendered in Trenston's own
 * styling. Mount <ConfirmHost /> once at the app root, then:
 *
 *   if (!(await confirmAction({ title: "Delete this event?" }))) return;
 */
let listener = null;

export function confirmAction({
  title,
  description = "",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
} = {}) {
  if (!listener) {
    // Host not mounted (e.g. an isolated test render): fail closed.
    return Promise.resolve(false);
  }
  return new Promise((resolve) => {
    listener({ title, description, confirmLabel, cancelLabel, destructive, resolve });
  });
}

export default function ConfirmHost() {
  const [req, setReq] = useState(null);
  const confirmRef = useRef(null);

  useEffect(() => {
    listener = (next) => {
      setReq((prev) => {
        prev?.resolve(false);
        return next;
      });
    };
    return () => { listener = null; };
  }, []);

  useEffect(() => {
    if (!req) return undefined;
    confirmRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") close(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [req]);

  const close = (value) => {
    setReq((prev) => {
      prev?.resolve(value);
      return null;
    });
  };

  if (!req) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-host-title"
      data-testid="confirm-host"
    >
      <div className="absolute inset-0 bg-helm-ink/70" onClick={() => close(false)} aria-hidden="true" />
      <div className="relative w-full max-w-sm rounded-md border border-helm-line bg-helm-card p-5 shadow-xl">
        <p id="confirm-host-title" className="text-sm font-medium text-helm-fg">{req.title}</p>
        {req.description ? (
          <p className="mt-1.5 text-sm text-helm-muted leading-relaxed whitespace-pre-line">{req.description}</p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            data-testid="confirm-host-cancel"
            onClick={() => close(false)}
            className="rounded-md border border-helm-line px-3 py-2 text-sm text-helm-fg hover:bg-helm-fg/[0.04]"
          >
            {req.cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            data-testid="confirm-host-confirm"
            onClick={() => close(true)}
            className={cn(
              "rounded-md px-3 py-2 text-sm font-medium",
              req.destructive
                ? "border border-helm-status-negative/35 bg-helm-status-negative/12 text-helm-status-negative hover:bg-helm-status-negative/20"
                : "bg-helm-gold text-helm-navy hover:bg-helm-gold-hover",
            )}
          >
            {req.confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
