/**
 * Lightweight product UI frames for marketing — real cockpit surfaces,
 * not abstract icons. Used on Landing / Features.
 */

export function Chrome({ title, children }) {
  return (
    <div className="overflow-hidden border border-white/10 bg-mk-ink text-left shadow-none">
      <div className="flex items-center gap-2 border-b border-white/[0.06] px-3 py-2">
        <span className="h-1.5 w-1.5 rounded-full bg-white/20" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/20" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/20" />
        <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.18em] text-mk-gray-dark">{title}</span>
      </div>
      <div className="p-3 md:p-4">{children}</div>
    </div>
  );
}

export function Row({ left, mid, right, tone }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-white/[0.06] py-2.5 last:border-0">
      <p className="truncate text-xs text-white/90">{left}</p>
      <p className="font-mono text-[10px] text-mk-gray-dark">{mid}</p>
      <p className={`font-mono text-[10px] tabular-nums ${tone || "text-mk-gray-dark"}`}>{right}</p>
    </div>
  );
}

export function ProductionScreen() {
  return (
    <Chrome title="Production · Work orders">
      <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">Active queue</p>
      <Row left="WO-1842 · Chassis kit A" mid="Assembly" right="Due Fri" tone="text-white" />
      <Row left="WO-1839 · Frame weld B" mid="QA" right="On track" />
      <Row left="WO-1831 · Finish pass" mid="Blocked" right="Parts" tone="text-white underline decoration-white/40 underline-offset-2" />
      <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-3">
        <span className="text-[10px] text-mk-gray-dark">3 open · 1 blocked</span>
        <span className="font-mono text-[10px] text-white">Avg stage 2.4d</span>
      </div>
    </Chrome>
  );
}

export function ProcurementScreen() {
  return (
    <Chrome title="Procurement · Purchase requests">
      <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">This week</p>
      <Row left="Steel coil · 12t" mid="Approved" right="$18.4K" tone="text-white" />
      <Row left="Sensor pack · M4" mid="Ordered" right="$2.1K" />
      <Row left="Packaging sleeves" mid="Requested" right="$640" />
      <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-3">
        <span className="text-[10px] text-mk-gray-dark">Awaiting delivery · 2</span>
        <span className="font-mono text-[10px] text-white">Committed $20.5K</span>
      </div>
    </Chrome>
  );
}

export function DecisionScreen() {
  return (
    <Chrome title="Decision Center">
      <p className="mb-2 font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">Needs you today</p>
      <p className="text-sm text-white leading-snug">Approve $40K infrastructure reservation</p>
      <p className="mt-1.5 text-xs text-white/70 leading-relaxed">
        Pays back in four months. Cloud spend −18%. Owner: Ops.
      </p>
      <div className="mt-4 flex gap-2">
        <span className="border border-white/15 px-2.5 py-1 font-mono text-[10px] text-white">Approve</span>
        <span className="border border-white/10 px-2.5 py-1 font-mono text-[10px] text-mk-gray-dark">Defer</span>
      </div>
    </Chrome>
  );
}

export function FinanceScreen() {
  return (
    <Chrome title="Sales · Order book">
      <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">This month</p>
      <Row left="Deal #4102 · Expansion" mid="Won" right="+$42K" tone="text-white" />
      <Row left="Deal #4098 · Renewal" mid="Follow up" right="$18K" />
      <Row left="Deal #4110 · New logo" mid="Proposal" right="$9.5K" />
      <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-3">
        <span className="text-[10px] text-mk-gray-dark">$3.0M confirmed · $5.0M target</span>
        <span className="font-mono text-[10px] text-white">Gap $2.0M</span>
      </div>
    </Chrome>
  );
}

export function TeamScreen() {
  return (
    <Chrome title="Team & Access">
      <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">Departments</p>
      <Row left="Sales" mid="4 members" right="Owner" tone="text-white" />
      <Row left="Production" mid="6 members" right="Manager" />
      <Row left="Procurement" mid="2 members" right="Manager" />
      <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-3">
        <span className="text-[10px] text-mk-gray-dark">4 integrations connected</span>
        <span className="font-mono text-[10px] text-white">12 seats used</span>
      </div>
    </Chrome>
  );
}


/** Ask Trenston — the question comes from CEO_DAY copy; the answer panel
 * only names the sources it draws on (no invented figures). */
export function AskScreen() {
  return (
    <Chrome title="Ask Trenston">
      <p className="mb-2 font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">You asked</p>
      <p className="text-sm leading-snug text-white">&ldquo;What&apos;s our biggest risk this quarter?&rdquo;</p>
      <div className="mt-4 border-t border-white/[0.08] pt-3">
        <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">Answered from</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {["Financials", "Pipeline", "Decisions", "Departments"].map((s) => (
            <span key={s} className="border border-white/15 px-2 py-0.5 font-mono text-[10px] text-white">{s}</span>
          ))}
        </div>
      </div>
      <p className="mt-3 text-[10px] text-mk-gray-dark">Not the internet. Gaps are called out, not guessed.</p>
    </Chrome>
  );
}

/** CEO Pack — section list mirrors the CEO_DAY description. */
export function PackScreen() {
  return (
    <Chrome title="CEO Pack">
      <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-mk-gray-dark">Leadership summary</p>
      <Row left="Growth" mid="Section" right="Included" tone="text-white" />
      <Row left="Cash" mid="Section" right="Included" />
      <Row left="Team pulse" mid="Section" right="Included" />
      <Row left="Open decisions" mid="Section" right="Included" />
      <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-3">
        <span className="text-[10px] text-mk-gray-dark">Generated in one click</span>
        <span className="font-mono text-[10px] text-white">Share</span>
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
