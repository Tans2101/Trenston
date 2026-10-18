import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { Waves } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api, apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/money";
import { monthLabel } from "@/lib/modelingFormat";
import {
  MAX_START_OFFSET, baselineReady, changeTone, cleanEffect, emptyEffect,
  rippleProjection, runwayText,
} from "@/lib/ripple";

const W = 600;
const H = 200;
const PAD = { l: 8, r: 8, t: 12, b: 22 };

function scaleFor(points) {
  const vals = points.flatMap((p) => [p.base, p.after]).filter((v) => v != null);
  let lo = Math.min(0, ...vals);
  let hi = Math.max(0, ...vals);
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.08;
  lo -= pad;
  hi += pad;
  const n = points.length;
  const x = (i) => PAD.l + (i / Math.max(1, n - 1)) * (W - PAD.l - PAD.r);
  const y = (v) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
  return { x, y };
}

function pathFor(points, key, x, y) {
  return points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
}

function RippleChart({ projection, symbol }) {
  const reduce = useReducedMotion();
  const pts = projection.base.points.map((p, i) => ({
    month: p.month, base: p.cash, after: projection.after.points[i].cash,
  }));
  if (!pts.length || pts[0].base == null) return null;
  const { x, y } = scaleFor(pts);
  const startIdx = projection.effect.start_offset - 1;
  const zeroY = y(0);
  const last = pts[pts.length - 1];
  return (
    <figure className="mt-4" aria-label="Cash over the next two years, with and without this decision">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img">
        <title>Cash over two years</title>
        <line x1={PAD.l} x2={W - PAD.r} y1={zeroY} y2={zeroY} className="stroke-helm-status-negative/50" strokeDasharray="2 4" />
        <text x={PAD.l + 4} y={zeroY - 5} textAnchor="start" className="fill-helm-muted text-[12px]">Cash runs out</text>
        <motion.line
          initial={false}
          animate={{ x1: x(startIdx), x2: x(startIdx) }}
          transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 30 }}
          y1={PAD.t}
          y2={H - PAD.b}
          className="stroke-helm-gold/40"
          strokeWidth="1"
        />
        <motion.path
          initial={false}
          animate={{ d: `${pathFor(pts, "after", x, y)} ${pts.map((p, i) => `L${x(pts.length - 1 - i).toFixed(1)},${y(pts[pts.length - 1 - i].base).toFixed(1)}`).join(" ")} Z` }}
          transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 200, damping: 28 }}
          className={last.after < last.base ? "fill-helm-status-negative/10" : "fill-helm-status-positive/10"}
          stroke="none"
        />
        <path d={pathFor(pts, "base", x, y)} fill="none" className="stroke-helm-muted" strokeWidth="1.5" strokeDasharray="4 4" />
        <motion.path
          initial={false}
          animate={{ d: pathFor(pts, "after", x, y) }}
          transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 200, damping: 28 }}
          fill="none"
          className="stroke-helm-gold"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <text x={PAD.l} y={H - 6} className="fill-helm-muted text-[12px]">{monthLabel(pts[0].month)}</text>
        <text x={W - PAD.r} y={H - 6} textAnchor="end" className="fill-helm-muted text-[12px]">{monthLabel(last.month)}</text>
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-helm-muted">
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 bg-helm-gold" aria-hidden />With this decision ({formatMoney(last.after, symbol, { compact: true })} in 2 years)</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 border-t border-dashed border-helm-muted" aria-hidden />Without it ({formatMoney(last.base, symbol, { compact: true })})</span>
      </figcaption>
    </figure>
  );
}

function Stat({ label, before, after, tone }) {
  return (
    <div className="min-w-0 rounded-lg border border-helm-line p-2.5 sm:p-3">
      <p className="truncate text-[10px] font-mono uppercase tracking-wide text-helm-muted">{label}</p>
      <p className="mt-1 truncate text-[11px] text-helm-muted line-through decoration-helm-muted/40 sm:text-xs">{before}</p>
      <p
        className={cn(
          "truncate font-display text-base tracking-tight sm:text-xl",
          tone === "worse" ? "text-helm-status-negative" : tone === "better" ? "text-helm-status-positive" : "text-helm-fg",
        )}
      >
        {after}
      </p>
    </div>
  );
}

const INPUT = "rounded-md border border-helm-line bg-helm-card px-2 py-1.5 text-sm text-helm-fg focus:outline-none focus:border-helm-gold/60";

