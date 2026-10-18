/**
 * Decision ripple: what one decision does to cash and runway over 24 months.
 * Runs in the browser so moving the start month redraws instantly. The
 * baseline is the same one Financial Modeling uses (average of the last
 * complete months from real Financials, cash in bank today).
 */
import { projectCash, addMonths } from "@/lib/modeling";

export const RIPPLE_HORIZON = 24;
export const MAX_START_OFFSET = 12;

export function emptyEffect() {
  return { direction: "cost", cadence: "monthly", amount: "", start_offset: 1 };
}

export function cleanEffect(raw) {
  const e = raw && typeof raw === "object" ? raw : {};
  const amount = Number(e.amount);
  const start = Math.round(Number(e.start_offset));
  return {
    direction: e.direction === "income" ? "income" : "cost",
    cadence: e.cadence === "once" ? "once" : "monthly",
    amount: Number.isFinite(amount) && amount > 0 ? amount : 0,
    start_offset: Number.isFinite(start) ? Math.min(MAX_START_OFFSET, Math.max(1, start)) : 1,
  };
}

/** Is there enough real data to project? */
export function baselineReady(baseline) {
  if (!baseline) return { ok: false, missing: ["ledger", "cash"] };
  const missing = [];
  if (baseline.revenue == null && baseline.expenses == null) missing.push("ledger");
  if (baseline.cash == null) missing.push("cash");
  return { ok: missing.length === 0, missing };
}

function runwayFrom(points, cash0) {
  // Mirrors modeling.projectCash: interpolate inside the month cash crosses zero.
  if (cash0 == null) return { status: "no_cash", months: null, outMonth: null };
  if (cash0 < 0) return { status: "months", months: 0, outMonth: 0 };
  let prev = cash0;
  let allPositive = true;
  for (const p of points) {
    if (p.net < 0) allPositive = false;
    if (p.cash < 0) {
      const span = prev - p.cash;
      const frac = span > 0 && prev > 0 ? prev / span : 0;
      return { status: "months", months: p.m - 1 + frac, outMonth: p.m };
    }
    prev = p.cash;
  }
  return { status: allPositive ? "cash_growing" : "beyond_horizon", months: null, outMonth: null };
}

/**
 * Returns { base, after } where each is
 *   { points: [{m, month, net, cash}], runway: {status, months, outMonth}, endingCash }.
 */
export function rippleProjection(baseline, rawEffect) {
  const effect = cleanEffect(rawEffect);
  const b = baseline || {};
  const projected = projectCash(
    { horizon: RIPPLE_HORIZON, min_cash_reserve: b.min_cash_reserve ?? null },
    b,
  );
  const cash0 = b.cash == null ? null : Number(b.cash);
  const basePoints = projected.points.map((p) => ({ m: p.m, month: p.month, net: p.net, cash: p.cash }));
  const sign = effect.direction === "income" ? 1 : -1;
  let cash = cash0;
  const afterPoints = basePoints.map((p) => {
    const hits = effect.cadence === "monthly" ? p.m >= effect.start_offset : p.m === effect.start_offset;
    const net = p.net + (hits ? sign * effect.amount : 0);
    cash = cash == null ? null : cash + net;
    return { m: p.m, month: p.month, net, cash };
  });
  const pack = (points) => ({
    points,
    runway: runwayFrom(points, cash0),
    endingCash: points.length && points[points.length - 1].cash != null ? points[points.length - 1].cash : null,
  });
  return { base: pack(basePoints), after: pack(afterPoints), effect, startMonth: addMonths(b.start_month || "", effect.start_offset) };
}

/** Months of runway as a number for comparing, or Infinity when cash lasts. */
export function runwayValue(runway) {
  if (!runway) return null;
  if (runway.status === "months") return runway.months;
  if (runway.status === "cash_growing" || runway.status === "beyond_horizon") return Infinity;
  return null;
}

export function runwayText(runway) {
  if (!runway) return "";
  if (runway.status === "months") return `${runway.months < 10 ? runway.months.toFixed(1) : Math.round(runway.months)} months`;
  if (runway.status === "cash_growing") return "Cash keeps growing";
  if (runway.status === "beyond_horizon") return "Over 2 years";
  return "Add cash to see";
}

/** Short change label for a card chip, e.g. "-4.4 mo runway" or "Cash lasts 2+ yrs". */
export function runwayChangeLabel(before, after) {
  const a = runwayValue(before);
  const b = runwayValue(after);
  if (a == null || b == null) return null;
  if (a === Infinity && b === Infinity) return "Runway stays over 2 years";
  if (a === Infinity) return `Runway drops to ${runwayText(after)}`;
  if (b === Infinity) return "Runway goes past 2 years";
  const d = b - a;
  if (Math.abs(d) < 0.05) return "No change to runway";
  return `${d > 0 ? "+" : "-"}${Math.abs(d).toFixed(1)} mo runway`;
}

/** Tone for the change: worse (red), better (green) or neutral. */
export function changeTone(before, after) {
  const a = runwayValue(before);
  const b = runwayValue(after);
  if (a == null || b == null || a === b) return "neutral";
  return b < a ? "worse" : "better";
}
