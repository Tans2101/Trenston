import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ReferenceDot, Legend,
} from "recharts";
import { ChevronDown, Plus, X, Lock, SlidersHorizontal, MoreHorizontal, Table2 } from "lucide-react";
import { api } from "@/lib/api";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useTheme } from "@/context/ThemeContext";
import { PageHeader, ErrorScreen } from "@/components/kit";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { confirmAction } from "@/components/ConfirmHost";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/money";
import { formatAxisMoney } from "@/lib/formatAxisMoney";
import { ACCENT } from "@/lib/accent";
import palette from "@/design/palette.json";
import {
  projectCash, sanitizeInputs, baselineInputs,
  GROWTH_PCT_MIN, GROWTH_PCT_MAX, HORIZONS, DEFAULT_HORIZON, MAX_HIRES, MAX_EVENTS, MAX_LABEL_LEN,
} from "@/lib/modeling";
import {
  monthLabel, modelMonthLabel, runwayDisplay, cashOutDisplay, breakEvenDisplay, endingCashDisplay,
  runwayDelta, endingCashDelta, breakEvenDelta,
} from "@/lib/modelingFormat";


const BASELINE_ID = "baseline";
const MAX_COMPARE = 2;

// Comparison lines use the validated reference categorical slots 2 and 3
// (orange, aqua), stepped per theme. The active scenario is the brand accent;
// the current trajectory is a neutral dashed line.
const COMPARE_COLORS = {
  light: ["#eb6834", "#1baf7a"],
  dark: ["#d95926", "#199e70"],
};
const COMPARE_DASH = ["", "2 3"];

function defaultInputs(baseline) {
  return sanitizeInputs({
    horizon: DEFAULT_HORIZON,
    min_cash_reserve: baseline?.min_cash_reserve ?? null,
  });
}

const same = (a, b) => JSON.stringify(sanitizeInputs(a)) === JSON.stringify(sanitizeInputs(b));

/* ------------------------------------------------------------------ inputs */

/** Text input that lets people type freely and commits a parsed number on blur/Enter. */
function NumberInput({ value, onCommit, min, max, step, suffix, prefix, ariaLabel, disabled, allowEmpty, className }) {
  const [text, setText] = useState(value === null || value === undefined ? "" : String(value));
  const focused = useRef(false);
  useEffect(() => {
    if (!focused.current) setText(value === null || value === undefined ? "" : String(value));
  }, [value]);

  const commit = () => {
    const raw = text.replace(/,/g, "").trim();
    if (raw === "") {
      if (allowEmpty) { onCommit(null); return; }
      setText(String(value ?? ""));
      return;
    }
    const n = Number(raw);
    if (!Number.isFinite(n)) { setText(String(value ?? "")); return; }
    let v = n;
    if (min !== undefined) v = Math.max(min, v);
    if (max !== undefined) v = Math.min(max, v);
    if (step && step >= 1) v = Math.round(v);
    setText(String(v));
    onCommit(v);
  };

  return (
    <div className={cn(
      "flex items-center rounded-md border border-helm-line bg-helm-bg focus-within:border-helm-gold/50",
      disabled && "opacity-60",
      className,
    )}>
      {prefix ? <span className="pl-2.5 text-xs text-helm-muted">{prefix}</span> : null}
      <input
        type="text"
        inputMode="decimal"
        aria-label={ariaLabel}
        disabled={disabled}
        value={text}
        onFocus={() => { focused.current = true; }}
        onBlur={() => { focused.current = false; commit(); }}
        onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
        onChange={(e) => setText(e.target.value)}
        className="w-full min-w-0 bg-transparent px-2.5 py-1.5 text-sm tabular-nums text-helm-fg focus:outline-none"
      />
      {suffix ? <span className="pr-2.5 text-xs text-helm-muted">{suffix}</span> : null}
    </div>
  );
}

function DriverSlider({ id, label, hint, value, onChange, min, max, step, unit, disabled }) {
  const shown = Number.isInteger(value) ? value : value.toFixed(1);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm text-helm-fg">{label}</label>
        <NumberInput
          value={value}
          min={min}
          max={max}
          suffix={unit}
          ariaLabel={`${label} exact value`}
          disabled={disabled}
          onCommit={(v) => onChange(v)}
          className="w-24"
        />
      </div>
      {hint ? <p className="mt-0.5 text-xs text-helm-muted">{hint}</p> : null}
      <Slider
        className="mt-3"
        min={min}
        max={max}
        step={step}
        value={[value]}
        disabled={disabled}
        onValueChange={([v]) => onChange(v)}
        trackClassName="h-1 bg-helm-fg/10"
        rangeClassName="bg-helm-gold"
        thumbClassName="h-4 w-4 border-helm-gold bg-helm-bg shadow-none focus-visible:ring-2 focus-visible:ring-helm-gold/40"
        thumbProps={{ id, "aria-label": label, "aria-valuetext": `${shown}${unit === "%" ? " percent per month" : ""}` }}
      />
      <div className="mt-1.5 flex justify-between text-[11px] text-helm-muted tabular-nums">
        <span>{min}{unit}</span><span>0{unit}</span><span>+{max}{unit}</span>
      </div>
    </div>
  );
}

