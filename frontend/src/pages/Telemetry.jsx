import { useState } from "react";
import { toast } from "sonner";
import { Plus, PenLine, Sparkles } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, SectionLabel, Delta, ErrorScreen, EmptyState, SkeletonKPIRow, SkeletonChart } from "@/components/kit";
import { FunnelChart } from "@/components/charts/funnel-chart";
import {
  HeatmapCells,
  HeatmapChart,
  HeatmapInteractionBoundary,
  HeatmapInteractionProvider,
  HeatmapLegend,
  HeatmapTooltip,
  HeatmapXAxis,
  HeatmapYAxis,
  HEATMAP_DEFAULT_LEVEL_COLORS,
  HEATMAP_DEFAULT_LEVEL_STYLES,
} from "@/components/charts/heatmap";
import { cn } from "@/lib/utils";
import palette from "@/design/palette.json";

const GOLD = palette.gold;
const SLATE = palette.slate;
const CREAM = palette.cream;

function toFunnelStages(rows = []) {
  return rows.map((row) => ({
    label: row.stage,
    value: Number(row.value) || 0,
    displayValue: String(row.value ?? 0),
  }));
}

function toHeatmapColumns(columns = []) {
  return columns.map((col) => ({
    ...col,
    bins: (col.bins || []).map((bin) => ({
      ...bin,
      date: bin.date ? new Date(`${bin.date}T12:00:00`) : undefined,
    })),
  }));
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-helm-line bg-helm-card px-3 py-2 text-xs">
      {label && <p className="text-helm-muted mb-1 font-mono">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="text-helm-fg font-mono">
          <span style={{ color: p.color }}>●</span> {p.name}: {p.value}
        </p>
      ))}
    </div>
  );
}

