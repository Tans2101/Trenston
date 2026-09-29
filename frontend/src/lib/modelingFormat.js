/** Display helpers for the Financial Modeling page. Pure, so they are unit-tested. */
import { formatMoney } from "@/lib/money";
import {
  addMonths,
  RUNWAY_MONTHS,
  RUNWAY_CASH_GROWING,
  RUNWAY_BEYOND,
  RUNWAY_NO_CASH,
  RUNWAY_NO_LEDGER,
} from "@/lib/modeling";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10" -> "Oct 2026". Anything else passes through unchanged. */
export function monthLabel(ym) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(ym || ""));
  if (!m) return String(ym || "");
  const idx = Number(m[2]) - 1;
  if (idx < 0 || idx > 11) return String(ym);
  return `${MONTHS[idx]} ${m[1]}`;
}

/** Month index (1..horizon, or 0 for "now") to a calendar label. */
export function modelMonthLabel(startMonth, m) {
  if (m === 0) return "Now";
  return monthLabel(addMonths(startMonth, m));
}

export function fmtMonths(n) {
  const v = Math.round(n * 10) / 10;
  return `${v.toFixed(1)} month${v === 1 ? "" : "s"}`;
}

/** Headline runway: value text + one short supporting line. */
export function runwayDisplay(r) {
  switch (r.runway_status) {
    case RUNWAY_MONTHS:
      return { value: fmtMonths(r.runway_months), note: r.runway_months === 0 ? "Cash is already below zero" : "Until cash runs out" };
    case RUNWAY_CASH_GROWING:
      return { value: "No net burn", note: "Cash does not fall in any month" };
    case RUNWAY_BEYOND:
      return { value: `Over ${r.horizon} months`, note: "Still burning, but cash lasts the horizon" };
    case RUNWAY_NO_CASH:
      return { value: "Add cash balance", note: "Needed to project runway", missing: true };
    case RUNWAY_NO_LEDGER:
    default:
      return { value: "Add data", note: "Log revenue or expenses first", missing: true };
  }
}

export function cashOutDisplay(r, startMonth) {
  if (r.runway_status === RUNWAY_NO_CASH) return { value: "Add cash balance", missing: true };
  if (r.runway_status === RUNWAY_NO_LEDGER) return { value: "Add data", missing: true };
  if (r.cash_out_month === null) return { value: `Not within ${r.horizon} months` };
  return { value: modelMonthLabel(startMonth, r.cash_out_month) };
}

export function breakEvenDisplay(r, startMonth) {
  if (r.runway_status === RUNWAY_NO_LEDGER) return { value: "Add data", missing: true };
  if (r.break_even_month === null) return { value: `Not within ${r.horizon} months` };
  return { value: modelMonthLabel(startMonth, r.break_even_month) };
}

export function endingCashDisplay(r, symbol) {
  if (r.runway_status === RUNWAY_NO_CASH) return { value: "Add cash balance", missing: true };
  if (r.runway_status === RUNWAY_NO_LEDGER || r.ending_cash === null) return { value: "Add data", missing: true };
  return { value: formatMoney(r.ending_cash, symbol, { compact: Math.abs(r.ending_cash) >= 1e6 }) };
}

function signed(n, digits = 1) {
  const v = Number(n.toFixed(digits));
  if (v === 0) return null;
  return `${v > 0 ? "+" : "-"}${Math.abs(v).toFixed(digits)}`;
}

/** Runway change vs the comparison, or null when there is nothing honest to say. */
export function runwayDelta(r, base) {
  if (r.runway_status === RUNWAY_MONTHS && base.runway_status === RUNWAY_MONTHS) {
    const s = signed(r.runway_months - base.runway_months);
    return s ? `${s} months vs current trajectory` : "Same as current trajectory";
  }
  if (base.runway_status === RUNWAY_MONTHS && r.runway_status !== RUNWAY_MONTHS
      && r.runway_status !== RUNWAY_NO_CASH && r.runway_status !== RUNWAY_NO_LEDGER) {
    return `Current trajectory: ${fmtMonths(base.runway_months)}`;
  }
  if (r.runway_status === RUNWAY_MONTHS && base.runway_status !== RUNWAY_MONTHS
      && base.runway_status !== RUNWAY_NO_CASH && base.runway_status !== RUNWAY_NO_LEDGER) {
    return `Current trajectory lasts over ${base.horizon} months`;
  }
  return null;
}

export function endingCashDelta(r, base, symbol) {
  if (r.ending_cash === null || base.ending_cash === null) return null;
  const d = r.ending_cash - base.ending_cash;
  if (Math.abs(d) < 0.5) return "Same as current trajectory";
  const text = formatMoney(Math.abs(d), symbol, { compact: Math.abs(d) >= 1e4 });
  return `${d > 0 ? "+" : "-"}${text} vs current trajectory`;
}

export function breakEvenDelta(r, base) {
  if (r.break_even_month === null || base.break_even_month === null) return null;
  const d = r.break_even_month - base.break_even_month;
  if (d === 0) return "Same as current trajectory";
  return `${Math.abs(d)} month${Math.abs(d) === 1 ? "" : "s"} ${d < 0 ? "sooner" : "later"}`;
}
