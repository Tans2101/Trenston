import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  ChevronLeft, ChevronRight, Plus, Sparkles, ArrowRight, Wallet, Users,
} from "lucide-react";
import { useFetch } from "@/hooks/useFetch";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { cn } from "@/lib/utils";
import { formatAxisMoney } from "@/lib/formatAxisMoney";
import { formatMoney } from "@/lib/money";
import { useWorkspaceCurrency } from "@/hooks/useWorkspaceCurrency";
import {
  allFinanceKpisMissing,
  financialsPanelState,
  shouldShowFinanceEmptyCta,
} from "@/lib/briefingCockpit";
import palette from "@/design/palette.json";

const ASSISTANT_PROMPTS = [
  "What's my burn rate?",
  "What's my runway?",
  "Which decision should I make first?",
  "What's the single most important thing today?",
];

const METRIC_KEYS = [
  { id: "mrr", label: "Revenue", match: /mrr|revenue/i, href: "/app/financials#log-mrr" },
  { id: "burn", label: "Burn", match: /^burn/i, href: "/app/financials#log-entry" },
  { id: "runway", label: "Runway", match: /runway/i, href: "/app/financials#cash" },
  { id: "cash", label: "Cash", match: /cash/i, href: "/app/financials#cash" },
];

function spendColors(dark) {
  // Avoid cream-on-card washout in light theme (SPEND_COLORS[1] was palette.cream).
  return dark
    ? [palette.gold, palette.cream, palette.slate, palette.statusWarning, palette.ember]
    : [palette.gold, palette.slate, palette.navy, palette.statusWarning, palette.ember];
}

function pickMetric(metrics, key) {
  const def = METRIC_KEYS.find((m) => m.id === key) || METRIC_KEYS[0];
  return (metrics || []).find((m) => def.match.test(m.label || "")) || null;
}

function decisionQueueStatus(count) {
  if (count === 0) return { body: "Nothing waiting", badge: "Clear", tone: "positive" };
  if (count <= 2) return { body: `${count} open`, badge: "Good", tone: "positive" };
  return { body: `${count} open`, badge: "Busy", tone: "warning" };
}

/**
 * Briefing top viewport: Revenue / Burn / Runway side by side,
 * period comparison chart, and Assistant / Spending / Decisions columns.
 */