function Sparkline({ data }) {
  const chart = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={36}>
      <LineChart data={chart}>
        <Line type="monotone" dataKey="v" stroke={GOLD} strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

const riskColor = (score) => (
  score >= 15 ? palette.statusNegative : score >= 8 ? palette.statusWarning : palette.statusPositive
);

const emptyRisk = () => ({ id: "", name: "", likelihood: 3, impact: 3, category: "General" });

export default function Telemetry() {
  const { data, loading, error, reload } = useFetch("/telemetry");
  const [editing, setEditing] = useState(false);
  const [risks, setRisks] = useState([]);
  const [notes, setNotes] = useState("");
  const [targetEnabled, setTargetEnabled] = useState(false);
  const [growthPct, setGrowthPct] = useState(3);
  const [busy, setBusy] = useState(false);

  if (error && !data) {
    return (
      <ErrorScreen
        label="Could not load telemetry"
        message={fetchErrorMessage(error, "Telemetry data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  if (loading && !data) {
    return (
      <div>
        <PageHeader title="Telemetry" subtitle="Live KPIs and growth trends from your real data." />
        <SkeletonKPIRow count={3} className="lg:grid-cols-3" />
        <div className="grid lg:grid-cols-2 gap-4 mb-6">
          <SkeletonChart />
          <SkeletonChart />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <ErrorScreen
        label="Could not load telemetry"
        message={fetchErrorMessage(error, "Telemetry data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }
  if ((data.kpis || []).length === 0) return <div><PageHeader title="Telemetry" subtitle="Live KPIs and growth trends from your real data." /><EmptyState title="No telemetry yet" body="Log financials and add your team. Your KPIs build from real data." /></div>;

  const asOf = data.data_as_of ? new Date(data.data_as_of).toLocaleString() : null;
  const canWrite = data.can_write;
  const suggestedRisks = data.suggested_risks || [];
  const hasTargetLine = (data.revenue_trend || []).some((r) => r.target != null && r.target !== undefined);
  const funnelStages = toFunnelStages(data.funnel);
  const activityTotal = data.activity_heatmap?.total ?? 0;
  const heatmapColumns = toHeatmapColumns(data.activity_heatmap?.columns || []);

  const openEdit = (seedRisk = null) => {
    const base = (data.risks || []).length ? data.risks.map((r) => ({ ...r })) : [];
    if (seedRisk) {
      base.push({
        ...emptyRisk(),
        name: seedRisk.name || "",
        category: seedRisk.category || "General",
        likelihood: 3,
        impact: 3,
      });
    }
    setRisks(base.length ? base : [{ ...emptyRisk() }]);
    setNotes(data.notes || "");
    setTargetEnabled(!!data.targets?.enabled);
    setGrowthPct(
      data.targets?.monthly_growth_pct != null && data.targets.monthly_growth_pct !== ""
        ? Number(data.targets.monthly_growth_pct)
        : 3,
    );
    setEditing(true);
  };

  const saveTelemetry = async () => {
    setBusy(true);
    try {
      await api.patch("/telemetry", {
        risks: risks.filter((r) => r.name?.trim()),
        notes: notes.trim(),
        targets: {
          enabled: !!targetEnabled,
          monthly_growth_pct: Number.isFinite(Number(growthPct)) ? Number(growthPct) : 0,
        },
      });
      toast.success("Telemetry updated");
      setEditing(false);
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Telemetry"
        subtitle="Live KPIs from your integrated sources: financials, pipeline, people, and tasks."
        action={canWrite ? (
          <button type="button" onClick={() => openEdit()} className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10">
            <PenLine className="w-3.5 h-3.5" /> Edit telemetry
          </button>
        ) : null}
      />

      {data.sources?.length > 0 && (
        <GlassCard className="p-4 mb-6 fade-up" data-testid="telemetry-sources">
          <SectionLabel className="mb-2">Data sources</SectionLabel>
          {asOf && <p className="text-[11px] font-mono text-helm-muted mb-3">As of {asOf}</p>}
          <div className="flex flex-wrap gap-2">
            {data.sources.map((s) => (
              <span key={s.label} className="inline-flex flex-col rounded-md border border-helm-line bg-helm-fg/[0.02] px-3 py-2 text-left">
                <span className="text-xs text-helm-fg">{s.label}</span>
                <span className="text-[10px] text-helm-muted">{s.detail}</span>
                <span className={cn("text-[9px] font-mono uppercase mt-1", s.freshness === "live" ? "text-helm-status-positive" : s.freshness === "hourly" ? "text-helm-muted" : "text-helm-status-warning")}>{s.freshness}</span>
              </span>
            ))}
          </div>
        </GlassCard>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {data.kpis.map((k, i) => (
          <GlassCard key={k.label} className="p-4 fade-up" style={{ animationDelay: `${i * 50}ms` }} data-testid={`kpi-${i}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">{k.label}</span>
              <Delta value={k.delta} tone={k.tone} />
            </div>
            <span className="font-mono text-3xl text-helm-fg">{k.value}</span>
            <div className="mt-2 -mx-1"><Sparkline data={k.spark} /></div>
          </GlassCard>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-6">
        <GlassCard className="p-5 fade-up">
          <SectionLabel className="mb-4">{hasTargetLine ? "MRR vs Target" : "MRR"}</SectionLabel>
          {(data.revenue_trend || []).length === 0 ? (
            <p className="text-sm text-helm-muted py-10 text-center">No revenue series yet. Add financial entries to plot MRR.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={data.revenue_trend} margin={{ left: -18, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="mrr" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={GOLD} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={GOLD} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={SLATE} strokeOpacity={0.25} vertical={false} />
                <XAxis dataKey="month" stroke={SLATE} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke={SLATE} fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip />} />
                {hasTargetLine && (
                  <Area type="monotone" dataKey="target" name="Target" stroke={SLATE} strokeDasharray="4 4" fill="none" strokeWidth={1.5} />
                )}
                <Area type="monotone" dataKey="mrr" name="MRR" stroke={GOLD} strokeWidth={2} fill="url(#mrr)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        {funnelStages.length > 0 && (
          <GlassCard className="p-5 fade-up" data-testid="sales-funnel">
            <div className="flex items-start justify-between gap-3 mb-4">
              <SectionLabel className="mb-0">Sales Funnel</SectionLabel>
              {data.funnel_is_sample && (
                <span
                  className="shrink-0 text-[10px] font-mono uppercase tracking-wide px-2 py-1 rounded border border-helm-status-warning/35 bg-helm-status-warning/12 text-helm-status-warning"
                  data-testid="funnel-sample-badge"
                >
                  Sample data
                </span>
              )}
            </div>
            {data.funnel_is_sample && (
              <p className="text-xs text-helm-status-warning mb-3 leading-relaxed" data-testid="funnel-sample-note">
                This funnel is demo sample data, not your live pipeline. Add deals to replace it.
              </p>
            )}
            <FunnelChart
              data={funnelStages}
              color={GOLD}
              layers={3}
              className="min-h-[240px]"
              grid={{
                bands: true,
                bandColor: `${CREAM}14`,
                lines: true,
                lineColor: SLATE,
                lineOpacity: 0.28,
              }}
            />
          </GlassCard>
        )}
      </div>

      {(data.risks?.length > 0 || data.notes || canWrite || suggestedRisks.length > 0) && (
        <GlassCard className="p-5 fade-up" data-testid="telemetry-risks">
          <div className="flex items-start justify-between gap-3 mb-4">
            <SectionLabel className="mb-0">Risk radar</SectionLabel>
            {data.risks_is_sample && (
              <span
                className="shrink-0 text-[10px] font-mono uppercase tracking-wide px-2 py-1 rounded border border-helm-status-warning/35 bg-helm-status-warning/12 text-helm-status-warning"
                data-testid="risks-sample-badge"
              >
                Sample data
              </span>
            )}
          </div>
          {data.risks_is_sample && (
            <p className="text-xs text-helm-status-warning mb-3 leading-relaxed" data-testid="risks-sample-note">
              These risk cards are demo sample data. Edit telemetry to replace them with risks you&apos;re actually watching.
            </p>
          )}
          {data.notes && !editing && (
            <p className="text-sm text-helm-muted mb-4 leading-relaxed border-l-2 border-helm-gold/35 pl-3">{data.notes}</p>
          )}
          {!editing && data.risks?.length > 0 && (
            <div className="grid sm:grid-cols-2 gap-3">
              {data.risks.map((r) => {
                const score = (r.likelihood || 1) * (r.impact || 1);
                return (
                  <div key={r.id || r.name} className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-helm-fg">{r.name}</p>
                      <span className="text-[10px] font-mono rounded px-1.5 py-0.5" style={{ color: riskColor(score), background: `${riskColor(score)}15` }}>{score}</span>
                    </div>
                    <p className="text-[10px] text-helm-muted mt-1 font-mono uppercase">
                      {r.category}
                      <span className="normal-case tracking-normal ml-2 opacity-80">
                        L{r.likelihood} × I{r.impact}
                      </span>
                    </p>
                  </div>
                );
              })}
            </div>
          )}
          {!editing && !data.risks?.length && canWrite && (
            <p className="text-sm text-helm-muted">No risks logged yet. Click Edit telemetry to add what you&apos;re watching.</p>
          )}

          {!editing && suggestedRisks.length > 0 && (
            <div className="mt-5 pt-4 border-t border-helm-line" data-testid="helm-noticed-risks">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="w-3.5 h-3.5 text-helm-status-warning" />
                <span className="text-[11px] font-mono uppercase tracking-wider text-helm-status-warning">Trenston noticed</span>
              </div>
              <div className="space-y-2">
                {suggestedRisks.map((s) => (
                  <div
                    key={s.source_signal}
                    className="flex items-center gap-3 rounded-lg border border-helm-status-warning/25 bg-helm-status-warning/[0.04] px-3 py-2.5"
                    data-testid={`suggested-risk-${s.source_signal}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-helm-fg truncate">{s.name}</p>
                      <p className="text-[10px] font-mono uppercase text-helm-muted mt-0.5">{s.category}</p>
                    </div>
                    {canWrite && (
                      <button
                        type="button"
                        onClick={() => openEdit(s)}
                        className="shrink-0 text-xs text-helm-gold hover:text-helm-gold-hover font-medium"
                      >
                        Add to radar
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </GlassCard>
      )}

      <GlassCard className="p-5 fade-up mb-6" data-testid="telemetry-activity">
        <SectionLabel className="mb-4">Activity</SectionLabel>
        {activityTotal === 0 || heatmapColumns.length === 0 ? (
          <p className="text-sm text-helm-muted leading-relaxed">
            Not enough workspace activity yet to show a pattern. As your team uses Trenston, this calendar fills in.
          </p>
        ) : (
          <HeatmapInteractionProvider>
            <HeatmapInteractionBoundary>
              <HeatmapChart
                data={heatmapColumns}
                layout="fluid"
                gap={3}
                binSize={11}
                levelColors={HEATMAP_DEFAULT_LEVEL_COLORS}
                margin={{ top: 28, right: 8, bottom: 0, left: 28 }}
                className="max-w-full overflow-x-auto"
              >
                <HeatmapCells cornerRadius={2} />
                <HeatmapXAxis />
                <HeatmapYAxis tickFilter="odd" labelFormat="initial" />
                <HeatmapTooltip
                  formatLabel={(count) => (count === 1 ? "1 activity" : `${count} activities`)}
                  backgroundColor="var(--helm-card, #121214)"
                />
              </HeatmapChart>
              <HeatmapLegend
                levelStyles={HEATMAP_DEFAULT_LEVEL_STYLES}
                labelClassName="text-helm-muted"
                className="mt-3"
                align="start"
              />
            </HeatmapInteractionBoundary>
          </HeatmapInteractionProvider>
        )}
      </GlassCard>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setEditing(false)} />
          <GlassCard className="relative w-full sm:max-w-lg m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6 max-h-[90vh] overflow-y-auto" data-testid="telemetry-edit-form">
            <h3 className="text-lg text-helm-fg font-light">Edit telemetry</h3>
            <p className="text-xs text-helm-muted mt-1 mb-5 leading-relaxed">
              Set an optional revenue target and track risks scored 1–5 for likelihood and impact.
            </p>

            <div className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-4 mb-5" data-testid="telemetry-targets-editor">
              <SectionLabel className="mb-3">Targets</SectionLabel>
              <label className="flex items-center gap-2 text-sm text-helm-fg cursor-pointer">
                <input
                  type="checkbox"
                  checked={targetEnabled}
                  onChange={(e) => setTargetEnabled(e.target.checked)}
                  className="accent-helm-gold w-4 h-4"
                  data-testid="enable-revenue-target"
                />
                Enable revenue target
              </label>
              <p className="text-[11px] text-helm-muted mt-1.5 leading-relaxed">
                When on, the chart shows a dashed target from last month&apos;s actual MRR grown by your %.
              </p>
              {targetEnabled && (
                <label className="text-[10px] font-mono uppercase tracking-wider text-helm-muted block mt-3">
                  Target monthly growth %
                  <input
                    type="number"
                    step="0.1"
                    value={growthPct}
                    onChange={(e) => setGrowthPct(e.target.value)}
                    data-testid="target-growth-pct"
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                  />
                </label>
              )}
            </div>

            <label className="text-xs text-helm-muted block mb-5">
              Radar notes
              <span className="block font-normal text-[11px] text-helm-muted/80 mt-0.5">Optional context for the whole radar, not a risk itself.</span>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="What are you watching overall this month?"
                className="mt-1.5 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 resize-none focus:outline-none focus:border-helm-gold/40"
              />
            </label>

            <div className="flex items-center justify-between mb-3">
              <SectionLabel>Risks</SectionLabel>
              <span className="text-[10px] font-mono text-helm-muted">{risks.filter((r) => r.name?.trim()).length} named</span>
            </div>

            <div className="space-y-3">
              {risks.map((r, i) => {
                const score = (Number(r.likelihood) || 1) * (Number(r.impact) || 1);
                return (
                  <div
                    key={r.id || `new-${i}`}
                    className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-4 space-y-3"
                    data-testid={`risk-editor-${i}`}
                  >
                    <div className="flex items-start gap-2">
                      <div className="flex-1 min-w-0 space-y-2">
                        <label className="text-[10px] font-mono uppercase tracking-wider text-helm-muted block">
                          Risk
                          <input
                            value={r.name}
                            onChange={(e) => setRisks((prev) => prev.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                            placeholder="e.g. Key hire slips, runway under 6 months"
                            className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                          />
                        </label>
                        <label className="text-[10px] font-mono uppercase tracking-wider text-helm-muted block">
                          Category
                          <input
                            value={r.category}
                            onChange={(e) => setRisks((prev) => prev.map((x, j) => (j === i ? { ...x, category: e.target.value } : x)))}
                            placeholder="People, Finance, Ops…"
                            className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                          />
                        </label>
                      </div>
                      <CirDeleteBtn
                        title="Remove risk"
                        onClick={() => setRisks((prev) => (prev.length <= 1 ? [{ ...emptyRisk() }] : prev.filter((_, j) => j !== i)))}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3 pt-1 border-t border-helm-line">
                      <label className="text-[10px] font-mono uppercase tracking-wider text-helm-muted block">
                        Likelihood
                        <span className="block normal-case tracking-normal font-sans text-[11px] text-helm-muted/80 mt-0.5">How likely? (1–5)</span>
                        <select
                          value={r.likelihood}
                          onChange={(e) => setRisks((prev) => prev.map((x, j) => (j === i ? { ...x, likelihood: parseInt(e.target.value, 10) || 1 } : x)))}
                          className="mt-1.5 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-2 py-2 focus:outline-none focus:border-helm-gold/40"
                        >
                          {[1, 2, 3, 4, 5].map((n) => (
                            <option key={n} value={n}>{n}</option>
                          ))}
                        </select>
                      </label>
                      <label className="text-[10px] font-mono uppercase tracking-wider text-helm-muted block">
                        Impact
                        <span className="block normal-case tracking-normal font-sans text-[11px] text-helm-muted/80 mt-0.5">How bad if it hits? (1–5)</span>
                        <select
                          value={r.impact}
                          onChange={(e) => setRisks((prev) => prev.map((x, j) => (j === i ? { ...x, impact: parseInt(e.target.value, 10) || 1 } : x)))}
                          className="mt-1.5 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-2 py-2 focus:outline-none focus:border-helm-gold/40"
                        >
                          {[1, 2, 3, 4, 5].map((n) => (
                            <option key={n} value={n}>{n}</option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-helm-muted font-mono">
                        {r.likelihood} × {r.impact}
                      </span>
                      <span
                        className="text-[11px] font-mono rounded px-2 py-0.5"
                        style={{ color: riskColor(score), background: `${riskColor(score)}15` }}
                      >
                        Score {score}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              onClick={() => setRisks((prev) => [...prev, emptyRisk()])}
              className="mt-3 inline-flex items-center gap-1.5 text-xs text-helm-gold hover:text-helm-gold-hover"
            >
              <Plus className="w-3.5 h-3.5" /> Add another risk
            </button>

            <div className="flex gap-2 mt-5">
              <button type="button" onClick={() => setEditing(false)} className="rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/5">Cancel</button>
              <button type="button" onClick={saveTelemetry} disabled={busy} className="flex-1 rounded-md bg-helm-gold text-helm-navy font-medium text-sm py-2.5 hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : "Save"}</button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
