import { AlertTriangle, Lock, Puzzle } from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { GlassCard, SectionLabel } from "@/components/kit";
import { cn } from "@/lib/utils";
import { ACCENT } from "@/lib/accent";
import { currencySymbol } from "@/lib/money";
import { formatAxisMoney } from "@/lib/formatAxisMoney";
import { useTheme } from "@/context/ThemeContext";
import palette from "@/design/palette.json";
import { bespokeComponent } from "@/components/custom/bespoke";

const WIDTH_CLASS = {
  1: "md:col-span-1",
  2: "md:col-span-2",
  3: "md:col-span-3",
};

const TONE_CLASS = {
  positive: "text-emerald-600 dark:text-emerald-400",
  negative: "text-red-600 dark:text-red-400",
  warning: "text-amber-600 dark:text-amber-400",
  neutral: "text-helm-fg",
};

function Muted({ children, icon: Icon }) {
  return (
    <p className="flex items-center gap-2 text-sm text-helm-muted">
      {Icon ? <Icon className="h-4 w-4 shrink-0" /> : null}
      {children}
    </p>
  );
}

function StateNote({ state }) {
  if (state === "restricted") {
    return <Muted icon={Lock}>Your access does not include Financials.</Muted>;
  }
  if (state === "error") {
    return <Muted icon={AlertTriangle}>Could not load this right now.</Muted>;
  }
  if (state === "not_entered") {
    return <Muted>Not entered in Trenston yet.</Muted>;
  }
  return null;
}

function BigFigure({ value, tone = "neutral", caption }) {
  return (
    <div>
      <p className={cn("text-3xl font-semibold tracking-tight tabular-nums", TONE_CLASS[tone] || TONE_CLASS.neutral)}>
        {value}
      </p>
      {caption ? <p className="mt-1 text-xs text-helm-muted">{caption}</p> : null}
    </div>
  );
}

function FinancialKpi({ widget }) {
  const d = widget.data || {};
  if (d.state === "restricted" || d.state === "error" || d.state === "not_entered" || !d.display) {
    return <StateNote state={d.state === "ok" ? "not_entered" : d.state || "not_entered"} />;
  }
  return <BigFigure value={d.display} />;
}

