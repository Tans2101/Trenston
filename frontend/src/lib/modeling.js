/**
 * Deterministic cash projection. A line-for-line port of backend/modeling.py
 * so sliders recompute instantly in the browser. Both are checked against
 * shared/modeling-parity.json (see modeling.test.js and
 * backend/tests/test_modeling.py). Change one, and the parity tests fail
 * until the other matches.
 */

export const GROWTH_PCT_MIN = -50;
export const GROWTH_PCT_MAX = 100;
export const HORIZONS = [12, 24, 36];
export const DEFAULT_HORIZON = 24;
export const MAX_HIRES = 20;
export const MAX_EVENTS = 20;
export const MAX_LABEL_LEN = 60;
export const MAX_MONEY = 1e12;

export const RUNWAY_MONTHS = "months";
export const RUNWAY_CASH_GROWING = "cash_growing";
export const RUNWAY_BEYOND = "beyond_horizon";
export const RUNWAY_NO_CASH = "no_cash";
export const RUNWAY_NO_LEDGER = "no_ledger";

const NUMERIC_RE = /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/;

function num(value, fallback = null) {
  if (value === null || value === undefined || typeof value === "boolean") return fallback;
  let f;
  if (typeof value === "string") {
    if (!NUMERIC_RE.test(value)) return fallback;
    f = Number(value);
  } else if (typeof value === "number") {
    f = value;
  } else {
    return fallback;
  }
  return Number.isFinite(f) ? f : fallback;
}

function clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value));
}

function label(value) {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, MAX_LABEL_LEN);
}

function intIn(value, lo, hi, fallback) {
  const f = num(value);
  if (f === null) return fallback;
  return clamp(Math.floor(f), lo, hi);
}

export function sanitizeInputs(raw) {
  const r = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  let horizon = intIn(r.horizon, 0, 1000, DEFAULT_HORIZON);
  if (!HORIZONS.includes(horizon)) horizon = DEFAULT_HORIZON;

  const hires = [];
  for (const h of Array.isArray(r.hires) ? r.hires.slice(0, MAX_HIRES) : []) {
    if (!h || typeof h !== "object" || Array.isArray(h)) continue;
    hires.push({
      label: label(h.label),
      monthly_cost: clamp(num(h.monthly_cost, 0), 0, MAX_MONEY),
      start_month: intIn(h.start_month, 1, horizon, 1),
    });
  }

  const events = [];
  for (const e of Array.isArray(r.events) ? r.events.slice(0, MAX_EVENTS) : []) {
    if (!e || typeof e !== "object" || Array.isArray(e)) continue;
    events.push({
      label: label(e.label),
      amount: clamp(num(e.amount, 0), -MAX_MONEY, MAX_MONEY),
      month: intIn(e.month, 1, horizon, 1),
    });
  }

  let reserve = num(r.min_cash_reserve);
  if (reserve !== null) reserve = clamp(reserve, 0, MAX_MONEY);

  return {
    revenue_growth_pct: clamp(num(r.revenue_growth_pct, 0), GROWTH_PCT_MIN, GROWTH_PCT_MAX),
    expense_growth_pct: clamp(num(r.expense_growth_pct, 0), GROWTH_PCT_MIN, GROWTH_PCT_MAX),
    hires,
    events,
    min_cash_reserve: reserve,
    horizon,
  };
}

const INT_RE = /^\s*[+-]?\d+\s*$/;

/** "2026-09" + 3 -> "2026-12". Invalid input returns "". */
export function addMonths(ym, n) {
  const parts = String(ym ?? "").split("-");
  if (parts.length < 2 || !INT_RE.test(parts[0]) || !INT_RE.test(parts[1])) return "";
  const y = Number.parseInt(parts[0], 10);
  const m = Number.parseInt(parts[1], 10);
  if (m < 1 || m > 12) return "";
  const idx = y * 12 + (m - 1) + n;
  const yy = Math.floor(idx / 12);
  const mm = (((idx % 12) + 12) % 12) + 1;
  return `${String(yy).padStart(4, "0")}-${String(mm).padStart(2, "0")}`;
}

export function projectCash(inputs, baseline) {
  const x = sanitizeInputs(inputs);
  const b = baseline && typeof baseline === "object" ? baseline : {};
  const cash0 = num(b.cash);
  let rev0 = num(b.revenue);
  let exp0 = num(b.expenses);
  const start = String(b.start_month || "");
  const { horizon } = x;
  const reserve = x.min_cash_reserve;

  const result = {
    horizon,
    points: [],
    runway_status: RUNWAY_NO_LEDGER,
    runway_months: null,
    cash_out_month: null,
    reserve_breach_month: null,
    break_even_month: null,
    ending_cash: null,
    cash_known: cash0 !== null,
    ledger_known: rev0 !== null || exp0 !== null,
  };
  if (rev0 === null && exp0 === null) return result;

  rev0 = rev0 || 0;
  exp0 = exp0 || 0;
  const gRev = x.revenue_growth_pct / 100;
  const gExp = x.expense_growth_pct / 100;

  let cash = cash0;
  let allPositive = true;
  const points = [];
  for (let m = 1; m <= horizon; m += 1) {
    const revenue = rev0 * (1 + gRev) ** m;
    let expenses = exp0 * (1 + gExp) ** m;
    for (const h of x.hires) {
      if (h.start_month <= m) expenses += h.monthly_cost;
    }
    let oneTime = 0;
    for (const e of x.events) {
      if (e.month === m) oneTime += e.amount;
    }
    const net = revenue - expenses + oneTime;
    if (net < 0) allPositive = false;
    if (result.break_even_month === null && revenue >= expenses && revenue > 0) {
      result.break_even_month = m;
    }

    const prevCash = cash;
    if (cash !== null) {
      cash += net;
      if (result.cash_out_month === null && cash < 0) {
        result.cash_out_month = m;
        const span = prevCash - cash;
        const frac = span > 0 && prevCash > 0 ? prevCash / span : 0;
        result.runway_months = m - 1 + frac;
      }
      if (reserve !== null && result.reserve_breach_month === null && cash < reserve) {
        result.reserve_breach_month = m;
      }
    }

    points.push({ m, month: addMonths(start, m), revenue, expenses, net, cash });
  }

  result.points = points;
  if (cash0 === null) {
    result.runway_status = RUNWAY_NO_CASH;
    return result;
  }

  if (cash0 < 0) {
    result.cash_out_month = 0;
    result.runway_months = 0;
  }
  if (reserve !== null && cash0 < reserve) result.reserve_breach_month = 0;

  result.ending_cash = cash;
  if (result.runway_months !== null) result.runway_status = RUNWAY_MONTHS;
  else if (allPositive) result.runway_status = RUNWAY_CASH_GROWING;
  else result.runway_status = RUNWAY_BEYOND;
  return result;
}

/** The comparison line: current trajectory with no growth, hires or events. */
export function baselineInputs(inputs) {
  const x = sanitizeInputs(inputs);
  return {
    revenue_growth_pct: 0,
    expense_growth_pct: 0,
    hires: [],
    events: [],
    min_cash_reserve: x.min_cash_reserve,
    horizon: x.horizon,
  };
}
