import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { FileText, Plus, PenLine, X, Copy, Download, Check, ArrowRight, ChevronDown } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage, blobErrorDetail } from "@/hooks/useFetch";
import { useSoftRefreshToast } from "@/hooks/useSoftRefreshToast";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, SkeletonKPIRow, SkeletonChart, SkeletonCardList } from "@/components/kit";
import DocumentStamp, { stampLabelForLine } from "@/components/DocumentStamp";
import ReportsDailyDigest from "@/components/ReportsDailyDigest";
import AiSummaryMeta from "@/components/AiSummaryMeta";
import { cn } from "@/lib/utils";
import { currencySymbol, formatMoney } from "@/lib/money";
import { confirmAction } from "@/components/ConfirmHost";

// Auto trend cards → the page whose data they summarise.
const AUTO_REPORT_SOURCES = {
  auto_fin: { to: "/app/financials", label: "View in Financials" },
  auto_team: { to: "/app/people", label: "View team" },
  auto_exec: { to: "/app/tasks", label: "View tasks" },
};

export const REPORT_TYPES = ["General", "Sales", "Finance", "Operations", "Team", "Production", "Procurement", "Marketing"];
export const MAX_REPORT_METRICS = 6;
const blankMetric = () => ({ label: "", value: "" });
const emptyReport = () => ({ title: "", type: "General", period: "", summary: "", metrics: [blankMetric(), blankMetric(), blankMetric()] });

/** Form rows for a report's numbers: what it has (up to the max), padded to at least 3. */
export function formMetrics(metrics) {
  const rows = (metrics || [])
    .map((m) => ({ label: m?.label || "", value: m?.value?.toString?.() ?? String(m?.value ?? "") }))
    .slice(0, MAX_REPORT_METRICS);
  while (rows.length < 3) rows.push(blankMetric());
  return rows;
}