function MonthSelect({ value, horizon, startMonth, onChange, ariaLabel, disabled }) {
  return (
    <div className="relative">
      <select
        aria-label={ariaLabel}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full appearance-none rounded-md border border-helm-line bg-helm-bg py-1.5 pl-2.5 pr-7 text-sm text-helm-fg focus:outline-none focus:border-helm-gold/50"
      >
        {Array.from({ length: horizon }, (_, i) => i + 1).map((m) => (
          <option key={m} value={m}>{modelMonthLabel(startMonth, m)}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-helm-muted" />
    </div>
  );
}

function RowList({ title, hint, rows, emptyText, addLabel, onAdd, canAdd, renderRow, disabled }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-sm text-helm-fg">{title}</p>
        <button
          type="button"
          onClick={onAdd}
          disabled={!canAdd || disabled}
          className="inline-flex items-center gap-1 text-xs text-helm-gold hover:text-helm-gold-hover disabled:opacity-40"
        >
          <Plus className="h-3.5 w-3.5" /> {addLabel}
        </button>
      </div>
      {hint ? <p className="mt-0.5 text-xs text-helm-muted">{hint}</p> : null}
      <div className="mt-2 space-y-2">
        {rows.length === 0 ? (
          <p className="rounded-md border border-dashed border-helm-line px-3 py-2.5 text-xs text-helm-muted">{emptyText}</p>
        ) : rows.map(renderRow)}
      </div>
    </div>
  );
}

function Controls({ inputs, setInputs, baseline, symbol, disabled, onSaveReserve, reserveBusy }) {
  const set = (patch) => setInputs((prev) => sanitizeInputs({ ...prev, ...patch }));
  const { horizon } = inputs;
  const start = baseline?.start_month || "";
  const companyReserve = baseline?.min_cash_reserve ?? null;
  const reserveDiffers = inputs.min_cash_reserve !== companyReserve;

  const updateRow = (key, i, patch) =>
    set({ [key]: inputs[key].map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const removeRow = (key, i) => set({ [key]: inputs[key].filter((_, j) => j !== i) });

  return (
    <div className="space-y-7" data-testid="modeling-controls">
      <div>
        <p className="text-sm text-helm-fg">Horizon</p>
        <div className="mt-2 inline-flex rounded-md border border-helm-line overflow-hidden" role="group" aria-label="Horizon">
          {HORIZONS.map((h, i) => (
            <button
              key={h}
              type="button"
              disabled={disabled}
              aria-pressed={horizon === h}
              data-testid={`horizon-${h}`}
              onClick={() => set({ horizon: h })}
              className={cn(
                "px-3.5 py-1.5 text-sm tabular-nums transition-colors",
                i > 0 && "border-l border-helm-line",
                horizon === h ? "bg-helm-gold text-helm-navy" : "text-helm-muted hover:text-helm-fg hover:bg-helm-fg/[0.04]",
              )}
            >
              {h} months
            </button>
          ))}
        </div>
      </div>

      <DriverSlider
        id="rev-growth"
        label="Revenue growth"
        hint="Change per month, compounding."
        value={inputs.revenue_growth_pct}
        onChange={(v) => set({ revenue_growth_pct: v })}
        min={GROWTH_PCT_MIN}
        max={GROWTH_PCT_MAX}
        step={0.5}
        unit="%"
        disabled={disabled}
      />
      <DriverSlider
        id="exp-growth"
        label="Expense growth"
        hint="Applies to today's expenses. Hires below are added on top."
        value={inputs.expense_growth_pct}
        onChange={(v) => set({ expense_growth_pct: v })}
        min={GROWTH_PCT_MIN}
        max={GROWTH_PCT_MAX}
        step={0.5}
        unit="%"
        disabled={disabled}
      />

      <RowList
        title="Planned hires"
        hint="Monthly cost from the start month onward."
        rows={inputs.hires}
        emptyText="No hires in this scenario."
        addLabel="Add hire"
        canAdd={inputs.hires.length < MAX_HIRES}
        disabled={disabled}
        onAdd={() => set({ hires: [...inputs.hires, { label: "", monthly_cost: 0, start_month: 1 }] })}
        renderRow={(h, i) => (
          <div key={i} className="grid grid-cols-[1fr_auto] gap-2 rounded-md border border-helm-line p-2.5" data-testid={`hire-row-${i}`}>
            <input
              value={h.label}
              maxLength={MAX_LABEL_LEN}
              disabled={disabled}
              aria-label={`Hire ${i + 1} role`}
              placeholder="Role, e.g. Engineer"
              onChange={(e) => updateRow("hires", i, { label: e.target.value })}
              className="min-w-0 rounded-md border border-helm-line bg-helm-bg px-2.5 py-1.5 text-sm text-helm-fg focus:outline-none focus:border-helm-gold/50"
            />
            <button type="button" disabled={disabled} onClick={() => removeRow("hires", i)} aria-label={`Remove hire ${i + 1}`} className="rounded-md px-1.5 text-helm-muted hover:text-helm-fg">
              <X className="h-4 w-4" />
            </button>
            <div className="col-span-2 grid grid-cols-2 gap-2">
              <NumberInput value={h.monthly_cost} min={0} prefix={symbol} suffix="/mo" ariaLabel={`Hire ${i + 1} monthly cost`} disabled={disabled} onCommit={(v) => updateRow("hires", i, { monthly_cost: v })} />
              <MonthSelect value={h.start_month} horizon={horizon} startMonth={start} ariaLabel={`Hire ${i + 1} start month`} disabled={disabled} onChange={(v) => updateRow("hires", i, { start_month: v })} />
            </div>
          </div>
        )}
      />

      <RowList
        title="One-time events"
        hint="A funding round, a large purchase, a tax payment."
        rows={inputs.events}
        emptyText="No one-time events."
        addLabel="Add event"
        canAdd={inputs.events.length < MAX_EVENTS}
        disabled={disabled}
        onAdd={() => set({ events: [...inputs.events, { label: "", amount: 0, month: 1 }] })}
        renderRow={(e, i) => {
          const inflow = e.amount >= 0;
          return (
            <div key={i} className="grid grid-cols-[1fr_auto] gap-2 rounded-md border border-helm-line p-2.5" data-testid={`event-row-${i}`}>
              <input
                value={e.label}
                maxLength={MAX_LABEL_LEN}
                disabled={disabled}
                aria-label={`Event ${i + 1} name`}
                placeholder="e.g. Seed round"
                onChange={(ev) => updateRow("events", i, { label: ev.target.value })}
                className="min-w-0 rounded-md border border-helm-line bg-helm-bg px-2.5 py-1.5 text-sm text-helm-fg focus:outline-none focus:border-helm-gold/50"
              />
              <button type="button" disabled={disabled} onClick={() => removeRow("events", i)} aria-label={`Remove event ${i + 1}`} className="rounded-md px-1.5 text-helm-muted hover:text-helm-fg">
                <X className="h-4 w-4" />
              </button>
              <div className="col-span-2 grid grid-cols-[auto_1fr_1fr] gap-2">
                <div className="inline-flex rounded-md border border-helm-line overflow-hidden text-xs" role="group" aria-label={`Event ${i + 1} direction`}>
                  {[["In", true], ["Out", false]].map(([lbl, dirIn], k) => (
                    <button
                      key={lbl}
                      type="button"
                      disabled={disabled}
                      aria-pressed={inflow === dirIn}
                      onClick={() => updateRow("events", i, { amount: dirIn ? Math.abs(e.amount) : -Math.abs(e.amount) })}
                      className={cn("px-2.5", k > 0 && "border-l border-helm-line", inflow === dirIn ? "bg-helm-gold text-helm-navy" : "text-helm-muted hover:text-helm-fg")}
                    >
                      {lbl}
                    </button>
                  ))}
                </div>
                <NumberInput
                  value={Math.abs(e.amount)}
                  min={0}
                  prefix={symbol}
                  ariaLabel={`Event ${i + 1} amount`}
                  disabled={disabled}
                  onCommit={(v) => updateRow("events", i, { amount: inflow ? v : -v })}
                />
                <MonthSelect value={e.month} horizon={horizon} startMonth={start} ariaLabel={`Event ${i + 1} month`} disabled={disabled} onChange={(v) => updateRow("events", i, { month: v })} />
              </div>
            </div>
          );
        }}
      />

      <div>
        <p className="text-sm text-helm-fg">Minimum cash reserve</p>
        <p className="mt-0.5 text-xs text-helm-muted">The cash you never want to go below. Shown as a line on the chart.</p>
        <NumberInput
          className="mt-2"
          value={inputs.min_cash_reserve}
          min={0}
          prefix={symbol}
          allowEmpty
          ariaLabel="Minimum cash reserve"
          disabled={disabled}
          onCommit={(v) => set({ min_cash_reserve: v })}
        />
        {onSaveReserve && reserveDiffers && !disabled ? (
          <button
            type="button"
            onClick={() => onSaveReserve(inputs.min_cash_reserve)}
            disabled={reserveBusy}
            data-testid="save-company-reserve"
            className="mt-2 text-xs text-helm-gold underline-offset-2 hover:underline disabled:opacity-50"
          >
            {inputs.min_cash_reserve === null ? "Clear the company reserve" : "Use this as the company reserve for runway alerts"}
          </button>
        ) : null}
        {!onSaveReserve || disabled || reserveDiffers ? null : (
          <p className="mt-2 text-xs text-helm-muted">
            {companyReserve === null ? "No company reserve set, so runway alerts stay off." : "Matches the company reserve used for runway alerts."}
          </p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ results */

function ResultCard({ label, display, delta, testId }) {
  return (
    <div className="border-t border-helm-line pt-3" data-testid={testId}>
      <p className="text-xs text-helm-muted">{label}</p>
      <p className={cn(
        "mt-1 font-display tracking-tight tabular-nums",
        display.missing ? "text-lg text-helm-muted" : "text-2xl text-helm-fg",
      )}>
        {display.value}
      </p>
      {display.note ? <p className="mt-0.5 text-xs text-helm-muted">{display.note}</p> : null}
      {delta ? <p className="mt-1 text-xs text-helm-muted tabular-nums">{delta}</p> : null}
    </div>
  );
}

function ChartTooltip({ active, payload, label, symbol }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-helm-line bg-helm-card px-3 py-2 text-xs shadow-sm">
      <p className="mb-1 text-helm-muted">{label}</p>
      {payload.filter((p) => p.value !== null && p.value !== undefined).map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-helm-fg tabular-nums">
          <span className="inline-block h-0.5 w-3" style={{ background: p.color }} aria-hidden />
          <span className="text-helm-muted">{p.name}</span>
          <span className="ml-auto pl-3">{formatMoney(p.value, symbol)}</span>
        </p>
      ))}
    </div>
  );
}

function CashChart({ series, startMonth, reserve, cashOut, symbol, theme }) {
  const data = useMemo(() => {
    const len = series[0]?.result.points.length || 0;
    const rows = [];
    for (let m = 0; m <= len; m += 1) {
      const row = { label: modelMonthLabel(startMonth, m) };
      for (const s of series) {
        row[s.key] = m === 0 ? s.cash0 : s.result.points[m - 1]?.cash ?? null;
      }
      rows.push(row);
    }
    return rows;
  }, [series, startMonth]);

  const grid = theme === "dark" ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";
  const outRow = cashOut !== null && cashOut !== undefined ? data[cashOut] : null;

  return (
    <div className="h-[300px] sm:h-[340px]" data-testid="modeling-chart" role="img" aria-label="Projected cash by month for each scenario. Exact values are in the monthly table.">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ left: 4, right: 12, top: 12, bottom: 0 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="label" stroke={palette.slate} fontSize={11} tickLine={false} axisLine={false} minTickGap={28} />
          <YAxis stroke={palette.slate} fontSize={11} tickLine={false} axisLine={false} width={56} tickFormatter={(v) => formatAxisMoney(v, { symbol })} />
          <Tooltip content={<ChartTooltip symbol={symbol} />} cursor={{ stroke: palette.slate, strokeOpacity: 0.4 }} isAnimationActive={false} />
          <Legend verticalAlign="top" align="left" height={32} iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine y={0} stroke={palette.slate} strokeOpacity={0.5} />
          {reserve !== null && reserve !== undefined ? (
            <ReferenceLine
              y={reserve}
              stroke={palette.slate}
              strokeDasharray="6 4"
              label={{ value: "Minimum reserve", position: "insideTopRight", fontSize: 11, fill: palette.slate }}
            />
          ) : null}
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.name}
              type="linear"
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dash || undefined}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--helm-card)" }}
              isAnimationActive={false}
              connectNulls={false}
            />
          ))}
          {outRow ? (
            <ReferenceDot x={outRow.label} y={0} r={5} fill={ACCENT} stroke="var(--helm-card)" strokeWidth={2} ifOverflow="extendDomain" />
          ) : null}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function MonthlyTable({ result, startMonth, symbol }) {
  return (
    <div className="overflow-x-auto" data-testid="modeling-table">
      <table className="w-full text-sm tabular-nums">
        <thead>
          <tr className="border-b border-helm-line text-left text-xs text-helm-muted">
            <th className="py-2 pr-4 font-medium">Month</th>
            <th className="py-2 pr-4 font-medium text-right">Revenue</th>
            <th className="py-2 pr-4 font-medium text-right">Expenses</th>
            <th className="py-2 pr-4 font-medium text-right">Net</th>
            <th className="py-2 font-medium text-right">Cash</th>
          </tr>
        </thead>
        <tbody>
          {result.points.map((p) => (
            <tr key={p.m} className="border-b border-helm-line/60">
              <td className="py-1.5 pr-4 text-helm-muted">{modelMonthLabel(startMonth, p.m)}</td>
              <td className="py-1.5 pr-4 text-right text-helm-fg">{formatMoney(p.revenue, symbol)}</td>
              <td className="py-1.5 pr-4 text-right text-helm-fg">{formatMoney(p.expenses, symbol)}</td>
              <td className="py-1.5 pr-4 text-right text-helm-fg">{formatMoney(p.net, symbol)}</td>
              <td className={cn("py-1.5 text-right", p.cash !== null && p.cash < 0 ? "text-helm-status-negative" : "text-helm-fg")}>
                {p.cash === null ? "Add cash balance" : formatMoney(p.cash, symbol)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Results({ result, base, baseline, symbol, series, reserve, showTable, setShowTable, example }) {
  const start = baseline.start_month;
  const noLedger = result.runway_status === "no_ledger";
  const noCash = result.runway_status === "no_cash";
  const breach = result.reserve_breach_month;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-x-6 gap-y-5 xl:grid-cols-4" data-testid="modeling-results">
        <ResultCard testId="result-runway" label="Runway" display={runwayDisplay(result)} delta={runwayDelta(result, base)} />
        <ResultCard
          testId="result-cashout"
          label="Cash runs out"
          display={{
            ...cashOutDisplay(result, start),
            note: breach !== null && reserve !== null
              ? `Below reserve from ${modelMonthLabel(start, breach)}`
              : undefined,
          }}
        />
        <ResultCard testId="result-breakeven" label="Break-even" display={breakEvenDisplay(result, start)} delta={breakEvenDelta(result, base)} />
        <ResultCard testId="result-ending" label={`Cash after ${result.horizon} months`} display={endingCashDisplay(result, symbol)} delta={endingCashDelta(result, base, symbol)} />
      </div>

      <div className="rounded-md border border-helm-line bg-helm-card p-4 sm:p-5">
        {noLedger ? (
          <div className="flex h-[260px] flex-col items-center justify-center text-center" data-testid="modeling-empty-ledger">
            <p className="text-sm text-helm-fg">Add revenue or expenses to model your runway.</p>
            <p className="mt-1 max-w-sm text-xs text-helm-muted">The model starts from your last three months in Financials. There is nothing to start from yet.</p>
            <Link to="/app/financials" className="mt-3 text-sm text-helm-gold hover:text-helm-gold-hover">Open Financials</Link>
          </div>
        ) : noCash ? (
          <div className="flex h-[260px] flex-col items-center justify-center text-center" data-testid="modeling-empty-cash">
            <p className="text-sm text-helm-fg">Add your cash balance in Financials to see runway.</p>
            <p className="mt-1 max-w-sm text-xs text-helm-muted">Break-even is still shown above, because it only depends on revenue and expenses.</p>
            <Link to="/app/financials" className="mt-3 text-sm text-helm-gold hover:text-helm-gold-hover">Add cash balance</Link>
          </div>
        ) : (
          <CashChart
            series={series}
            startMonth={start}
            reserve={reserve}
            cashOut={result.cash_out_month}
            symbol={symbol}
            theme={series.theme}
          />
        )}
        <p className="mt-3 text-xs text-helm-muted">
          {example
            ? "Example numbers for illustration. Not your data."
            : "Projection from your assumptions and your last 3 months of data. It is not a forecast."}
        </p>
      </div>

      {!noLedger ? (
        <div>
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            aria-expanded={showTable}
            data-testid="toggle-table"
            className="inline-flex items-center gap-1.5 text-sm text-helm-muted hover:text-helm-fg"
          >
            <Table2 className="h-4 w-4" /> {showTable ? "Hide monthly table" : "Show monthly table"}
          </button>
          {showTable ? <div className="mt-3"><MonthlyTable result={result} startMonth={start} symbol={symbol} /></div> : null}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ dialogs */

function NameDialog({ title, initial, confirmLabel, onSubmit, onClose }) {
  const [name, setName] = useState(initial || "");
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
    const onKey = (e) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);
  const trimmed = name.replace(/\s+/g, " ").trim();
  const submit = async (e) => {
    e.preventDefault();
    if (!trimmed || busy) return;
    setBusy(true);
    const ok = await onSubmit(trimmed);
    if (!ok) setBusy(false);
  };
  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="name-dialog-title" data-testid="scenario-name-dialog">
      <div className="absolute inset-0 bg-helm-ink/70" onClick={() => !busy && onClose()} aria-hidden="true" />
      <form onSubmit={submit} className="relative w-full max-w-sm rounded-md border border-helm-line bg-helm-card p-5 shadow-xl">
        <p id="name-dialog-title" className="text-sm font-medium text-helm-fg">{title}</p>
        <input
          ref={ref}
          value={name}
          maxLength={MAX_LABEL_LEN}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Hire two engineers in Q1"
          data-testid="scenario-name-input"
          className="mt-3 w-full rounded-md border border-helm-line bg-helm-bg px-3 py-2 text-sm text-helm-fg focus:outline-none focus:border-helm-gold/50"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={busy} className="rounded-md border border-helm-line px-3 py-2 text-sm text-helm-fg hover:bg-helm-fg/[0.04]">Cancel</button>
          <button type="submit" disabled={!trimmed || busy} data-testid="scenario-name-submit" className="rounded-md bg-helm-gold px-3 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover disabled:opacity-40">
            {busy ? "Saving…" : confirmLabel}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

/* ------------------------------------------------------------------ scenario bar */

function ScenarioBar({
  scenarios, activeId, onSelect, dirty, onSave, onSaveAs, onRename, onDuplicate, onDelete, onReset,
  compare, onToggleCompare, busy, cap,
}) {
  const [menu, setMenu] = useState(false);
  const menuRef = useRef(null);
  useEffect(() => {
    if (!menu) return undefined;
    const close = (e) => { if (!menuRef.current?.contains(e.target)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  const isBaseline = activeId === BASELINE_ID;
  const options = [{ id: BASELINE_ID, name: "Current trajectory" }, ...scenarios.map((s) => ({ id: s.scenario_id, name: s.name }))];
  // In the select, the baseline entry is where new scenarios start from.
  const selectOptions = [{ id: BASELINE_ID, name: "New scenario from current trajectory" }, ...options.slice(1)];
  const compareOptions = options.filter((o) => o.id === BASELINE_ID || o.id !== activeId);
  const atCap = scenarios.length >= cap;

  return (
    <div className="border-y border-helm-line py-3" data-testid="scenario-bar">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:flex-none">
          <select
            aria-label="Scenario"
            value={activeId}
            onChange={(e) => onSelect(e.target.value)}
            data-testid="scenario-select"
            className="w-full appearance-none rounded-md border border-helm-line bg-helm-bg py-2 pl-3 pr-8 text-sm text-helm-fg focus:outline-none focus:border-helm-gold/50 sm:w-72"
          >
            {selectOptions.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-helm-muted" />
        </div>
        {dirty ? <span className="text-xs text-helm-muted" data-testid="unsaved-indicator">Unsaved changes</span> : null}
        <div className="ml-auto flex items-center gap-2">
          {dirty ? (
            <button type="button" onClick={onReset} disabled={busy} className="rounded-md px-2.5 py-2 text-sm text-helm-muted hover:text-helm-fg" data-testid="scenario-reset">
              {isBaseline ? "Reset" : "Discard changes"}
            </button>
          ) : null}
          {isBaseline ? (
            <button type="button" onClick={onSaveAs} disabled={busy || atCap || !dirty} data-testid="scenario-save-as" title={atCap ? `Up to ${cap} scenarios` : undefined}
              className="rounded-md bg-helm-gold px-3 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover disabled:opacity-40">
              Save as scenario
            </button>
          ) : (
            <button type="button" onClick={onSave} disabled={busy || !dirty} data-testid="scenario-save"
              className="rounded-md bg-helm-gold px-3 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover disabled:opacity-40">
              Save
            </button>
          )}
          {!isBaseline ? (
            <div className="relative" ref={menuRef}>
              <button type="button" onClick={() => setMenu((m) => !m)} aria-label="More scenario actions" aria-expanded={menu} data-testid="scenario-more"
                className="rounded-md border border-helm-line p-2 text-helm-muted hover:text-helm-fg">
                <MoreHorizontal className="h-4 w-4" />
              </button>
              {menu ? (
                <div className="absolute right-0 z-30 mt-1 w-44 overflow-hidden rounded-md border border-helm-line bg-helm-card py-1 shadow-lg" role="menu">
                  {[
                    ["Save as new", onSaveAs, atCap],
                    ["Rename", onRename, false],
                    ["Duplicate", onDuplicate, atCap],
                    ["Delete", onDelete, false],
                  ].map(([lbl, fn, off]) => (
                    <button key={lbl} type="button" role="menuitem" disabled={off || busy}
                      onClick={() => { setMenu(false); fn(); }}
                      className={cn("block w-full px-3 py-2 text-left text-sm hover:bg-helm-fg/[0.04] disabled:opacity-40", lbl === "Delete" ? "text-helm-status-negative" : "text-helm-fg")}>
                      {lbl}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      {compareOptions.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs" data-testid="compare-row">
          <span className="text-helm-muted">Compare with</span>
          {compareOptions.map((o) => {
            const on = compare.includes(o.id);
            const full = !on && compare.length >= MAX_COMPARE;
            return (
              <button key={o.id} type="button" aria-pressed={on} disabled={full}
                onClick={() => onToggleCompare(o.id)}
                title={full ? `Up to ${MAX_COMPARE} comparisons` : undefined}
                data-testid={`compare-${o.id}`}
                className={cn("rounded-full border px-2.5 py-1 transition-colors disabled:opacity-40",
                  on ? "border-helm-gold bg-helm-gold text-helm-navy" : "border-helm-line text-helm-muted hover:text-helm-fg")}>
                {o.name}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ layout */

function ModelingLayout({ controls, results, summary }) {
  const [sheet, setSheet] = useState(false);
  useEffect(() => {
    if (!sheet) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setSheet(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheet]);

  return (
    <>
      {/* Mobile: summary pinned under the app header. */}
      <div className="sticky top-14 z-20 -mx-4 mb-4 border-b border-helm-line bg-helm-bg/95 px-4 py-2 backdrop-blur lg:hidden" data-testid="modeling-summary-strip">
        {summary}
      </div>
      <div className="grid gap-8 lg:grid-cols-[340px_1fr] xl:grid-cols-[360px_1fr]">
        <aside className="hidden lg:block">
          <div className="sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto pr-2">{controls}</div>
        </aside>
        <div className="min-w-0 pb-24 lg:pb-0">{results}</div>
      </div>
      {/* Mobile: controls live in a bottom sheet. */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-helm-line bg-helm-bg/95 p-3 backdrop-blur lg:hidden">
        <button type="button" onClick={() => setSheet(true)} data-testid="open-controls"
          className="flex w-full items-center justify-center gap-2 rounded-md bg-helm-gold py-2.5 text-sm font-medium text-helm-navy">
          <SlidersHorizontal className="h-4 w-4" /> Adjust assumptions
        </button>
      </div>
      {sheet ? createPortal(
        <div className="fixed inset-0 z-[90] lg:hidden" role="dialog" aria-modal="true" aria-label="Assumptions">
          <div className="absolute inset-0 bg-helm-ink/60" onClick={() => setSheet(false)} aria-hidden="true" />
          <div className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-xl border-t border-helm-line bg-helm-bg px-4 pb-8 pt-3">
            <div className="sticky top-0 -mx-4 mb-4 flex items-center justify-between border-b border-helm-line bg-helm-bg px-4 pb-3">
              <p className="text-sm font-medium text-helm-fg">Assumptions</p>
              <button type="button" onClick={() => setSheet(false)} className="text-sm text-helm-gold">Done</button>
            </div>
            {summary ? <div className="mb-5 rounded-md border border-helm-line px-3 py-2">{summary}</div> : null}
            {controls}
          </div>
        </div>,
        document.body,
      ) : null}
    </>
  );
}

function SummaryStrip({ result, symbol }) {
  const rw = runwayDisplay(result);
  const end = endingCashDisplay(result, symbol);
  return (
    <div className="flex items-center justify-between gap-4 text-sm tabular-nums">
      <span><span className="text-helm-muted">Runway </span><span className="text-helm-fg">{rw.value}</span></span>
      <span><span className="text-helm-muted">Ending cash </span><span className="text-helm-fg">{end.value}</span></span>
    </div>
  );
}

function useSeries(result, compareResults, theme, cash0) {
  return useMemo(() => {
    const start = cash0 === undefined ? null : cash0;
    const colors = COMPARE_COLORS[theme === "dark" ? "dark" : "light"];
    const list = [{ key: "active", name: result.name || "This scenario", color: ACCENT, result, cash0: start }];
    compareResults.forEach((c, i) => {
      list.push({
        key: `cmp_${i}`,
        name: c.name,
        color: c.id === BASELINE_ID ? palette.slate : colors[i % colors.length],
        dash: c.id === BASELINE_ID ? "6 4" : COMPARE_DASH[i % COMPARE_DASH.length],
        result: c.result,
        cash0: start,
      });
    });
    list.theme = theme;
    return list;
  }, [result, compareResults, theme, cash0]);
}

function PageSkeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-[340px_1fr]" aria-hidden data-testid="modeling-skeleton">
      <div className="hidden space-y-6 lg:block">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
      </div>
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-6 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
        <Skeleton className="h-[340px] w-full" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ locked preview */

const EXAMPLE_BASELINE = {
  cash: 250000, revenue: 18000, expenses: 32000, min_cash_reserve: 60000,
};
const EXAMPLE_INPUTS = {
  horizon: 24, revenue_growth_pct: 6, expense_growth_pct: 1, min_cash_reserve: 60000,
  hires: [{ label: "Engineer", monthly_cost: 6000, start_month: 3 }],
  events: [{ label: "Seed round", amount: 400000, month: 8 }],
};

function LockedPreview({ access, theme }) {
  const start = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  }, []);
  const baseline = { ...EXAMPLE_BASELINE, start_month: start };
  const result = useMemo(() => ({ ...projectCash(EXAMPLE_INPUTS, baseline), name: "Example scenario" }), [baseline.start_month]); // eslint-disable-line react-hooks/exhaustive-deps
  const base = useMemo(() => projectCash(baselineInputs(EXAMPLE_INPUTS), baseline), [baseline.start_month]); // eslint-disable-line react-hooks/exhaustive-deps
  const compareResults = useMemo(() => [{ id: BASELINE_ID, name: "Current trajectory", result: base }], [base]);
  const series = useSeries(result, compareResults, theme, baseline.cash);
  const [showTable, setShowTable] = useState(false);

  return (
    <div data-testid="modeling-locked">
      <div className="mb-8 rounded-md border border-helm-line bg-helm-card p-5 sm:flex sm:items-center sm:justify-between sm:gap-6" data-testid="modeling-upgrade-card">
        <div className="flex items-start gap-3">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-helm-muted" aria-hidden />
          <div>
            <p className="text-sm font-medium text-helm-fg">Financial Modeling is included in Growth and Business</p>
            <p className="mt-1 max-w-xl text-sm text-helm-muted">
              Test hires, growth and funding against your real numbers, save scenarios and compare them side by side. Below is an example with made-up numbers.
            </p>
          </div>
        </div>
        {access?.can_manage_billing ? (
          <Link to="/app/billing" data-testid="modeling-upgrade-btn"
            className="mt-4 inline-flex shrink-0 rounded-md bg-helm-gold px-4 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover sm:mt-0">
            See plans
          </Link>
        ) : (
          <p className="mt-4 shrink-0 text-sm text-helm-muted sm:mt-0">Ask a workspace owner to upgrade.</p>
        )}
      </div>
      <span className="mb-4 inline-block rounded border border-helm-line px-2 py-0.5 text-[11px] uppercase tracking-wider text-helm-muted">Example data</span>
      <div className="grid gap-8 lg:grid-cols-[340px_1fr] xl:grid-cols-[360px_1fr]">
        <aside className="pointer-events-none hidden select-none blur-[1.5px] lg:block" aria-hidden="true">
          <Controls inputs={sanitizeInputs(EXAMPLE_INPUTS)} setInputs={() => {}} baseline={baseline} symbol="$" disabled />
        </aside>
        <div className="min-w-0">
          <Results
            result={result} base={base} baseline={baseline} symbol="$" series={series}
            reserve={EXAMPLE_INPUTS.min_cash_reserve} showTable={showTable} setShowTable={setShowTable} example
          />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ page */

function ModelingWorkspace({ theme }) {
  const baselineQ = useFetch("/modeling/baseline");
  const scenariosQ = useFetch("/modeling/scenarios");
  const [baselineOverride, setBaselineOverride] = useState(null);
  const baseline = baselineOverride || baselineQ.data;
  const scenarios = useMemo(() => scenariosQ.data?.scenarios || [], [scenariosQ.data]);
  const cap = scenariosQ.data?.cap || 20;

  const [activeId, setActiveId] = useState(BASELINE_ID);
  const [draft, setDraft] = useState(null);
  const [compare, setCompare] = useState([BASELINE_ID]);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reserveBusy, setReserveBusy] = useState(false);
  const [showTable, setShowTable] = useState(false);

  const savedInputs = useMemo(() => {
    if (!baseline) return null;
    if (activeId === BASELINE_ID) return defaultInputs(baseline);
    const s = scenarios.find((x) => x.scenario_id === activeId);
    return s ? sanitizeInputs(s.inputs) : defaultInputs(baseline);
  }, [activeId, scenarios, baseline]);

  useEffect(() => {
    if (savedInputs && draft === null) setDraft(savedInputs);
  }, [savedInputs, draft]);

  // A deleted or missing scenario falls back to the baseline.
  useEffect(() => {
    if (activeId !== BASELINE_ID && scenariosQ.data && !scenarios.some((s) => s.scenario_id === activeId)) {
      setActiveId(BASELINE_ID);
      setDraft(null);
    }
  }, [activeId, scenarios, scenariosQ.data]);

  const inputs = draft || savedInputs;
  const deferredInputs = useDeferredValue(inputs);
  const dirty = Boolean(inputs && savedInputs && !same(inputs, savedInputs));
  const activeName = activeId === BASELINE_ID ? "This scenario" : scenarios.find((s) => s.scenario_id === activeId)?.name || "This scenario";

  const result = useMemo(
    () => (inputs && baseline ? { ...projectCash(inputs, baseline), name: activeName } : null),
    [inputs, baseline, activeName],
  );
  const base = useMemo(
    () => (inputs && baseline ? projectCash(baselineInputs(inputs), baseline) : null),
    [inputs, baseline],
  );
  // The chart reads deferred values so a fast slider drag never waits on it.
  const chartResult = useMemo(
    () => (deferredInputs && baseline ? { ...projectCash(deferredInputs, baseline), name: activeName } : null),
    [deferredInputs, baseline, activeName],
  );
  const compareResults = useMemo(() => {
    if (!baseline || !deferredInputs) return [];
    return compare
      .filter((id) => id === BASELINE_ID || id !== activeId)
      .map((id) => {
        if (id === BASELINE_ID) {
          return { id, name: "Current trajectory", result: projectCash(baselineInputs(deferredInputs), baseline) };
        }
        const s = scenarios.find((x) => x.scenario_id === id);
        if (!s) return null;
        // Compared scenarios share this view's horizon so lines line up.
        return { id, name: s.name, result: projectCash({ ...s.inputs, horizon: deferredInputs.horizon }, baseline) };
      })
      .filter(Boolean);
  }, [compare, activeId, scenarios, baseline, deferredInputs]);
  const series = useSeries(chartResult || result || { points: [] }, compareResults, theme, baseline?.cash ?? null);

  const setInputs = useCallback((updater) => {
    setDraft((prev) => (typeof updater === "function" ? updater(prev) : updater));
  }, []);

  const confirmDiscard = async () => {
    if (!dirty) return true;
    return confirmAction({
      title: "Discard unsaved changes?",
      description: "Your changes to this scenario have not been saved.",
      confirmLabel: "Discard",
      destructive: true,
    });
  };

  const select = async (id) => {
    if (id === activeId) return;
    if (!(await confirmDiscard())) return;
    setActiveId(id);
    setDraft(null);
    setCompare((c) => c.filter((x) => x === BASELINE_ID || x !== id));
  };

  const toggleCompare = (id) => {
    setCompare((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= MAX_COMPARE ? c : [...c, id]));
  };

  const errMsg = (e, fallback) => {
    const d = e?.response?.data?.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d[0]?.msg?.replace(/^Value error, /, "") || fallback;
    return d?.message || fallback;
  };

  const createScenario = async (name, body) => {
    try {
      const { data } = await api.post("/modeling/scenarios", { name, inputs: body });
      await scenariosQ.reload();
      setActiveId(data.scenario_id);
      setDraft(null);
      toast.success("Scenario saved");
      return true;
    } catch (e) {
      toast.error(errMsg(e, "Could not save scenario"));
      return false;
    }
  };

  const updateScenario = async (patch) => {
    const s = scenarios.find((x) => x.scenario_id === activeId);
    if (!s) return false;
    setBusy(true);
    try {
      await api.put(`/modeling/scenarios/${activeId}`, { name: patch.name ?? s.name, inputs: patch.inputs ?? s.inputs });
      await scenariosQ.reload();
      if (patch.inputs) setDraft(null);
      toast.success(patch.name ? "Scenario renamed" : "Scenario saved");
      return true;
    } catch (e) {
      toast.error(errMsg(e, "Could not save scenario"));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const del = async () => {
    const s = scenarios.find((x) => x.scenario_id === activeId);
    if (!s) return;
    const ok = await confirmAction({ title: `Delete "${s.name}"?`, description: "This removes the saved scenario. Your financial data is not affected.", confirmLabel: "Delete", destructive: true });
    if (!ok) return;
    setBusy(true);
    try {
      await api.delete(`/modeling/scenarios/${activeId}`);
      setActiveId(BASELINE_ID);
      setDraft(null);
      setCompare((c) => c.filter((x) => x !== s.scenario_id));
      await scenariosQ.reload();
      toast.success("Scenario deleted");
    } catch (e) {
      toast.error(errMsg(e, "Could not delete scenario"));
    } finally {
      setBusy(false);
    }
  };

  const saveReserve = async (value) => {
    setReserveBusy(true);
    try {
      const { data } = await api.put("/financials/min-reserve", { value });
      setBaselineOverride({ ...baseline, min_cash_reserve: data.min_cash_reserve });
      toast.success(value === null ? "Company reserve cleared" : "Company reserve updated. Runway alerts will use it.");
    } catch (e) {
      toast.error(errMsg(e, "Could not update the reserve"));
    } finally {
      setReserveBusy(false);
    }
  };

  if (baselineQ.error || scenariosQ.error) {
    return (
      <ErrorScreen
        label="Could not load Financial Modeling"
        message={fetchErrorMessage(baselineQ.error || scenariosQ.error)}
        onRetry={() => { baselineQ.reload(); scenariosQ.reload(); }}
      />
    );
  }
  if (!baseline || !inputs || !result || !base || scenariosQ.loading) return <PageSkeleton />;

  const symbol = baseline.currency_symbol || "$";
  const startingFacts = (
    <p className="mb-5 text-xs text-helm-muted" data-testid="modeling-baseline-facts">
      Starting point:{" "}
      <span className="text-helm-fg tabular-nums">{baseline.cash === null ? "cash not entered" : `${formatMoney(baseline.cash, symbol)} cash`}</span>
      {baseline.revenue !== null ? (
        <>
          {", "}
          <span className="text-helm-fg tabular-nums">{formatMoney(baseline.revenue, symbol)}</span>/mo revenue and{" "}
          <span className="text-helm-fg tabular-nums">{formatMoney(baseline.expenses, symbol)}</span>/mo expenses, averaged over{" "}
          {baseline.months_used.length === 1 ? monthLabel(baseline.months_used[0]) : `${monthLabel(baseline.months_used[0])} to ${monthLabel(baseline.months_used[baseline.months_used.length - 1])}`}
          {baseline.months_used.length < 3 ? " (limited history)" : ""}.
        </>
      ) : ". No revenue or expenses logged yet."}
    </p>
  );

  const controls = (
    <Controls
      inputs={inputs}
      setInputs={setInputs}
      baseline={baseline}
      symbol={symbol}
      onSaveReserve={saveReserve}
      reserveBusy={reserveBusy}
    />
  );

  const results = (
    <>
      {startingFacts}
      <Results
        result={result}
        base={base}
        baseline={baseline}
        symbol={symbol}
        series={series}
        reserve={inputs.min_cash_reserve}
        showTable={showTable}
        setShowTable={setShowTable}
      />
    </>
  );

  return (
    <>
      <div className="mb-6">
        <ScenarioBar
          scenarios={scenarios}
          activeId={activeId}
          onSelect={select}
          dirty={dirty}
          busy={busy}
          cap={cap}
          onSave={() => updateScenario({ inputs })}
          onSaveAs={() => setDialog({ kind: "new" })}
          onRename={() => setDialog({ kind: "rename" })}
          onDuplicate={() => setDialog({ kind: "duplicate" })}
          onDelete={del}
          onReset={() => setDraft(savedInputs)}
          compare={compare.filter((id) => id === BASELINE_ID || id !== activeId)}
          onToggleCompare={toggleCompare}
        />
      </div>
      <ModelingLayout controls={controls} results={results} summary={<SummaryStrip result={result} symbol={symbol} />} />
      {dialog ? (
        <NameDialog
          title={dialog.kind === "rename" ? "Rename scenario" : dialog.kind === "duplicate" ? "Duplicate scenario" : "Save as a new scenario"}
          confirmLabel={dialog.kind === "rename" ? "Rename" : "Save"}
          initial={
            dialog.kind === "rename" ? activeName
              : dialog.kind === "duplicate" ? `Copy of ${activeName}`.slice(0, MAX_LABEL_LEN)
                : ""
          }
          onClose={() => setDialog(null)}
          onSubmit={async (name) => {
            let ok;
            if (dialog.kind === "rename") ok = await updateScenario({ name });
            else if (dialog.kind === "duplicate") {
              const s = scenarios.find((x) => x.scenario_id === activeId);
              ok = await createScenario(name, s ? s.inputs : inputs);
            } else ok = await createScenario(name, inputs);
            if (ok) setDialog(null);
            return ok;
          }}
        />
      ) : null}
    </>
  );
}

export default function FinancialModeling() {
  const { resolvedTheme } = useTheme();
  const access = useFetch("/modeling/access");
  const theme = resolvedTheme === "dark" ? "dark" : "light";

  let body;
  if (access.loading || !access.data) {
    body = access.error ? (
      <ErrorScreen label="Could not load Financial Modeling" message={fetchErrorMessage(access.error)} onRetry={access.reload} />
    ) : <PageSkeleton />;
  } else if (access.data.allowed) {
    body = <ModelingWorkspace theme={theme} />;
  } else if (access.data.reason === "plan") {
    body = <LockedPreview access={access.data} theme={theme} />;
  } else {
    body = (
      <div className="rounded-md border border-helm-line bg-helm-card p-6 text-sm text-helm-muted" data-testid="modeling-no-permission">
        Financial Modeling uses your company&apos;s financial data. Ask a workspace owner for Financials access.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Financial Modeling"
        subtitle="Test hires, growth and funding against your real numbers. Nothing here changes your books."
      />
      {body}
    </div>
  );
}

