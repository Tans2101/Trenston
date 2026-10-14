import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

function formatAsOf(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return null;
  }
}

/**
 * Quiet framing for AI-generated summaries: labels them as a summary and
 * shows an "as of" timestamp from underlying data when available.
 */
export default function AiSummaryMeta({
  asOf,
  detailHref = "/app/reports",
  detailLabel = "source data",
  className,
}) {
  const asOfLabel = formatAsOf(asOf);
  return (
    <p
      className={cn("text-[11px] font-mono uppercase tracking-wider text-helm-muted", className)}
      data-testid="ai-summary-meta"
    >
      AI summary · check key figures
      {asOfLabel ? <> · as of {asOfLabel}</> : null}
      {detailHref ? (
        <>
          {" · "}
          <Link to={detailHref} className="text-helm-gold/80 hover:text-helm-gold normal-case tracking-normal">
            see {detailLabel}
          </Link>
        </>
      ) : null}
    </p>
  );
}

export function PossiblyStaleBadge({ show }) {
  if (!show) return null;
  return (
    <span
      className="text-[10px] font-mono uppercase tracking-wider text-helm-status-warning"
      data-testid="possibly-stale-badge"
    >
      Possibly stale
    </span>
  );
}
