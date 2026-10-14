import { useState } from "react";
import { formatDay } from "@/lib/dates";
import { toast } from "sonner";
import { FileText, FolderOpen, ExternalLink } from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api, apiErrorMessage } from "@/lib/api";
import { GlassCard, ErrorScreen, SkeletonCardList } from "@/components/kit";

const CONTEXT_LABELS = {
  financial: "Financial",
  reports: "Reports",
  legal: "Legal",
};

const CONTEXT_ORDER = ["financial", "reports", "legal"];

const ALLOWED_OPEN_PREFIXES = [
  "/documents/",
  "/reports/documents/",
  "/legal/matters/",
];

function openPathIsSafe(path) {
  if (!path || typeof path !== "string" || !path.startsWith("/")) return false;
  if (path.includes("://") || path.includes("..")) return false;
  return ALLOWED_OPEN_PREFIXES.some((p) => path.startsWith(p));
}

/**
 * Settings card: every document the signed-in user may open, grouped by context.
 * Opening always goes through the existing per-context GET (presigned URL) — never raw.
 */
export default function DocumentsLibrarySettings() {
  const { data, loading, error, reload } = useFetch("/documents/library");
  const [openingId, setOpeningId] = useState(null);

  const grouped = { financial: [], reports: [], legal: [] };
  for (const d of data?.documents || []) {
    if (d.context in grouped) grouped[d.context].push(d);
  }

  const openDocument = async (doc) => {
    const path = doc.open_path || "";
    if (!openPathIsSafe(path)) {
      toast.error("No open path for this document");
      return;
    }
    const key = `${doc.context}:${doc.id || doc.matter_id}`;
    setOpeningId(key);
    // Open synchronously so browsers do not treat the post-await navigation as a popup.
    // Do not pass "noopener" in features — that makes window.open return null and blocks href updates.
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    try {
      const { data: res } = await api.get(path);
      if (res?.presigned_url) {
        if (tab) tab.location.href = res.presigned_url;
        else window.open(res.presigned_url, "_blank", "noopener,noreferrer");
      } else {
        tab?.close();
        toast.error("Could not open document");
      }
    } catch (e) {
      tab?.close();
      toast.error(apiErrorMessage(e, "Could not open document"));
    } finally {
      setOpeningId(null);
    }
  };

  if (loading) {
    return (
      <GlassCard id="documents-library" className="p-5 mb-4 fade-up scroll-mt-24">
        <SkeletonCardList count={2} />
      </GlassCard>
    );
  }

  if (error) {
    return (
      <GlassCard id="documents-library" className="p-5 mb-4 fade-up scroll-mt-24">
        <ErrorScreen
          label="Could not load documents"
          message={fetchErrorMessage(error, "Document library is unavailable.")}
          onRetry={reload}
        />
      </GlassCard>
    );
  }

  const total = data?.count ?? (data?.documents || []).length;

  return (
    <GlassCard
      id="documents-library"
      className="p-5 mb-4 fade-up scroll-mt-24"
      data-testid="settings-documents-card"
    >
      <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
        <FolderOpen className="w-4 h-4" />
        <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Documents</span>
      </div>
      <p className="text-sm text-helm-muted mb-4 leading-relaxed">
        Files you already have access to across Financials, Reports, and Legal.
        Opening a file uses the same permission-checked download as each section.
      </p>

      {total === 0 ? (
        <p className="text-sm text-helm-muted" data-testid="documents-library-empty">
          No documents available for your access.
        </p>
      ) : (
        <div className="space-y-5">
          {CONTEXT_ORDER.map((ctx) => {
            const rows = grouped[ctx] || [];
            if (!rows.length) return null;
            return (
              <div key={ctx} data-testid={`documents-group-${ctx}`}>
                <div className="flex items-center gap-1.5 mb-2">
                  <FileText className="w-3.5 h-3.5 text-helm-muted" />
                  <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-helm-muted">
                    {CONTEXT_LABELS[ctx]}
                  </span>
                  <span className="text-[10px] text-helm-muted/70">({rows.length})</span>
                </div>
                <ul className="divide-y divide-helm-line/60 border border-helm-line/60 rounded-md overflow-hidden">
                  {rows.map((doc) => {
                    const rowKey = `${doc.context}:${doc.id || doc.matter_id}`;
                    const busy = openingId === rowKey;
                    return (
                      <li
                        key={rowKey}
                        className="flex items-center justify-between gap-3 px-3 py-2.5 bg-helm-card/40"
                      >
                        <div className="min-w-0">
                          <p className="text-sm text-helm-fg truncate">
                            {doc.filename || "Untitled"}
                          </p>
                          <p className="text-xs text-helm-muted truncate">
                            {doc.matter_title
                              ? `Matter · ${doc.matter_title}`
                              : doc.report_date
                                ? `Report date · ${doc.report_date}`
                                : doc.uploaded_at
                                  ? `Uploaded · ${formatDay(doc.uploaded_at)}`
                                  : CONTEXT_LABELS[ctx]}
                          </p>
                        </div>
                        <button
                          type="button"
                          data-testid={`documents-open-${doc.id || doc.matter_id}`}
                          onClick={() => openDocument(doc)}
                          disabled={busy}
                          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-helm-line px-2.5 py-1.5 text-xs text-helm-gold hover:border-helm-gold/40 disabled:opacity-60"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          {busy ? "Opening…" : "Open"}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}
