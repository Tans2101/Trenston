/**
 * Lightweight product UI frames for marketing — real cockpit surfaces,
 * not abstract icons. Used on Landing / Features.
 */

function Chrome({ title, children }) {
  return (
    <div className="overflow-hidden rounded-lg border border-helm-cream/10 bg-helm-ink-card text-left shadow-none">
      <div className="flex items-center gap-2 border-b border-helm-cream/[0.06] px-3 py-2">
        <span className="h-1.5 w-1.5 rounded-full bg-helm-cream/20" />
        <span className="h-1.5 w-1.5 rounded-full bg-helm-cream/20" />
        <span className="h-1.5 w-1.5 rounded-full bg-helm-cream/20" />
        <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.18em] text-helm-slate">{title}</span>
      </div>
      <div className="p-3 md:p-4">{children}</div>
    </div>
  );
}

function Row({ left, mid, right, tone }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-helm-cream/[0.06] py-2.5 last:border-0">
      <p className="truncate text-xs text-helm-cream/90">{left}</p>
      <p className="font-mono text-[10px] text-helm-slate">{mid}</p>
      <p className={`font-mono text-[10px] tabular-nums ${tone || "text-helm-slate"}`}>{right}</p>
    </div>
  );
}

export function ProductionScreen() {
  return (
    <Chrome title="Production · Work orders">
      <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-helm-slate">Active queue</p>
      <Row left="WO-1842 · Chassis kit A" mid="Assembly" right="Due Fri" tone="text-helm-cream" />
      <Row left="WO-1839 · Frame weld B" mid="QA" right="On track" />
      <Row left="WO-1831 · Finish pass" mid="Blocked" right="Parts" tone="text-helm-status-warning" />
      <div className="mt-3 flex items-center justify-between border-t border-helm-cream/[0.06] pt-3">
        <span className="text-[10px] text-helm-slate">3 open · 1 blocked</span>
        <span className="font-mono text-[10px] text-helm-cream">Avg stage 2.4d</span>
      </div>
    </Chrome>
  );
}

export function ProcurementScreen() {
  return (
    <Chrome title="Procurement · Purchase requests">
      <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-helm-slate">This week</p>
      <Row left="Steel coil · 12t" mid="Approved" right="$18.4K" tone="text-helm-cream" />
      <Row left="Sensor pack · M4" mid="Ordered" right="$2.1K" />
      <Row left="Packaging sleeves" mid="Requested" right="$640" />
      <div className="mt-3 flex items-center justify-between border-t border-helm-cream/[0.06] pt-3">
        <span className="text-[10px] text-helm-slate">Awaiting delivery · 2</span>
        <span className="font-mono text-[10px] text-helm-cream">Committed $20.5K</span>
      </div>
    </Chrome>
  );
}

export function DecisionScreen() {
  return (
    <Chrome title="Decision Center">
      <p className="mb-2 font-mono text-[9px] uppercase tracking-[0.2em] text-helm-slate">Needs you today</p>
      <p className="text-sm text-helm-cream leading-snug">Approve $40K infrastructure reservation</p>
      <p className="mt-1.5 text-xs text-helm-cream/70 leading-relaxed">
        Pays back in four months. Cloud spend −18%. Owner: Ops.
      </p>
      <div className="mt-4 flex gap-2">
        <span className="rounded border border-helm-cream/15 px-2.5 py-1 font-mono text-[10px] text-helm-cream">Approve</span>
        <span className="rounded border border-helm-cream/10 px-2.5 py-1 font-mono text-[10px] text-helm-slate">Defer</span>
      </div>
    </Chrome>
  );
}

/** Landing / Features strip: three real cockpit surfaces. */
export default function ProductScreens({ className = "" }) {
  return (
    <div className={`grid gap-4 md:grid-cols-3 ${className}`} data-testid="product-screens">
      <ProductionScreen />
      <ProcurementScreen />
      <DecisionScreen />
    </div>
  );
}
