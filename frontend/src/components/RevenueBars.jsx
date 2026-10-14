import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { formatAxisMoney } from "@/lib/formatAxisMoney";
import { formatMoney } from "@/lib/money";

/** Current vs prior month revenue bars for the Briefing hero (lazy-loaded with recharts). */
export default function RevenueBars({
  data, axisStroke, cursorFill, tooltipBg, tooltipBorder, tooltipFg, moneySymbol, currentBar, lastBar,
}) {
  return (
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
  );
}
