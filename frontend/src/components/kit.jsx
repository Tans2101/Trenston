import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import TrenstonMark from "@/components/HelmMark";

export function GlassCard({ className, children, glow, ...props }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-helm-line bg-helm-card shadow-sm",
        glow && "border-helm-gold/35",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between mb-8 fade-up">
      <div className="min-w-0">
        <h1 className="font-display text-3xl md:text-4xl font-normal tracking-tight text-helm-fg">{title}</h1>
        {subtitle && <p className="text-helm-muted text-sm mt-2 max-w-2xl font-sans">{subtitle}</p>}
      </div>
      {action ? <div className="shrink-0 sm:pt-1">{action}</div> : null}
    </div>
  );
}

export function PageHeaderSkeleton({ className }) {
  return (
    <div className={cn("mb-8 fade-up", className)} aria-hidden>
      <Skeleton className="h-9 w-48 md:w-64 max-w-[70%]" />
      <Skeleton className="h-4 w-full max-w-md mt-3" />
    </div>
  );
}

export function SkeletonKPIRow({ count = 4, className }) {
  return (
    <div
      className={cn(
        "grid gap-4 mb-6",
        count <= 2 ? "grid-cols-2" : "grid-cols-2 lg:grid-cols-4",
        className,
      )}
      aria-hidden
    >
      {Array.from({ length: count }, (_, i) => (
        <GlassCard key={i} className="p-4 fade-up">
          <Skeleton className="h-3 w-20 mb-3" />
          <Skeleton className="h-8 w-28" />
        </GlassCard>
      ))}
    </div>
  );
}

export function SkeletonCardList({ count = 3, className }) {
  return (
    <div className={cn("space-y-3", className)} aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <GlassCard key={i} className="p-4 fade-up">
          <Skeleton className="h-4 w-48 max-w-full mb-3" />
          <Skeleton className="h-3 w-full max-w-md mb-2" />
          <Skeleton className="h-3 w-40 max-w-full" />
        </GlassCard>
      ))}
    </div>
  );
}

export function SkeletonChart({ className }) {
  return (
    <GlassCard className={cn("p-5 fade-up", className)} aria-hidden>
      <Skeleton className="h-3 w-28 mb-4" />
      <Skeleton className="h-64 w-full" />
    </GlassCard>
  );
}

export function SectionLabel({ children, className }) {
  return (
    <h2 className={cn("font-display text-sm font-medium tracking-tight text-helm-fg", className)}>
      {children}
    </h2>
  );
}

const toneColor = {
  positive: "text-helm-status-positive",
  negative: "text-helm-status-negative",
  warning: "text-helm-status-warning",
  neutral: "text-helm-muted",
};

export function Delta({ value, tone, invert }) {
  // Hide until there is a real period-over-period change — bare "—" is meaningless.
  if (value === 0 || value === undefined || value === null) {
    return null;
  }
  const up = value > 0;
  const effectiveTone = tone || (up ? "positive" : "negative");
  return (
    <span className={cn("font-mono text-xs", toneColor[effectiveTone] || toneColor.neutral)}>
      {up ? "▲" : "▼"} {Math.abs(value)}%
    </span>
  );
}

export function ProBadge({ className }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border border-helm-gold/35 bg-helm-gold/12 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-helm-gold", className)}>
      Active
    </span>
  );
}

export function Spinner({ className }) {
  return <div className={cn("w-5 h-5 rounded-full border-2 border-helm-gold/35 border-t-helm-gold animate-spin", className)} />;
}

export function LoadingScreen({ label = "Loading" }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center py-32">
      <Spinner className="w-6 h-6 mb-4" />
      <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-muted">{label}</p>
    </div>
  );
}

export function ErrorScreen({
  label = "Something went wrong",
  title,
  message,
  onRetry,
}) {
  // Unexpected/crash-style: gold label + display title + recovery copy.
  // Load/access failures usually pass label + message only — keep that readable
  // without forcing the crash headline on top of a specific explanation.
  const headline = title || (!message ? "This screen hit an unexpected error." : null);
  const body = message || (
    headline
      ? "You can try again. If it keeps happening, refresh the page or sign back in."
      : null
  );

  return (
    <div
      className="flex-1 flex flex-col items-center justify-center py-24 md:py-32 px-6 text-center fade-up"
      data-testid="error-screen"
    >
      <TrenstonMark size={48} className="rounded-md mx-auto mb-6" />
      <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold mb-3">{label}</p>
      {headline ? (
        <h2 className="font-display text-2xl font-normal text-helm-fg tracking-tight max-w-md">{headline}</h2>
      ) : null}
      {body ? (
        <p className={cn("text-sm text-helm-muted max-w-md leading-relaxed", headline ? "mt-3" : "mt-1")}>
          {body}
        </p>
      ) : null}
      {onRetry && (
        <button
          type="button"
          data-testid="error-retry-btn"
          onClick={onRetry}
          className="mt-8 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-5 py-2.5 transition-colors hover:bg-helm-gold-hover"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, body, action }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-24 px-6 fade-up">
      {Icon && (
        <div className="w-14 h-14 rounded-2xl bg-helm-navy/5 border border-helm-line flex items-center justify-center mb-5">
          <Icon className="w-6 h-6 text-helm-gold" />
        </div>
      )}
      <h3 className="font-display text-xl text-helm-fg font-medium tracking-tight">{title}</h3>
      {body && <p className="text-sm text-helm-muted mt-2 max-w-sm leading-relaxed font-sans">{body}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

/** In-app confirm — replaces native window.confirm so dialogs match Trenston. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  destructive = true,
  busy = false,
  onConfirm,
  onCancel,
  testId = "confirm-dialog",
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid={testId} role="alertdialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-helm-ink/70"
        onClick={() => !busy && onCancel?.()}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-sm rounded-md border border-helm-line bg-helm-card p-5 space-y-3 shadow-xl">
        <div className="space-y-1.5">
          <p className="text-sm font-medium text-helm-fg">{title}</p>
          {description ? (
            <p className="text-sm text-helm-muted leading-relaxed">{description}</p>
          ) : null}
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            disabled={busy}
            data-testid={`${testId}-cancel`}
            onClick={() => onCancel?.()}
            className="rounded-md border border-helm-line text-sm px-3 py-2 text-helm-fg hover:bg-helm-fg/[0.04] disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            disabled={busy}
            data-testid={`${testId}-confirm`}
            onClick={() => onConfirm?.()}
            className={cn(
              "rounded-md text-sm font-medium px-3 py-2 disabled:opacity-50",
              destructive
                ? "border border-helm-status-negative/35 bg-helm-status-negative/12 text-helm-status-negative hover:bg-helm-status-negative/10"
                : "bg-helm-gold text-helm-navy hover:bg-helm-gold-hover",
            )}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
