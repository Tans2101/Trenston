import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Network } from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import {
  PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, SkeletonCardList,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { layoutMap, linkPath, truncate } from "@/lib/companyMapLayout";

const TONE_STROKE = {
  ok: "stroke-helm-status-positive",
  warn: "stroke-helm-status-warning",
  bad: "stroke-helm-status-negative",
  neutral: "stroke-helm-line",
};
const TONE_FILL = {
  ok: "fill-helm-status-positive/10",
  warn: "fill-helm-status-warning/10",
  bad: "fill-helm-status-negative/12",
  neutral: "fill-helm-card",
};
const TONE_TEXT = {
  ok: "text-helm-status-positive",
  warn: "text-helm-status-warning",
  bad: "text-helm-status-negative",
  neutral: "text-helm-muted",
};

const SUBTITLE = {
  solo: "Money coming in, money going out, what you've promised and what's going wrong, in one picture.",
  team: "Money, promises, your team and what's going wrong, in one picture.",
};

function MapNode({ node, box, selected, onSelect }) {
  const big = node.kind === "cash";
  const isHub = node.kind === "hub";
  const tone = node.tone || "neutral";
  const x = box.x - box.w / 2;
  const y = box.y - box.h / 2;
  const maxLabel = big ? 22 : isHub ? 15 : node.kind === "problem" || node.kind === "person" ? 15 : 18;
  const maxSub = big ? 34 : node.kind === "problem" ? 0 : 22;
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={`${node.label}${node.sub ? `: ${node.sub}` : ""}`}
      data-testid={`map-node-${node.id}`}
      className="cursor-pointer outline-none"
      onClick={() => onSelect(node.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(node.id);
        }
      }}
    >
      <rect
        x={x}
        y={y}
        width={box.w}
        height={box.h}
        rx={isHub ? 20 : 10}
        strokeDasharray={node.placeholder ? "5 4" : undefined}
        className={cn(
          TONE_FILL[tone],
          TONE_STROKE[tone === "neutral" && (big || selected) ? "ok" : tone],
          selected ? "stroke-[2.5]" : "stroke-[1.25]",
          big && tone === "neutral" && "stroke-helm-gold",
        )}
      />
      {node.kind === "problem" && (
        <circle cx={x + 10} cy={y + 10} r={3.5} className={cn(tone === "bad" ? "fill-helm-status-negative" : "fill-helm-status-warning")} />
      )}
      <text
        x={box.x}
        y={maxSub && node.sub ? box.y - (big ? 8 : 4) : box.y + 4}
        textAnchor="middle"
        className={cn("fill-helm-fg", big ? "text-[15px] font-semibold" : "text-[12px] font-medium")}
      >
        {truncate(node.label, maxLabel)}
      </text>
      {maxSub > 0 && node.sub ? (
        <text x={box.x} y={box.y + (big ? 14 : 12)} textAnchor="middle" className="fill-helm-muted text-[10.5px]">
          {truncate(node.sub, maxSub)}
        </text>
      ) : null}
    </g>
  );
}

function Detail({ node }) {
  if (!node) {
    return (
      <p className="text-sm text-helm-muted" data-testid="map-detail-empty">
        Tap anything on the map to see what it is and what to do about it.
      </p>
    );
  }
  return (
    <div data-testid="map-detail">
      <p className="text-xs font-mono uppercase tracking-wider text-helm-muted">{node.kind === "problem" ? "Problem" : node.kind}</p>
      <p className="mt-1 text-base font-medium text-helm-fg">{node.label}</p>
      {node.sub ? <p className="mt-1 text-sm text-helm-muted whitespace-pre-line">{node.sub}</p> : null}
      {node.action ? <p className="mt-2 text-sm text-helm-fg"><span className={TONE_TEXT[node.tone]}>Next step:</span> {node.action}</p> : null}
      {node.to ? (
        <Link to={node.to} className="mt-3 inline-block text-sm text-helm-gold hover:underline" data-testid="map-detail-open">
          Open it
        </Link>
      ) : null}
    </div>
  );
}

