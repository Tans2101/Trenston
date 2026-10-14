import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { formatAxisMoney } from "@/lib/formatAxisMoney";
import { formatMoney } from "@/lib/money";

/** One plain sentence for screen readers (and anyone who can't read the bars). */
export function revenueSummary(data, symbol) {
  const rows = (data || []).filter((r) => r && r.month);
  if (!rows.length) return "Revenue by month: no data yet.";
  const last = rows[rows.length - 1];
  const cur = Number(last.current);
  const prev = Number(last.last);
  const span = `Revenue by month, ${rows[0].month} to ${last.month}.`;
  if (!Number.isFinite(cur)) return span;
  let out = `${span} ${last.month}: ${formatMoney(Math.round(cur), symbol)}`;
  if (Number.isFinite(prev) && prev > 0) {
    const pct = Math.round(((cur - prev) / prev) * 100);
    out += `, ${pct >= 0 ? "up" : "down"} ${Math.abs(pct)} percent on the month before (${formatMoney(Math.round(prev), symbol)}).`;
  } else {
    out += ".";
  }
  return out;
}

/** Current vs prior month revenue bars for the Briefing hero (lazy-loaded with recharts). */
export default function RevenueBars({
  data, axisStroke, cursorFill, tooltipBg, tooltipBorder, tooltipFg, moneySymbol, currentBar, lastBar,
}) {
  const summary = revenueSummary(data, moneySymbol);
  return (
    <div role="img" aria-label={summary}>
      <p className="sr-only">{summary}</p>
<ResponsiveContainer width="100%" height={220}>
              <BarChart data={data} margin={{ left: -8, right: 8, top: 4 }}>
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
    </div>
  );
}