export default function RippleDialog({ open, onOpenChange, decision, baseline, saved, canEdit, onSaved }) {
  const [effect, setEffect] = useState(emptyEffect());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setEffect(saved ? { ...saved } : emptyEffect());
  }, [open, saved]);

  const ready = baselineReady(baseline);
  const symbol = baseline?.currency_symbol || "$";
  const clean = cleanEffect(effect);
  const projection = useMemo(
    () => (ready.ok ? rippleProjection(baseline, effect) : null),
    [ready.ok, baseline, effect],
  );
  const tone = projection ? changeTone(projection.base.runway, projection.after.runway) : "neutral";
  const outText = (r) => (r.outMonth ? monthLabel(projection.base.points[r.outMonth - 1].month) : "Not in 2 years");
  const set = (k, v) => setEffect((e) => ({ ...e, [k]: v }));

  const save = async () => {
    if (!clean.amount) {
      toast.error("Enter an amount first");
      return;
    }
    setBusy(true);
    try {
      await api.put(`/decisions/${decision.id}/ripple`, clean);
      toast.success("Ripple saved to this decision");
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save"));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    try {
      await api.delete(`/decisions/${decision.id}/ripple`);
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not remove"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[92vh] w-[calc(100%-1.5rem)] max-w-2xl overflow-y-auto rounded-xl border-helm-line bg-helm-card p-5 sm:p-6"
        data-testid="ripple-dialog"
      >
        <div className="pr-6">
          <p className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-wider text-helm-gold">
            <Waves className="h-3.5 w-3.5" aria-hidden /> Ripple effect
          </p>
          <DialogTitle className="mt-1 font-display text-xl font-normal tracking-tight text-helm-fg">{decision?.title}</DialogTitle>
          <DialogDescription className="mt-1 text-sm text-helm-muted">
            See what this decision does to your cash and runway before you make it.
          </DialogDescription>
        </div>

        {!ready.ok ? (
          <div className="rounded-lg border border-helm-line bg-helm-fg/[0.03] p-4 text-sm text-helm-muted">
            <p className="text-helm-fg">The ripple needs your real numbers first.</p>
            <p className="mt-1">
              {ready.missing.includes("ledger") ? "Add at least one month of revenue and expenses" : "Add your cash balance"}
              {ready.missing.length > 1 ? " and your cash balance" : ""} on Financials, or import a spreadsheet.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link to="/app/financials" className="rounded-md bg-helm-gold px-3 py-1.5 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover">Open Financials</Link>
              <Link to="/app/import" className="rounded-md border border-helm-line px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-fg/[0.04]">Import a spreadsheet</Link>
            </div>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-2 text-sm text-helm-fg" data-testid="ripple-sentence">
              <span>This decision</span>
              <select aria-label="Cost or income" value={clean.direction} onChange={(e) => set("direction", e.target.value)} className={INPUT}>
                <option value="cost">costs</option>
                <option value="income">brings in</option>
              </select>
              <span className="inline-flex items-center rounded-md border border-helm-line bg-helm-card focus-within:border-helm-gold/60">
                <span className="pl-2 text-helm-muted" aria-hidden>{symbol}</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  aria-label="Amount"
                  placeholder="0"
                  value={effect.amount}
                  onChange={(e) => set("amount", e.target.value)}
                  className="w-28 bg-transparent px-1.5 py-1.5 text-sm text-helm-fg focus:outline-none"
                  data-testid="ripple-amount"
                />
              </span>
              <select aria-label="How often" value={clean.cadence} onChange={(e) => set("cadence", e.target.value)} className={INPUT}>
                <option value="monthly">every month</option>
                <option value="once">once</option>
              </select>
            </div>

            <div>
              <div className="flex items-center justify-between text-xs text-helm-muted">
                <label htmlFor="ripple-start">Starting</label>
                <span className="font-medium text-helm-fg">{monthLabel(projection.startMonth)}</span>
              </div>
              <input
                id="ripple-start"
                type="range"
                min="1"
                max={MAX_START_OFFSET}
                step="1"
                value={clean.start_offset}
                onChange={(e) => set("start_offset", Number(e.target.value))}
                className="mt-1 w-full accent-helm-gold"
                data-testid="ripple-start"
              />
              <p className="text-[11px] text-helm-muted">Drag to see what happens if you wait.</p>
            </div>

            <div className="grid grid-cols-3 gap-2" aria-live="polite">
              <Stat label="Runway" before={runwayText(projection.base.runway)} after={runwayText(projection.after.runway)} tone={tone} />
              <Stat label="Runs out" before={outText(projection.base.runway)} after={outText(projection.after.runway)} tone={tone} />
              <Stat
                label="Cash in 2 yrs"
                before={formatMoney(projection.base.endingCash, symbol, { compact: true })}
                after={formatMoney(projection.after.endingCash, symbol, { compact: true })}
                tone={projection.after.endingCash < projection.base.endingCash ? "worse" : projection.after.endingCash > projection.base.endingCash ? "better" : "neutral"}
              />
            </div>

            <RippleChart projection={projection} symbol={symbol} />

            <p className="text-[11px] leading-relaxed text-helm-muted">
              Based on your average month
              {baseline.months_used?.length ? ` (${baseline.months_used.map(monthLabel).join(", ")})` : ""}: revenue{" "}
              {formatMoney(baseline.revenue || 0, symbol, { compact: true })}, expenses {formatMoney(baseline.expenses || 0, symbol, { compact: true })},
              cash today {formatMoney(baseline.cash, symbol, { compact: true })}. It assumes everything else stays the same, so treat it as a guide, not a promise.
            </p>

            {canEdit && (
              <div className="flex flex-wrap items-center gap-2 border-t border-helm-line pt-4">
                <button
                  type="button"
                  onClick={save}
                  disabled={busy || !clean.amount}
                  className="rounded-md bg-helm-gold px-4 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover disabled:opacity-60"
                  data-testid="ripple-save"
                >
                  {saved ? "Update ripple" : "Save to this decision"}
                </button>
                {saved && (
                  <button type="button" onClick={clear} disabled={busy} className="px-2 text-sm text-helm-muted underline underline-offset-2 hover:text-helm-fg">
                    Remove
                  </button>
                )}
                <span className="text-xs text-helm-muted">Saved ripples show on the decision card for everyone with Financials access.</span>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