/** "Oct 17, 3:05 PM" for when a CEO Pack was written. */
export function writtenAt(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function Section({ id, title, description, action, children, testId }) {
  return (
    <section id={id} className="mb-10 scroll-mt-20 fade-up" data-testid={testId}>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-lg font-medium tracking-tight text-helm-fg">{title}</h2>
          {description && <p className="mt-1 max-w-2xl text-sm leading-relaxed text-helm-muted">{description}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </section>
  );
}

export default function Reports() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useFetch("/reports");
  const [pack, setPack] = useState("");
  const [packAsOf, setPackAsOf] = useState(null);
  const [packWrittenAt, setPackWrittenAt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [packBusy, setPackBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyReport());
  const [editing, setEditing] = useState(null);
  const [publishingDraftId, setPublishingDraftId] = useState(null);
  const [finPeriod, setFinPeriod] = useState("");
  const [finExporting, setFinExporting] = useState(null);
  const [finPreview, setFinPreview] = useState(null);
  const [finPreviewLoading, setFinPreviewLoading] = useState(false);
  const [showFinPreview, setShowFinPreview] = useState(false);
  useSoftRefreshToast(error, data, "Could not refresh reports. Showing the last loaded data.");

  useEffect(() => () => {
    if (copyTimer.current) clearTimeout(copyTimer.current);
  }, []);

  useEffect(() => {
    if (!data) return;
    const months = data.financial_months || [];
    const next = data.financial_latest_month || months[months.length - 1] || new Date().toISOString().slice(0, 7);
    setFinPeriod((prev) => prev || next);
    // Show the last CEO Pack someone wrote, so it survives a reload.
    if (data.last_pack?.content) {
      setPack((prev) => prev || data.last_pack.content);
      setPackAsOf((prev) => prev || data.last_pack.data_as_of || null);
      setPackWrittenAt((prev) => prev || data.last_pack.created_at || null);
    }
  }, [data]);

  useEffect(() => {
    const canExport = Boolean(data?.can_export_financials);
    if (!canExport || !finPeriod || !showFinPreview) {
      return undefined;
    }
    let cancelled = false;
    setFinPreviewLoading(true);
    (async () => {
      try {
        const { data: bundle } = await api.get("/reports/financial-export", { params: { period: finPeriod } });
        if (!cancelled) setFinPreview(bundle);
      } catch {
        if (!cancelled) setFinPreview(null);
      } finally {
        if (!cancelled) setFinPreviewLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [data?.can_export_financials, finPeriod, showFinPreview]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Reports" subtitle="See how the week went, write updates, and export your numbers." />
        <SkeletonKPIRow count={3} className="lg:grid-cols-3" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <SkeletonChart />
          <SkeletonCardList count={3} />
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <ErrorScreen
        label="Could not load reports"
        message={fetchErrorMessage(error, "Reports data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  const manual = data.manual_reports || data.reports?.filter((r) => r.source === "manual") || [];
  const auto = data.auto_reports || data.reports?.filter((r) => r.source === "auto") || [];
  const drafts = data.draft_reports || [];
  const canWrite = data.can_write;
  const canGeneratePack = Boolean(data.can_generate_pack);
  const canExportFinancials = Boolean(data.can_export_financials);

  const openAdd = () => {
    setEditing(null);
    setPublishingDraftId(null);
    setForm(emptyReport());
    setShowForm(true);
  };
  const openEdit = (r) => {
    setEditing(r.id);
    setPublishingDraftId(null);
    setForm({
      title: r.title || "",
      type: r.type || "General",
      period: r.period === "Manual" ? "" : (r.period || ""),
      summary: r.summary || "",
      metrics: formMetrics(r.metrics),
    });
    setShowForm(true);
  };
  const openPublishDraft = (d) => {
    setEditing(null);
    setPublishingDraftId(d.id);
    setForm({
      title: d.title || "",
      type: d.type || "General",
      period: d.period || "",
      summary: d.summary || "",
      metrics: formMetrics(d.metrics),
    });
    setShowForm(true);
  };
  const dismissDraft = async (d) => {
    try {
      await api.post(`/reports/drafts/${d.id}/dismiss`);
      toast.success("Draft dismissed");
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not dismiss draft");
    }
  };

  const submit = async () => {
    if (!form.title.trim()) { toast.error("Add a title"); return; }
    setBusy(true);
    const payload = {
      ...form,
      metrics: form.metrics.filter((m) => m.label?.trim() && m.value?.toString().trim()),
    };
    try {
      if (editing) await api.patch(`/reports/${editing}`, payload);
      else await api.post("/reports", publishingDraftId ? { ...payload, from_draft_id: publishingDraftId } : payload);
      toast.success(editing ? "Report updated" : publishingDraftId ? "Report published" : "Report saved");
      setShowForm(false);
      setPublishingDraftId(null);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save"); }
    finally { setBusy(false); }
  };

  const del = async (r) => {
    if (!(await confirmAction({ title: `Delete "${r.title}"?`, confirmLabel: "Delete", destructive: true }))) return;
    try { await api.delete(`/reports/${r.id}`); reload(); toast.success("Report removed"); }
    catch (e) { toast.error("Could not delete"); }
  };

  const generatePack = async () => {
    setPackBusy(true);
    try {
      const { data: res } = await api.post("/reports/weekly-pack", {}, { timeout: 90000 });
      setPack(res.content);
      setPackAsOf(res.data_as_of || null);
      setPackWrittenAt(res.created_at || new Date().toISOString());
      toast.success("CEO Pack ready");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not write the CEO Pack");
    } finally {
      setPackBusy(false);
    }
  };

  const copyPack = async () => {
    if (!pack) return;
    try {
      await navigator.clipboard.writeText(pack);
      setCopied(true);
      toast.success("CEO Pack copied");
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy. Select the text instead");
    }
  };

  const saveBlob = (res, mime, fallbackName) => {
    const blob = new Blob([res.data], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const disposition = res.headers["content-disposition"] || "";
    const match = disposition.match(/filename="([^"]+)"/);
    a.download = match?.[1] || fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Revoking right after click() can cancel the download in Safari/Firefox.
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  };

  const downloadFinancialExport = async (kind) => {
    if (!finPeriod) return;
    setFinExporting(kind);
    try {
      const res = await api.post(`/reports/financial-export/${kind}`, { period: finPeriod }, { responseType: "blob" });
      saveBlob(
        res,
        kind === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        `Trenston-Financial-Export.${kind}`,
      );
      toast.success(kind === "pdf" ? "PDF downloaded" : "Excel downloaded");
    } catch (e) {
      toast.error(await blobErrorDetail(e, "Could not download export"));
    } finally {
      setFinExporting(null);
    }
  };

  const downloadPdf = async () => {
    if (!pack) return;
    setExporting(true);
    try {
      const res = await api.post("/reports/weekly-pack/export-pdf", { content: pack }, { responseType: "blob" });
      saveBlob(res, "application/pdf", "Trenston-Weekly-Pack.pdf");
      toast.success("PDF downloaded");
    } catch (e) {
      toast.error(await blobErrorDetail(e, "Could not download PDF"));
    } finally {
      setExporting(false);
    }
  };

  const openFromTrend = (r) => {
    setEditing(null);
    setPublishingDraftId(null);
    const changeNotes = (r.metrics || [])
      .filter((m) => m.change && m.change !== "Current total" && m.change !== "No comparison yet")
      .map((m) => `${m.label}: ${m.change}`)
      .join(". ");
    setForm({
      title: r.title || "",
      type: "General",
      period: r.period || "",
      summary: changeNotes || r.summary || "",
      metrics: formMetrics(r.metrics),
    });
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setPublishingDraftId(null);
  };

  const setMetric = (i, key, value) => setForm((f) => {
    const metrics = [...f.metrics];
    metrics[i] = { ...metrics[i], [key]: value };
    return { ...f, metrics };
  });

  const writeBtn = canWrite ? (
    <button data-testid="add-report-btn" type="button" onClick={openAdd}
      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover">
      <Plus className="w-4 h-4" /> Write a report
    </button>
  ) : null;

  const jumps = [
    { id: "this-week", label: "This week" },
    { id: "ceo-pack", label: "CEO Pack" },
    canExportFinancials && { id: "accountant-export", label: "Accountant export" },
    canWrite && { id: "daily-files", label: "Daily files" },
    { id: "saved-reports", label: "Saved reports" },
  ].filter(Boolean);

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="See how the week went, write updates, and export your numbers. Everything comes from your own records."
        action={writeBtn}
      />

      <nav aria-label="Report sections" className="-mt-2 mb-8 flex flex-wrap gap-2" data-testid="report-jumps">
        {jumps.map((j) => (
          <a
            key={j.id}
            href={`#${j.id}`}
            onClick={(e) => { e.preventDefault(); document.getElementById(j.id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}
            className="rounded-full border border-helm-line px-3 py-1 text-xs text-helm-muted hover:border-helm-gold/40 hover:text-helm-fg"
          >
            {j.label}
          </a>
        ))}
      </nav>

      {auto.length > 0 && (
        <Section
          id="this-week"
          testId="week-over-week-trends"
          title="This week at a glance"
          description="Built automatically from your records and compared with last week. Nothing to fill in."
        >
          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            {auto.map((r, i) => (
              <ReportCard
                key={r.id}
                report={r}
                index={i}
                canWrite={canWrite}
                onAddToReport={() => openFromTrend(r)}
                source={AUTO_REPORT_SOURCES[r.id]}
              />
            ))}
          </div>
        </Section>
      )}

      <Section
        id="ceo-pack"
        title="CEO Pack"
        description="A one-page update on the week for you, your team or investors. Trenston writes it from this week's numbers and your saved reports. Read it, then copy it or download a PDF."
        action={canGeneratePack ? (
          <button data-testid="generate-pack-btn" type="button" onClick={generatePack} disabled={packBusy}
            className="inline-flex items-center gap-2 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60">
            <FileText className="w-4 h-4" />{packBusy ? "Writing… (about 20 seconds)" : pack ? "Write a new one" : "Write this week's CEO Pack"}
          </button>
        ) : null}
      >
        {!canGeneratePack && (
          <GlassCard className="p-5 text-sm text-helm-muted" data-testid="pack-locked">
            {(user?.perms || []).includes("reports:pack")
              ? "The CEO Pack is on the Starter plan and above."
              : "Only owners and executives can write the CEO Pack."}
          </GlassCard>
        )}
        {canGeneratePack && !pack && (
          <GlassCard className="p-5 text-sm text-helm-muted" data-testid="pack-empty">
            No CEO Pack yet. Press the button and Trenston will write one in about 20 seconds.
          </GlassCard>
        )}
        {pack && (
          <GlassCard className="p-5" data-testid="pack-content">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {packWrittenAt && (
                <span className="mr-auto text-xs text-helm-muted" data-testid="pack-written-at">Written {writtenAt(packWrittenAt)}</span>
              )}
              <button data-testid="copy-pack-btn" type="button" onClick={copyPack}
                className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5">
                <Copy className="w-3.5 h-3.5" />{copied ? "Copied" : "Copy"}
              </button>
              {canGeneratePack && (
                <button data-testid="download-pack-pdf-btn" type="button" onClick={downloadPdf} disabled={exporting}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10 disabled:opacity-60">
                  <Download className="w-3.5 h-3.5" />{exporting ? "Building PDF…" : "Download PDF"}
                </button>
              )}
            </div>
            <AiSummaryMeta asOf={packAsOf} detailHref="/app/financials" detailLabel="Financials" className="mb-3" />
            <PackPreview content={pack} />
          </GlassCard>
        )}
      </Section>

      {canExportFinancials && (
        <Section
          id="accountant-export"
          testId="financial-export-card"
          title="Export for your accountant"
          description="Income statement, cash summary and every line item for one month, as a PDF or Excel file. Same numbers as Financials. Not a balance sheet."
        >
          <GlassCard className="p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="text-xs text-helm-muted">
                Month
                <input
                  data-testid="financial-export-period"
                  type="month"
                  value={finPeriod}
                  onChange={(e) => setFinPeriod(e.target.value)}
                  className="mt-1 block rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button data-testid="financial-export-pdf-btn" type="button" onClick={() => downloadFinancialExport("pdf")} disabled={Boolean(finExporting)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10 disabled:opacity-60">
                  <Download className="w-3.5 h-3.5" />{finExporting === "pdf" ? "Building PDF…" : "Download PDF"}
                </button>
                <button data-testid="financial-export-xlsx-btn" type="button" onClick={() => downloadFinancialExport("xlsx")} disabled={Boolean(finExporting)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10 disabled:opacity-60">
                  <Download className="w-3.5 h-3.5" />{finExporting === "xlsx" ? "Building Excel…" : "Download Excel"}
                </button>
                <button data-testid="financial-export-preview-toggle" type="button" onClick={() => setShowFinPreview((v) => !v)} aria-expanded={showFinPreview}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5">
                  {showFinPreview ? "Hide preview" : "Preview"}
                  <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", showFinPreview && "rotate-180")} />
                </button>
              </div>
            </div>
            {showFinPreview && (
              <div className="mt-6 overflow-x-auto" data-testid="financial-export-preview">
                {finPreviewLoading && !finPreview ? (
                  <p className="text-xs text-helm-muted">Loading preview…</p>
                ) : finPreview ? (
                  <FinancialExportPreview bundle={finPreview} />
                ) : (
                  <p className="text-xs text-helm-muted">Could not load the preview for this month.</p>
                )}
              </div>
            )}
          </GlassCard>
        </Section>
      )}

      {canWrite && (
        <Section
          id="daily-files"
          title="Daily report files"
          description="Have reports from your team as Excel, CSV, PDF or photos? Add them here. Trenston reads each one and writes one short summary for the day."
        >
          <ReportsDailyDigest canWrite={canWrite} />
        </Section>
      )}

      <Section
        id="saved-reports"
        title="Saved reports"
        description="Short notes with a few key numbers, written by you or suggested by your departments. They stay here for your team and go into the CEO Pack."
      >
        {drafts.length > 0 && (
          <div className="mb-6" data-testid="department-drafts">
            <SectionLabel className="mb-3">Suggested by your departments</SectionLabel>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {drafts.map((d, i) => (
                <GlassCard key={d.id} className="p-5 fade-up border-helm-gold/35" style={{ animationDelay: `${i * 60}ms` }} data-testid={`draft-${d.id}`}>
                  <div className="flex items-center gap-2 mb-3">
                    <FileText className="w-4 h-4 text-helm-gold" />
                    <span className="text-[10px] font-mono uppercase tracking-wider text-helm-muted truncate">{[d.type, d.period].filter(Boolean).join(" · ")}</span>
                    <span className="text-[9px] font-mono uppercase rounded px-1.5 py-0.5 ml-auto text-helm-gold bg-helm-gold/12">Not published</span>
                  </div>
                  <h3 className="text-helm-fg font-medium">{d.title}</h3>
                  <p className="text-sm text-helm-muted mt-2 leading-relaxed">{d.summary}</p>
                  {d.metrics?.length > 0 && (
                    <div className="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-helm-line">
                      {d.metrics.map((m, mi) => (
                        <div key={`${m.label}-${mi}`}>
                          <p className="font-mono text-lg text-helm-fg">{m.value}</p>
                          <p className="text-[10px] text-helm-muted uppercase tracking-wide">{m.label}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {canWrite && (
                    <div className="flex gap-2 mt-4">
                      <button data-testid={`publish-draft-${d.id}`} type="button" onClick={() => openPublishDraft(d)}
                        className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-3 py-2 hover:bg-helm-gold-hover">
                        <Check className="w-3.5 h-3.5" /> Review and publish
                      </button>
                      <button data-testid={`dismiss-draft-${d.id}`} type="button" onClick={() => dismissDraft(d)}
                        className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5">
                        <X className="w-3.5 h-3.5" /> Dismiss
                      </button>
                    </div>
                  )}
                </GlassCard>
              ))}
            </div>
          </div>
        )}

        {manual.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {manual.map((r, i) => (
              <ReportCard key={r.id} report={r} index={i} canWrite={canWrite} onEdit={() => openEdit(r)} onDelete={() => del(r)} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No saved reports yet"
            body={canWrite
              ? "Write a short note on anything your team tracks, like weekly sales or production, with up to six numbers. Or press \"Save as report\" on a card above."
              : "Reports your team writes will show up here."}
          />
        )}
      </Section>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={closeForm} />
          <GlassCard role="dialog" aria-modal="true" aria-label={editing ? "Edit report" : "Write a report"} onKeyDown={(e) => { if (e.key === "Escape") closeForm(); }} className="relative max-h-[90vh] w-full overflow-y-auto sm:max-w-lg m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="report-form">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg text-helm-fg font-light">{editing ? "Edit report" : publishingDraftId ? "Review department draft" : "Write a report"}</h3>
              <button type="button" aria-label="Close" title="Close" onClick={closeForm} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button>
            </div>
            <p className="mb-5 text-xs leading-relaxed text-helm-muted">A short note with a few numbers. It is saved for your team and included in the next CEO Pack.</p>
            <div className="space-y-3">
              <label className="text-xs text-helm-muted block">Title
                <input data-testid="report-title" value={form.title} maxLength={120} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Sales this week" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-helm-muted">Area
                  <input data-testid="report-type" list="report-type-options" value={form.type} maxLength={40} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))} placeholder="Sales" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
                  <datalist id="report-type-options">
                    {REPORT_TYPES.map((t) => <option key={t} value={t} />)}
                  </datalist>
                </label>
                <label className="text-xs text-helm-muted">Time it covers
                  <input data-testid="report-period" value={form.period} maxLength={60} onChange={(e) => setForm((f) => ({ ...f, period: e.target.value }))} placeholder="Oct 12 to 18" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
                </label>
              </div>
              <label className="text-xs text-helm-muted block">What happened
                <textarea data-testid="report-summary" value={form.summary} maxLength={2000} onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))} rows={3} placeholder="Two new clients signed. Pipeline is up after the trade show." className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40 resize-none" />
              </label>
              <div>
                <p className="text-xs text-helm-muted mb-1">Key numbers (optional)</p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {form.metrics.map((m, i) => (
                    <div key={i}>
                      <input value={m.label} maxLength={60} onChange={(e) => setMetric(i, "label", e.target.value)} placeholder="Name, e.g. Deals won" aria-label={`Number ${i + 1} name`} className="w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-xs px-2 py-1.5 mb-1 focus:outline-none focus:border-helm-gold/40" />
                      <input value={m.value} maxLength={40} onChange={(e) => setMetric(i, "value", e.target.value)} placeholder="Value, e.g. 4" aria-label={`Number ${i + 1} value`} className="w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-xs px-2 py-1.5 focus:outline-none focus:border-helm-gold/40" />
                    </div>
                  ))}
                </div>
                {form.metrics.length < MAX_REPORT_METRICS && (
                  <button type="button" data-testid="report-add-metric" onClick={() => setForm((f) => ({ ...f, metrics: [...f.metrics, blankMetric()] }))}
                    className="mt-2 inline-flex items-center gap-1 text-xs text-helm-gold hover:text-helm-gold-hover">
                    <Plus className="w-3 h-3" /> Add a number
                  </button>
                )}
              </div>
            </div>
            <button data-testid="submit-report-btn" type="button" onClick={submit} disabled={busy} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : editing ? "Save changes" : publishingDraftId ? "Publish report" : "Save report"}</button>
          </GlassCard>
        </div>
      )}
    </div>
  );
}

/** Card header line: "Sales · Oct 12 to 18". Hides the old "Manual" placeholder period. */
export function reportMeta(r) {
  const period = r?.period === "Manual" ? "" : r?.period;
  return [r?.type, period].filter(Boolean).join(" · ");
}

function ReportCard({ report: r, index, canWrite, onEdit, onDelete, onAddToReport, hideSummary, source }) {
  const isAuto = r.source === "auto";
  const metrics = r.metrics || [];

  return (
    <GlassCard
      className={cn(
        "p-6 fade-up group relative flex flex-col h-full min-w-0",
        isAuto && "border-helm-gold/25 shadow-sm",
      )}
      style={{ animationDelay: `${index * 60}ms` }}
      data-testid={`report-${r.id}`}
    >
      {canWrite && onEdit && (
        <div className="absolute top-3 right-3 flex gap-1 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
          <button type="button" onClick={onEdit} className="text-helm-muted hover:text-helm-gold p-1" aria-label="Edit report" title="Edit report"><PenLine className="w-3.5 h-3.5" /></button>
          <CirDeleteBtn onClick={onDelete} title="Delete report" />
        </div>
      )}
      <div className="flex items-center gap-2.5 mb-3">
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-helm-gold/12 border border-helm-gold/25 shrink-0">
          <FileText className="w-3.5 h-3.5 text-helm-gold" />
        </span>
        <span className="text-[10px] uppercase tracking-wider text-helm-muted min-w-0 truncate">{isAuto ? r.period : reportMeta(r)}</span>
      </div>
      <h3 className="text-helm-fg text-base font-medium tracking-tight pr-8">{r.title}</h3>
      {!hideSummary && r.summary && (
        <p className="text-sm text-helm-muted mt-2.5 leading-relaxed">{r.summary}</p>
      )}
      {metrics.length > 0 && (
        <div className={cn(
          "grid gap-5 mt-5 pt-5 border-t border-helm-line",
          metrics.length >= 3 ? "grid-cols-1 sm:grid-cols-3" : "grid-cols-2",
        )}
        >
          {metrics.map((m, mi) => (
            <div key={`${m.label}-${mi}`} className="min-w-0">
              <p className="font-mono text-xl md:text-2xl tracking-tight text-helm-fg tabular-nums leading-none break-words">
                {m.value}
              </p>
              <p className="mt-2 text-[11px] leading-snug text-helm-muted">{m.label}</p>
              {m.change && (
                <p className="mt-1 text-[10px] leading-snug text-helm-muted/90">{m.change}</p>
              )}
            </div>
          ))}
        </div>
      )}
      {((canWrite && onAddToReport) || source) && (
        <div className="mt-auto pt-5 flex flex-wrap items-center gap-3">
          {canWrite && onAddToReport && (
            <button
              type="button"
              data-testid={`add-trend-to-report-${r.id}`}
              onClick={onAddToReport}
              className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5 hover:border-helm-fg/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> Save as report
            </button>
          )}
          {source && (
            <Link
              to={source.to}
              data-testid={`report-source-${r.id}`}
              className="inline-flex items-center gap-1 text-xs text-helm-gold hover:text-helm-gold-hover"
            >
              {source.label} <ArrowRight className="w-3 h-3" />
            </Link>
          )}
        </div>
      )}
    </GlassCard>
  );
}

function InlineText({ children }) {
  const parts = String(children || "").split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => (
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index} className="font-medium text-helm-fg">{part.slice(2, -2)}</strong>
      : <span key={index}>{part}</span>
  ));
}


function formatExportMoney(n, currency) {
  if (n === null || n === undefined) return "—";
  return formatMoney(n, currencySymbol(currency), { decimals: 2 });
}

function LedgerRow({ label, value, stamp, strong }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-4 border-b border-helm-navy/10 py-2.5 text-[13px] leading-relaxed">
      <div className="flex items-start gap-2.5 min-w-0">
        {stamp && <DocumentStamp label={stamp} className="mt-0.5 border-helm-navy/70 text-helm-navy/80" />}
        <p className={strong ? "font-medium text-helm-navy" : "text-helm-navy/90"}>{label}</p>
      </div>
      <p className="font-mono text-[13px] tabular-nums text-right text-helm-navy whitespace-nowrap">{value}</p>
    </div>
  );
}

/** Document-style Income Statement + Cash Summary for accountant export preview. */
function FinancialExportPreview({ bundle }) {
  if (!bundle) return null;
  const currency = bundle.currency || "usd";
  const income = bundle.income || {};
  const cash = bundle.cash || {};
  const items = bundle.line_items || [];
  const confirmed = Boolean(cash.ending_matches_dashboard);

  return (
    <div
      className="max-w-3xl bg-helm-cream text-helm-navy px-6 py-7 md:px-8 md:py-9 rounded-sm border border-helm-line"
      data-testid="formatted-financial-export"
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-helm-navy/50">Financial Export</p>
      <h2 className="mt-2 font-display text-2xl font-medium tracking-tight text-helm-navy">
        {bundle.workspace_name || "Company"}
      </h2>
      <p className="mt-1 text-sm text-helm-navy/60">{bundle.period_label || bundle.period}</p>
      <div className="mt-5 border-t border-helm-navy/25" />

      <h3 className="mt-6 mb-2 border-b border-helm-navy/20 pb-2 font-display text-xs font-medium uppercase tracking-[0.16em] text-helm-navy">
        Income Statement
      </h3>
      <LedgerRow label="Revenue" value={formatExportMoney(income.revenue, currency)} strong />
      {(income.expenses_by_category || []).map((row) => (
        <LedgerRow key={row.category} label={row.category} value={formatExportMoney(row.amount, currency)} />
      ))}
      <LedgerRow label="Total expenses" value={formatExportMoney(income.expenses_total, currency)} strong />
      <LedgerRow label="Net income" value={formatExportMoney(income.net_income, currency)} strong />

      <h3 className="mt-6 mb-2 border-b border-helm-navy/20 pb-2 font-display text-xs font-medium uppercase tracking-[0.16em] text-helm-navy">
        Line items
      </h3>
      {items.length === 0 ? (
        <p className="py-2.5 text-[13px] text-helm-navy/70 border-b border-helm-navy/10">None recorded this period</p>
      ) : (
        items.map((row, i) => (
          <LedgerRow
            key={`${row.name}-${i}`}
            label={`${row.name} (${row.category}, ${row.type})`}
            value={formatExportMoney(row.amount, currency)}
          />
        ))
      )}

      <h3 className="mt-6 mb-2 border-b border-helm-navy/20 pb-2 font-display text-xs font-medium uppercase tracking-[0.16em] text-helm-navy">
        Cash Summary
      </h3>
      {cash.entered ? (
        <>
          <LedgerRow label="Starting cash" value={formatExportMoney(cash.starting, currency)} />
          <LedgerRow label="Inflows (revenue)" value={formatExportMoney(cash.inflows, currency)} />
          <LedgerRow label="Outflows (expenses)" value={formatExportMoney(cash.outflows, currency)} />
          <LedgerRow
            label="Ending cash"
            value={formatExportMoney(cash.ending, currency)}
            stamp={confirmed ? "Confirmed" : null}
            strong
          />
        </>
      ) : (
        <p className="py-2.5 text-[13px] text-helm-navy/70 border-b border-helm-navy/10">
          Cash on hand has not been entered on Financials.
        </p>
      )}
      <p className="mt-5 text-[11px] text-helm-navy/50 leading-relaxed">
        Scope is Income Statement and Cash Summary only. No balance sheet is included.
      </p>
    </div>
  );
}

function PackPreview({ content }) {
  const lines = String(content || "").split("\n");
  return (
    <div
      className="max-w-3xl bg-helm-cream text-helm-navy px-6 py-7 md:px-8 md:py-9 rounded-sm border border-helm-line"
      data-testid="formatted-pack-content"
    >
      {lines.map((raw, index) => {
        const line = raw.trim();
        if (!line) return <div key={index} className="h-3" />;
        if (line.startsWith("# ")) {
          return (
            <h2 key={index} className="mb-3 font-display text-2xl font-medium tracking-tight text-helm-navy">
              <InlineText>{line.slice(2)}</InlineText>
            </h2>
          );
        }
        if (line.startsWith("## ")) {
          return (
            <h3
              key={index}
              className="mb-2 mt-6 border-b border-helm-navy/20 pb-2 font-display text-xs font-medium uppercase tracking-[0.16em] text-helm-navy"
            >
              <InlineText>{line.slice(3)}</InlineText>
            </h3>
          );
        }
        if (/^[-*]\s+/.test(line)) {
          const body = line.replace(/^[-*]\s+/, "");
          const stamp = stampLabelForLine(body);
          // Trailing figure goes in the right-hand column. Covers ₱, ₹, ¥ and S$ as well
          // as $ £ €, and leaves a bare year ("… in 2026") in the sentence.
          const rawMoney = body.match(/^(.*?)(\s+[–—-]\s+)?((?:S\$|[£$€₱₹¥])?-?[\d,]+\.?\d*\s*[KMB]?%?)\s*$/);
          const money = rawMoney && !/^(19|20)\d{2}$/.test(rawMoney[3].trim()) && rawMoney[1].trim() ? rawMoney : null;
          return (
            <div
              key={index}
              className="grid grid-cols-[1fr_auto] items-baseline gap-4 border-b border-helm-navy/10 py-2.5 text-[13px] leading-relaxed"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                {stamp && <DocumentStamp label={stamp} className="mt-0.5 border-helm-navy/70 text-helm-navy/80" />}
                <p className="text-helm-navy/90">
                  <InlineText>{money ? money[1].trim() : body}</InlineText>
                </p>
              </div>
              {money && money[3] && (
                <p className="font-mono text-[13px] tabular-nums text-right text-helm-navy whitespace-nowrap">
                  {money[3]}
                </p>
              )}
            </div>
          );
        }
        const numbered = line.match(/^\d+\.\s+(.*)$/);
        if (numbered) {
          const stamp = stampLabelForLine(numbered[1]);
          return (
            <div
              key={index}
              className="flex items-start gap-2.5 border-b border-helm-navy/10 py-2.5 text-[13px] leading-relaxed"
            >
              <span className="min-w-4 font-mono text-xs text-helm-navy/50">{line.match(/^\d+/)?.[0]}.</span>
              {stamp && <DocumentStamp label={stamp} className="mt-0.5 border-helm-navy/70 text-helm-navy/80" />}
              <p className="text-helm-navy/90"><InlineText>{numbered[1]}</InlineText></p>
            </div>
          );
        }
        if (line === "---") return <div key={index} className="my-5 border-t border-helm-navy/25" />;
        return (
          <p key={index} className="mb-2 text-[13px] leading-relaxed text-helm-navy/90">
            <InlineText>{line}</InlineText>
          </p>
        );
      })}
    </div>
  );
}