function RevenueExpensesChart({ widget }) {
  const { resolvedTheme } = useTheme();
  const d = widget.data || {};
  if (d.state !== "ok") return <StateNote state={d.state} />;
  const dark = resolvedTheme === "dark";
  const axis = dark ? "rgba(244, 244, 244, 0.5)" : palette.slate;
  const grid = dark ? "rgba(244, 244, 244, 0.06)" : "rgba(10, 10, 10, 0.06)";
  const symbol = currencySymbol(d.currency);
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={d.months} margin={{ left: -8, right: 8, top: 8 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="month" stroke={axis} fontSize={11} tickLine={false} axisLine={false} />
        <YAxis
          stroke={axis} fontSize={11} tickLine={false} axisLine={false} width={52}
          tickFormatter={(v) => formatAxisMoney(v, { symbol })}
        />
        <Tooltip formatter={(v) => formatAxisMoney(v, { symbol })} />
        <Area type="monotone" dataKey="revenue" name="Revenue" stroke={ACCENT} strokeWidth={2} fill={ACCENT} fillOpacity={0.08} />
        <Area type="monotone" dataKey="expenses" name="Expenses" stroke={axis} strokeWidth={1.5} fill="none" strokeDasharray="4 4" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function Rows({ items, render, empty }) {
  if (!items?.length) return <Muted>{empty}</Muted>;
  return <ul className="divide-y divide-helm-line">{items.map(render)}</ul>;
}

function TasksSummary({ widget }) {
  const d = widget.data || {};
  if (d.state !== "ok") return <StateNote state={d.state} />;
  return (
    <div className="space-y-4">
      <div className="flex gap-8">
        <BigFigure value={d.open} caption="Open" />
        <BigFigure value={d.overdue} caption="Overdue" tone={d.overdue ? "negative" : "neutral"} />
      </div>
      {widget.params?.limit ? (
        <Rows
          items={d.items}
          empty="Nothing open."
          render={(t, i) => (
            <li key={i} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="min-w-0 truncate text-helm-fg">{t.title}</span>
              <span className={cn("shrink-0 font-mono text-xs", t.overdue ? "text-red-600 dark:text-red-400" : "text-helm-muted")}>
                {t.overdue ? "Overdue" : t.due || t.status || ""}
              </span>
            </li>
          )}
        />
      ) : null}
    </div>
  );
}

function DecisionsOpen({ widget }) {
  const d = widget.data || {};
  if (d.state !== "ok") return <StateNote state={d.state} />;
  return (
    <div className="space-y-3">
      <BigFigure value={d.open} caption="Waiting on a decision" />
      {widget.params?.limit ? (
        <Rows
          items={d.items}
          empty="No open decisions."
          render={(item, i) => (
            <li key={i} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="min-w-0 truncate text-helm-fg">{item.title}</span>
              <span className="shrink-0 text-xs text-helm-muted">{item.owner || item.category || ""}</span>
            </li>
          )}
        />
      ) : null}
    </div>
  );
}

function BriefingHeadline({ widget }) {
  const d = widget.data || {};
  if (d.state !== "ok") return <StateNote state={d.state} />;
  if (!d.headline) return <Muted>The briefing fills in once your company data is in Trenston.</Muted>;
  return (
    <div>
      <p className="text-lg font-medium leading-snug text-helm-fg">{d.headline}</p>
      {d.summary ? <p className="mt-2 text-sm leading-relaxed text-helm-muted">{d.summary}</p> : null}
    </div>
  );
}

function ManualKpi({ widget }) {
  const p = widget.params || {};
  return (
    <div>
      <BigFigure value={p.value} tone={p.tone} />
      {p.target ? <p className="mt-1 font-mono text-xs text-helm-muted">Target {p.target}</p> : null}
      {p.caption ? <p className="mt-2 text-sm text-helm-muted">{p.caption}</p> : null}
    </div>
  );
}

function ManualTable({ widget }) {
  const { columns = [], rows = [] } = widget.params || {};
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[320px] text-left text-sm">
        <thead>
          <tr className="border-b border-helm-line">
            {columns.map((c, i) => (
              <th key={i} className="px-1 pb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-helm-muted">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-helm-line">
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) => <td key={j} className="px-1 py-2 text-helm-fg">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length ? <Muted>No rows yet.</Muted> : null}
    </div>
  );
}

function Note({ widget }) {
  return <p className="whitespace-pre-wrap text-sm leading-relaxed text-helm-fg">{widget.params?.body}</p>;
}

function Bespoke({ widget }) {
  const id = widget.params?.component;
  const Component = bespokeComponent(id);
  if (!Component) {
    return <Muted icon={Puzzle}>This part of the dashboard is still being built.</Muted>;
  }
  return <Component props={widget.params?.props || {}} widget={widget} />;
}

const RENDERERS = {
  financial_kpi: FinancialKpi,
  revenue_expenses_chart: RevenueExpensesChart,
  tasks_summary: TasksSummary,
  decisions_open: DecisionsOpen,
  briefing_headline: BriefingHeadline,
  manual_kpi: ManualKpi,
  manual_table: ManualTable,
  note: Note,
  custom: Bespoke,
};

export function WidgetCard({ widget }) {
  const Render = RENDERERS[widget.type];
  return (
    <GlassCard
      className={cn("col-span-1 p-5", WIDTH_CLASS[widget.width] || WIDTH_CLASS[1])}
      data-testid={`custom-widget-${widget.id}`}
    >
      <SectionLabel className="mb-4">{widget.title}</SectionLabel>
      {Render ? <Render widget={widget} /> : <Muted>Unknown widget.</Muted>}
    </GlassCard>
  );
}

export default function WidgetGrid({ widgets }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3" data-testid="custom-widget-grid">
      {(widgets || []).map((w) => <WidgetCard key={w.id} widget={w} />)}
    </div>
  );
}
