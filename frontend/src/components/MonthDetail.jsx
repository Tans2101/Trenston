import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { api } from "@/lib/api";
import { GlassCard, SectionLabel } from "@/components/kit";
import { formatMoney } from "@/lib/money";

export function monthTitle(iso) {
  const [y, m] = String(iso || "").split("-").map(Number);
  if (!y || !m) return "";
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
}

function shortMonth(iso) {
  const [y, m] = String(iso || "").split("-").map(Number);
  if (!y || !m) return "";
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

export function shiftMonth(iso, delta) {
  const [y, m] = String(iso).split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** How a line got into this month, in plain words. */
export function lineNote(row) {
  if (!row.recurring) return "One-time";
  if (row.cadence === "annual") return `Annual plan from ${shortMonth(row.month)}, 1/12 counted each month`;
  return `Every month since ${shortMonth(row.month)}`;
}

function Lines({ rows, sym, testId }) {
  return (
    <ul className="divide-y divide-helm-line" data-testid={testId}>
      {rows.map((r) => (
        <li key={r.id || `${r.name}-${r.month}`} className="flex items-start justify-between gap-4 py-2.5">
          <div className="min-w-0">
            <p className="truncate text-sm text-helm-fg">{r.name}</p>
            <p className="text-xs text-helm-muted">{r.category} · {lineNote(r)}</p>
          </div>
          <span className="shrink-0 font-mono text-sm tabular-nums text-helm-fg">
            {r.is_credit ? "-" : ""}{formatMoney(r.amount, sym)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Every line behind one month's totals. A recurring expense is stored once and
 * counted in each month from its start, so this is where you see it month by month.
 */
export default function MonthDetail({ month, sym, onClose, onMonthChange }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setFailed(false);
    api.get(`/financials/month/${month}`)
      .then(({ data: d }) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [month]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const expenses = (data?.counted || []).filter((r) => r.type === "expense");
  const revenue = (data?.counted || []).filter((r) => r.type === "revenue");
  const canPrev = !data?.first_month || month > data.first_month;
  const canNext = !data?.current_month || month < data.current_month;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-helm-ink/70" onClick={onClose} />
      <GlassCard
        role="dialog"
        aria-modal="true"
        aria-label={`${monthTitle(month)} breakdown`}
        className="relative m-0 max-h-[90vh] w-full overflow-y-auto rounded-t-2xl p-6 sm:m-4 sm:max-w-lg sm:rounded-2xl"
        data-testid="month-detail"
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-1">
            <button type="button" aria-label="Previous month" title="Previous month" disabled={!canPrev} onClick={() => onMonthChange(shiftMonth(month, -1))} className="rounded p-1 text-helm-muted hover:text-helm-fg disabled:opacity-30">
              <ChevronLeft className="h-5 w-5" />
            </button>
            <h3 className="min-w-[9rem] text-center text-lg font-light text-helm-fg">{monthTitle(month)}</h3>
            <button type="button" aria-label="Next month" title="Next month" disabled={!canNext} onClick={() => onMonthChange(shiftMonth(month, 1))} className="rounded p-1 text-helm-muted hover:text-helm-fg disabled:opacity-30">
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          <button type="button" aria-label="Close" title="Close" onClick={onClose} className="text-helm-muted hover:text-helm-fg">
            <X className="h-5 w-5" />
          </button>
        </div>

        {failed && <p className="py-8 text-center text-sm text-helm-muted" data-testid="month-detail-error">Could not load this month. Please try again.</p>}
        {!failed && !data && <p className="py-8 text-center text-sm text-helm-muted">Loading...</p>}

        {data && (
          <>
            {data.future ? (
              <p className="py-8 text-center text-sm text-helm-muted">This month has not happened yet, so nothing is counted.</p>
            ) : (
              <>
                <div className="mb-5 grid grid-cols-3 gap-3 text-center" data-testid="month-detail-totals">
                  <div><SectionLabel>Revenue</SectionLabel><p className="mt-1 font-mono text-sm tabular-nums text-helm-fg">{formatMoney(data.revenue_total, sym)}</p></div>
                  <div><SectionLabel>Expenses</SectionLabel><p className="mt-1 font-mono text-sm tabular-nums text-helm-fg">{formatMoney(data.expense_total, sym)}</p></div>
                  <div><SectionLabel>{data.net >= 0 ? "Left over" : "Net loss"}</SectionLabel><p className="mt-1 font-mono text-sm tabular-nums text-helm-fg">{formatMoney(Math.abs(data.net), sym)}</p></div>
                </div>

                <div className="mb-5">
                  <SectionLabel>What you spent on</SectionLabel>
                  {expenses.length > 0 ? <Lines rows={expenses} sym={sym} testId="month-detail-expenses" /> : <p className="mt-2 text-sm text-helm-muted">No expenses counted for this month.</p>}
                </div>

                <div className="mb-5">
                  <SectionLabel>Revenue</SectionLabel>
                  {revenue.length > 0 ? <Lines rows={revenue} sym={sym} testId="month-detail-revenue" /> : <p className="mt-2 text-sm text-helm-muted">No revenue counted for this month.</p>}
                </div>

                {data.not_counted?.length > 0 && (
                  <div className="rounded-md border border-helm-line p-3" data-testid="month-detail-not-counted">
                    <SectionLabel>Not counted this month</SectionLabel>
                    <p className="mt-1 text-xs leading-relaxed text-helm-muted">
                      Trenston keeps one recurring amount per category. A later recurring entry in the same category replaces the earlier one.
                    </p>
                    <ul className="mt-2 space-y-1.5">
                      {data.not_counted.map((r) => (
                        <li key={r.id} className="text-xs text-helm-fg">
                          {r.name} ({formatMoney(r.amount, sym)}, {r.category}) is replaced by {r.replaced_by_name} from {shortMonth(r.replaced_from)}.
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </GlassCard>
    </div>
  );
}