export default function CompanyMap() {
  const { data, loading, error, reload } = useFetch("/company-map");
  const [selectedId, setSelectedId] = useState(null);

  const nodes = useMemo(() => data?.nodes || [], [data?.nodes]);
  const links = useMemo(() => data?.links || [], [data?.links]);
  const layout = useMemo(() => layoutMap(nodes), [nodes]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const problems = useMemo(() => nodes.filter((n) => n.kind === "problem"), [nodes]);
  const selected = selectedId ? byId.get(selectedId) : null;

  if (loading && !data) {
    return (
      <div data-testid="company-map-page">
        <PageHeader title="Company map" subtitle={SUBTITLE.solo} />
        <SkeletonCardList count={2} />
      </div>
    );
  }
  if (error && !data) {
    return <ErrorScreen label="Company map" message={fetchErrorMessage(error)} onRetry={reload} />;
  }

  const missing = data?.missing || [];
  const subtitle = SUBTITLE[data?.mode] || SUBTITLE.solo;

  if (!data?.ready) {
    return (
      <div data-testid="company-map-page">
        <PageHeader title="Company map" subtitle={subtitle} />
        <GlassCard className="p-6">
          <EmptyState
            icon={Network}
            title="Your map starts with a few facts"
            body="Add any of these and the map draws itself from them. Nothing is guessed or filled in."
            action={(
              <div className="flex flex-wrap justify-center gap-2" data-testid="map-missing">
                {missing.map((m) => (
                  <Link
                    key={m.label}
                    to={m.to}
                    className="rounded-full border border-helm-line bg-helm-fg/[0.03] px-3 py-1.5 text-sm text-helm-fg hover:border-helm-gold/40"
                  >
                    {m.label}
                  </Link>
                ))}
              </div>
            )}
          />
        </GlassCard>
      </div>
    );
  }

  return (
    <div data-testid="company-map-page">
      <PageHeader title="Company map" subtitle={subtitle} />

      <GlassCard className="p-3 sm:p-5">
        <svg
          viewBox={layout.viewBox}
          className="w-full h-auto select-none"
          role="group"
          aria-label="Company map"
          data-testid="company-map-svg"
        >
          <g fill="none">
            {links.map((l) => {
              const a = layout.pos[l.source];
              const b = layout.pos[l.target];
              if (!a || !b) return null;
              const tone = l.tone || "neutral";
              return (
                <path
                  key={`${l.source}>${l.target}`}
                  d={linkPath(a, b)}
                  className={cn(TONE_STROKE[tone], tone === "bad" ? "stroke-[1.75]" : "stroke-[1.1]")}
                  strokeOpacity={tone === "neutral" ? 0.7 : 0.9}
                  strokeDasharray={tone === "bad" || tone === "warn" ? "4 3" : undefined}
                />
              );
            })}
          </g>
          {nodes.map((n) => (
            layout.pos[n.id] ? (
              <MapNode key={n.id} node={n} box={layout.pos[n.id]} selected={selectedId === n.id} onSelect={setSelectedId} />
            ) : null
          ))}
        </svg>
      </GlassCard>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <GlassCard className="p-4 sm:p-5">
          <SectionLabel>Selected</SectionLabel>
          <div className="mt-2"><Detail node={selected} /></div>
        </GlassCard>
        <GlassCard className="p-4 sm:p-5" data-testid="map-problems">
          <SectionLabel>What needs you ({problems.length})</SectionLabel>
          {problems.length === 0 ? (
            <p className="mt-2 text-sm text-helm-muted">Nothing is flagged right now.</p>
          ) : (
            <ul className="mt-2 space-y-3">
              {problems.map((p) => (
                <li key={p.id}>
                  <button type="button" className="w-full text-left" onClick={() => setSelectedId(p.id)}>
                    <span className={cn("text-sm font-medium", TONE_TEXT[p.tone])}>{p.label}</span>
                    <span className="block text-sm text-helm-muted">{p.action}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
      </div>

      {missing.length > 0 && (
        <p className="mt-4 text-sm text-helm-muted" data-testid="map-missing-note">
          Not on the map yet:{" "}
          {missing.map((m, i) => (
            <span key={m.label}>
              {i > 0 ? ", " : ""}
              <Link to={m.to} className="text-helm-gold hover:underline">{m.label.toLowerCase()}</Link>
            </span>
          ))}
          .
        </p>
      )}
    </div>
  );
}