export default function BriefingCockpitHero({
  metrics = [],
  decisions = [],
  loading = false,
  suppressFinanceEmpty = false,
}) {
  const { user } = useAuth();
  const { resolvedTheme } = useTheme();
  const navigate = useNavigate();
  const canFin = (user?.granted_sections || []).includes("financials");
  const {
    data: fin,
    loading: finLoading,
    error: finError,
    reload: reloadFin,
  } = useFetch(canFin ? "/financials" : null);
  const { symbol: workspaceSymbol } = useWorkspaceCurrency();
  const moneySymbol = fin?.currency_symbol || workspaceSymbol;
  const [chartOffset, setChartOffset] = useState(0);
  const dark = resolvedTheme === "dark";
  const currentBar = palette.gold;
  const lastBar = dark ? "rgba(245, 240, 230, 0.35)" : `${palette.slate}66`;
  const axisStroke = dark ? "rgba(245, 240, 230, 0.55)" : palette.slate;
  const tooltipFg = dark ? palette.cream : "#111111";
  const tooltipBg = dark ? palette.inkCard : "#FFFFFF";
  const tooltipBorder = dark ? "rgba(245, 240, 230, 0.22)" : "rgba(17, 17, 17, 0.2)";
  const cursorFill = dark ? "rgba(245, 240, 230, 0.06)" : "rgba(201,162,75,0.08)";
  const swatches = spendColors(dark);

  const heroMetrics = useMemo(() => {
    if (!canFin) return [];
    const order = ["mrr", "burn", "runway"];
    return order.map((id) => {
      const def = METRIC_KEYS.find((k) => k.id === id);
      const match = pickMetric(metrics, id);
      return {
        id,
        label: def?.label || id,
        value: match?.value,
        delta: match?.delta,
        missing: match?.missing ?? !match,
        href: match?.href || def?.href || "/app/financials",
        tone: match?.tone,
      };
    });
  }, [metrics, canFin]);

  const financeEmpty = shouldShowFinanceEmptyCta({
    canFin,
    metrics,
    suppressFinanceEmpty,
  });
  // When parent suppresses the empty CTA (Ready-when-you-are), skip the KPI strip too.
  const renderKpis = canFin && !financeEmpty && !allFinanceKpisMissing(metrics);

  const chartData = useMemo(() => {
    const series = fin?.revenue_series || [];
    if (!series.length) return [];
    return series.map((row, i) => ({
      month: row.month,
      current: Number(row.revenue) || 0,
      // First month has no prior period — omit rather than fake $0.
      last: i > 0 ? Number(series[i - 1].revenue) || 0 : null,
    }));
  }, [fin]);

  const visibleChart = useMemo(() => {
    if (chartData.length <= 6) return chartData;
    const start = Math.max(0, chartData.length - 6 - chartOffset);
    const end = Math.max(6, chartData.length - chartOffset);
    return chartData.slice(start, end);
  }, [chartData, chartOffset]);

  const spendRows = useMemo(() => {
    const rows = fin?.expense_breakdown || [];
    return rows.slice(0, 5);
  }, [fin]);

  const chartState = financialsPanelState({
    canFin,
    loading: finLoading,
    error: finError,
    hasRows: visibleChart.length > 0,
  });
  const spendState = financialsPanelState({
    canFin,
    loading: finLoading,
    error: finError,
    hasRows: spendRows.length > 0,
  });

  const decisionRows = (decisions || []).slice(0, 5);
  const queueStatus = decisionQueueStatus(decisionRows.length);
  const decisionsPriority = decisionRows.length > 0;
  const openDecisionsTotal = (decisions || []).length;

  if (loading) {
    return (
      <div className="mb-8 space-y-4 animate-pulse" data-testid="briefing-cockpit-skeleton">
        <div className="h-28 rounded-xl border border-helm-line bg-helm-card shadow-sm" />
        <div className="h-56 rounded-xl border border-helm-line bg-helm-card shadow-sm" />
        <div className="grid lg:grid-cols-3 gap-4">
          <div className="h-48 rounded-xl border border-helm-line bg-helm-card shadow-sm" />
          <div className="h-48 rounded-xl border border-helm-line bg-helm-card shadow-sm" />
          <div className="h-48 rounded-xl border border-helm-line bg-helm-card shadow-sm" />
        </div>
      </div>
    );
  }

  return (
    <div className="mb-8 space-y-4 fade-up" data-testid="briefing-cockpit-hero">
      {/* A. Revenue / Burn / Runway — or empty setup when no finance data */}
      {financeEmpty ? (
        <div
          className="rounded-xl border border-helm-gold/35 bg-helm-gold/10 p-5 md:p-6 shadow-sm"
          data-testid="briefing-finance-empty"
        >
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-helm-muted mb-2">
            Get started
          </p>
          <h2 className="font-display text-xl md:text-2xl text-helm-fg tracking-tight">
            Add your numbers to unlock Briefing
          </h2>
          <p className="mt-2 text-sm text-helm-muted max-w-xl leading-relaxed">
            Revenue, burn, and runway stay empty until you log financials. Invite your team when you are ready to share the cockpit.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              data-testid="briefing-empty-add-financials"
              onClick={() => navigate("/app/financials#log-mrr")}
              className="inline-flex items-center gap-2 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover transition-colors"
            >
              <Wallet className="w-4 h-4" />
              Add financial entry
            </button>
            <button
              type="button"
              data-testid="briefing-empty-invite-team"
              onClick={() => navigate("/app/people")}
              className="inline-flex items-center gap-2 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/[0.04] transition-colors"
            >
              <Users className="w-4 h-4" />
              Invite your team
            </button>
          </div>
        </div>
      ) : renderKpis ? (
        <div className="rounded-xl border border-helm-line bg-helm-card p-5 md:p-6 shadow-sm">
          {fin?.data_as_of ? (
            <div className="flex items-center justify-end mb-4">
              <span className="inline-flex items-center rounded-full border border-helm-line px-3 py-1.5 text-xs text-helm-muted">
                As of {new Date(fin.data_as_of).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
              </span>
            </div>
          ) : null}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6" data-testid="briefing-hero-metrics">
            {heroMetrics.map((m) => (
              <div key={m.id} className="min-w-0" data-testid={`briefing-hero-metric-${m.id}`}>
                <p className="text-sm font-medium text-helm-fg">{m.label}</p>
                {m.missing ? (
                  <>
                    <p className="mt-2 font-display text-3xl md:text-4xl text-helm-muted/50 tracking-tight tabular-nums">
                      —
                    </p>
                    <button
                      type="button"
                      onClick={() => navigate(m.href)}
                      className="mt-2 inline-flex items-center gap-1 text-sm text-helm-gold hover:text-helm-gold-hover transition-colors"
                    >
                      Add data
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <p className="mt-2 font-display text-3xl md:text-4xl text-helm-fg tracking-tight tabular-nums">
                      {m.value || "—"}
                    </p>
                    <p className="mt-2 inline-flex items-center gap-1.5 text-sm text-helm-muted">
                      {m.delta != null
                        ? `${m.delta > 0 ? "+" : ""}${m.delta}% vs last period`
                        : "vs last period"}
                    </p>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* B. Chart */}
      <div className="rounded-xl border border-helm-line bg-helm-card p-5 md:p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-helm-fg">Revenue by month</p>
            <p className="mt-0.5 text-xs text-helm-muted">Current month vs the month before</p>
          </div>
          <div className="flex items-center gap-3 font-mono text-[11px] text-helm-fg shrink-0">
            <span className="inline-flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: currentBar }}
                aria-hidden
              />
              Current
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: lastBar }}
                aria-hidden
              />
              Prior
            </span>
          </div>
        </div>
        {chartState === "loading" ? (
          <div
            className="h-[220px] rounded-lg bg-helm-fg/[0.04] animate-pulse"
            data-testid="briefing-chart-loading"
            aria-hidden
          />
        ) : chartState === "error" ? (
          <div className="py-12 text-center" data-testid="briefing-chart-error">
            <p className="text-sm text-helm-muted">Could not load revenue chart.</p>
            <button
              type="button"
              onClick={() => reloadFin()}
              className="mt-2 text-xs text-helm-gold hover:text-helm-gold-hover underline underline-offset-2"
            >
              Retry
            </button>
          </div>
        ) : chartState === "ready" ? (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={visibleChart} margin={{ left: -8, right: 8, top: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--helm-line)" vertical={false} />
                <XAxis dataKey="month" stroke={axisStroke} fontSize={11} tickLine={false} axisLine={false} tick={{ fill: axisStroke }} />
                <YAxis
                  stroke={axisStroke}
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: axisStroke }}
                  tickFormatter={(v) => formatAxisMoney(v, { symbol: moneySymbol })}
                  width={48}
                />
                <Tooltip
                  cursor={{ fill: cursorFill }}
                  contentStyle={{
                    background: tooltipBg,
                    border: `1px solid ${tooltipBorder}`,
                    borderRadius: 8,
                    fontSize: 12,
                    color: tooltipFg,
                  }}
                  labelStyle={{ color: tooltipFg, fontWeight: 500 }}
                  itemStyle={{ color: tooltipFg }}
                  formatter={(value, name) => {
                    if (value == null) return ["—", name === "current" ? "Current month" : "Prior month"];
                    return [
                      typeof value === "number" ? formatMoney(Math.round(value), moneySymbol) : value,
                      name === "current" ? "Current month" : "Prior month",
                    ];
                  }}
                  labelFormatter={(label) => `${label} revenue`}
                />
                <Bar dataKey="current" name="current" fill={currentBar} radius={[4, 4, 0, 0]} />
                <Bar dataKey="last" name="last" fill={lastBar} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            {chartData.length > 6 && (
              <div className="mt-2 flex justify-end gap-1">
                <button
                  type="button"
                  aria-label="Earlier periods"
                  disabled={chartOffset >= chartData.length - 6}
                  onClick={() => setChartOffset((o) => o + 1)}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-helm-line text-helm-muted disabled:opacity-40"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  aria-label="Later periods"
                  disabled={chartOffset <= 0}
                  onClick={() => setChartOffset((o) => Math.max(0, o - 1))}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-helm-line text-helm-muted disabled:opacity-40"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </>
        ) : (
          <p className="py-12 text-center text-sm text-helm-muted">
            {canFin
              ? "Log revenue on Financials to see period comparison."
              : "Financial charts appear when you have Financials access."}
          </p>
        )}
      </div>

      {/* C. Three columns */}
      <div className="grid lg:grid-cols-3 gap-4">
        <section className="rounded-xl border border-helm-line bg-helm-card p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-helm-gold" />
            <h3 className="text-sm font-medium text-helm-fg">Assistant</h3>
          </div>
          <div className="flex flex-col gap-2">
            {ASSISTANT_PROMPTS.map((q) => (
              <button
                key={q}
                type="button"
                data-testid="briefing-ask-chip"
                onClick={() => navigate("/app/ask", { state: { prefill: q, autoSend: true } })}
                className="rounded-full border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-left text-sm text-helm-fg transition-colors hover:border-helm-gold/35 hover:bg-helm-gold/10"
              >
                {q}
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-helm-line bg-helm-card p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-helm-fg">Spending</h3>
            <span className="text-xs text-helm-muted">Share of expenses</span>
          </div>
          {spendState === "loading" ? (
            <div className="space-y-3 py-2 animate-pulse" data-testid="briefing-spend-loading">
              <div className="h-4 rounded bg-helm-fg/[0.06]" />
              <div className="h-4 rounded bg-helm-fg/[0.06]" />
              <div className="h-4 rounded bg-helm-fg/[0.06]" />
            </div>
          ) : spendState === "error" ? (
            <div className="py-6 text-center" data-testid="briefing-spend-error">
              <p className="text-sm text-helm-muted">Could not load spending.</p>
              <button
                type="button"
                onClick={() => reloadFin()}
                className="mt-2 text-xs text-helm-gold hover:text-helm-gold-hover underline underline-offset-2"
              >
                Retry
              </button>
            </div>
          ) : spendState === "ready" ? (
            <ul className="space-y-3">
              {spendRows.map((row, i) => (
                <li key={row.name} className="flex items-center gap-2.5">
                  <span
                    className="h-2.5 w-2.5 rounded-sm shrink-0"
                    style={{ background: swatches[i % swatches.length] }}
                  />
                  <span className="text-sm text-helm-fg truncate flex-1">{row.name}</span>
                  <div className="w-20 h-1.5 rounded-full bg-helm-fg/[0.06] overflow-hidden">
                    <div
                      className="h-full rounded-full bg-helm-gold"
                      style={{ width: `${Math.min(100, Number(row.value) || 0)}%` }}
                    />
                  </div>
                  <span className="font-mono text-[11px] tabular-nums text-helm-muted w-8 text-right">
                    {row.value}%
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-helm-muted py-6 text-center">
              {canFin ? "Log expenses to see category spend." : "Spending needs Financials access."}
            </p>
          )}
        </section>

        <section
          data-testid="briefing-decisions-card"
          className={cn(
            "rounded-xl border bg-helm-card p-5 shadow-sm",
            decisionsPriority
              ? "border-helm-gold/40 border-l-[3px] border-l-helm-gold bg-helm-gold/[0.06]"
              : "border-helm-line",
          )}
        >
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-helm-fg">Decisions</h3>
            <button
              type="button"
              aria-label="Add decision"
              onClick={() => navigate("/app/decisions", { state: { openAdd: true } })}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-helm-line text-helm-muted hover:bg-helm-fg/[0.04]"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>
          <div
            className={cn(
              "mb-3 rounded-lg border px-3 py-2.5 flex items-center justify-between",
              queueStatus.tone === "positive"
                ? "border-helm-status-positive/35 bg-helm-status-positive/12"
                : "border-helm-status-warning/35 bg-helm-status-warning/12",
            )}
          >
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-helm-muted">Decision queue</p>
              <p className="text-sm text-helm-fg mt-0.5">{queueStatus.body}</p>
            </div>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider",
                queueStatus.tone === "positive"
                  ? "bg-helm-status-positive/12 text-helm-status-positive"
                  : "bg-helm-status-warning/12 text-helm-status-warning",
              )}
            >
              {queueStatus.badge}
            </span>
          </div>
          {decisionRows.length > 0 ? (
            <>
              <ul className="space-y-2 max-h-40 overflow-y-auto">
                {decisionRows.map((d, i) => (
                  <li key={d.id || i}>
                    <button
                      type="button"
                      onClick={() => navigate("/app/decisions")}
                      className="w-full flex items-start justify-between gap-2 text-sm text-left rounded-md px-1 py-0.5 -mx-1 hover:bg-helm-fg/[0.04] transition-colors"
                    >
                      <div className="min-w-0">
                        <p className="text-helm-fg truncate leading-snug">{d.title || d.label || "Open decision"}</p>
                        <p className="text-[11px] text-helm-muted mt-0.5">{d.urgency || d.source || "Pending"}</p>
                      </div>
                      <span className="shrink-0 rounded-full bg-helm-status-warning/12 px-2 py-0.5 text-[10px] text-helm-status-warning">
                        Open
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {openDecisionsTotal >= 5 ? (
                <button
                  type="button"
                  onClick={() => navigate("/app/decisions")}
                  className="mt-3 text-xs text-helm-gold hover:text-helm-gold-hover"
                >
                  View all decisions
                </button>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-helm-muted text-center py-4">No open decisions right now.</p>
          )}
        </section>
      </div>
    </div>
  );
}
