import { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { FileText, Plus, PenLine, X, Copy, Download, Check } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage, blobErrorDetail } from "@/hooks/useFetch";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, SkeletonKPIRow, SkeletonChart, SkeletonCardList } from "@/components/kit";
import DocumentStamp, { stampLabelForLine } from "@/components/DocumentStamp";
import ReportsDailyDigest from "@/components/ReportsDailyDigest";
import AiSummaryMeta from "@/components/AiSummaryMeta";
import { cn } from "@/lib/utils";

const emptyReport = () => ({ title: "", type: "General", period: "", summary: "", metrics: [{ label: "", value: "" }, { label: "", value: "" }, { label: "", value: "" }] });

export default function Reports() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useFetch("/reports");
  const [pack, setPack] = useState("");
  const [packAsOf, setPackAsOf] = useState(null);
  const [busy, setBusy] = useState(false);
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

  useEffect(() => () => {
    if (copyTimer.current) clearTimeout(copyTimer.current);
  }, []);

  useEffect(() => {
    if (!data) return;
    const months = data.financial_months || [];
    const next = data.financial_latest_month || months[months.length - 1] || new Date().toISOString().slice(0, 7);
    setFinPeriod((prev) => prev || next);
  }, [data]);

  useEffect(() => {
    const canExport = Boolean(data?.can_export_financials);
    if (!canExport || !finPeriod) {
      setFinPreview(null);
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
  }, [data?.can_export_financials, finPeriod]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Reports" subtitle="Understand the week, add context, and create an update you can share." />
        <SkeletonKPIRow count={3} className="lg:grid-cols-3" />
        <div className="grid lg:grid-cols-2 gap-4 mb-6">
          <SkeletonChart />
          <SkeletonCardList count={3} />
        </div>
      </div>
    );
  }
  if (error || !data) {
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
      title: r.title,
      type: r.type,
      period: r.period,
      summary: r.summary,
      metrics: (r.metrics?.length ? r.metrics : emptyReport().metrics).slice(0, 3),
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
      metrics: (d.metrics?.length ? d.metrics : emptyReport().metrics).concat(emptyReport().metrics).slice(0, 3),
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
    if (!form.title.trim()) { toast.error("Title is required"); return; }
    setBusy(true);
    const payload = {
      ...form,
      metrics: form.metrics.filter((m) => m.label?.trim() && m.value?.toString().trim()),
    };
    try {
      if (editing) await api.patch(`/reports/${editing}`, payload);
      else await api.post("/reports", publishingDraftId ? { ...payload, from_draft_id: publishingDraftId } : payload);
      toast.success(editing ? "Report updated" : publishingDraftId ? "Report published" : "Report added");
      setShowForm(false);
      setPublishingDraftId(null);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save"); }
    finally { setBusy(false); }
  };

  const del = async (r) => {
    if (!window.confirm(`Delete "${r.title}"?`)) return;
    try { await api.delete(`/reports/${r.id}`); reload(); toast.success("Report removed"); }
    catch (e) { toast.error("Could not delete"); }
  };

  const generatePack = async () => {
    setBusy(true);
    try {
      const { data: res } = await api.post("/reports/weekly-pack");
      setPack(res.content);
      setPackAsOf(res.data_as_of || null);
      toast.success("Weekly update draft ready");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not generate CEO Pack");
    } finally {
      setBusy(false);
    }
  };

  const copyPack = async () => {
    if (!pack) return;
    try {
      await navigator.clipboard.writeText(pack);
      setCopied(true);
      toast.success("Weekly pack copied");
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy. Select the text instead");
    }
  };

  const downloadFinancialExport = async (kind) => {
    if (!finPeriod) return;
    setFinExporting(kind);
    try {
      const res = await api.post(
        `/reports/financial-export/${kind}`,
        { period: finPeriod },
        { responseType: "blob" },
      );
      const mime = kind === "pdf"
        ? "application/pdf"
        : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
      const blob = new Blob([res.data], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="([^"]+)"/);
      a.download = match?.[1] || `Trenston-Financial-Export.${kind}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
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
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="([^"]+)"/);
      a.download = match?.[1] || "Trenston-Weekly-Pack.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
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
    const metrics = (r.metrics || [])
      .map((m) => ({ label: m.label || "", value: m.value?.toString?.() ?? String(m.value ?? "") }))
      .filter((m) => m.label.trim() && m.value.toString().trim());
    const changeNotes = (r.metrics || [])
      .filter((m) => m.change && m.change !== "Current total" && m.change !== "No comparison yet")
      .map((m) => `${m.label}: ${m.change}`)
      .join(". ");
    setForm({
      title: r.title || "",
      type: "General",
      period: r.period || "",
      summary: changeNotes || r.summary || "",
      metrics: metrics.concat(emptyReport().metrics).slice(0, 3),
    });
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setPublishingDraftId(null);
  };

  const action = canWrite ? (
    <button data-testid="add-report-btn" onClick={openAdd}
      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover">
      <Plus className="w-4 h-4" /> Add report
    </button>
  ) : null;

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Understand the week, add context, and create an update you can share."
        action={action}
      />

      <GlassCard className="p-4 mb-6 fade-up border-helm-line">
        <p className="text-sm text-helm-muted leading-relaxed">
          <span className="text-helm-fg">What happens here:</span> Trenston tracks money, team, and completed work week over week.
          Turn a trend card into a report when you want context on the record. Then draft the CEO Pack for a
          plain-English update you can share.
        </p>
      </GlassCard>

      {drafts.length > 0 && (
        <div className="mb-8" data-testid="department-drafts">
          <SectionLabel className="mb-3">Suggested from your departments</SectionLabel>
          <p className="text-sm text-helm-muted mb-3">
            Rollups of completed department work this week. Review before they become a report. They are not published until you say so.
          </p>
          <div className="grid md:grid-cols-3 gap-4">
            {drafts.map((d, i) => (
              <GlassCard key={d.id} className="p-5 fade-up border-helm-gold/35" style={{ animationDelay: `${i * 60}ms` }} data-testid={`draft-${d.id}`}>
                <div className="flex items-center gap-2 mb-3">
                  <FileText className="w-4 h-4 text-helm-gold" />
                  <span className="text-[10px] font-mono uppercase tracking-wider text-helm-muted">{d.type} · {d.period}</span>
                  <span className="text-[9px] font-mono uppercase rounded px-1.5 py-0.5 ml-auto text-helm-gold bg-helm-gold/12">Draft</span>
                </div>
                <h3 className="text-helm-fg font-medium">{d.title}</h3>
                <p className="text-sm text-helm-muted mt-2 leading-relaxed">{d.summary}</p>
                {d.metrics?.length > 0 && (
                  <div className="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-helm-line">
                    {d.metrics.map((m) => (
                      <div key={m.label}>
                        <p className="font-mono text-lg text-helm-fg">{m.value}</p>
                        <p className="text-[10px] text-helm-muted uppercase tracking-wide">{m.label}</p>
                      </div>
                    ))}
                  </div>
                )}
                {canWrite && (
                  <div className="flex gap-2 mt-4">
                    <button
                      data-testid={`publish-draft-${d.id}`}
                      type="button"
                      onClick={() => openPublishDraft(d)}
                      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-3 py-2 hover:bg-helm-gold-hover"
                    >
                      <Check className="w-3.5 h-3.5" /> Publish
                    </button>
                    <button
                      data-testid={`dismiss-draft-${d.id}`}
                      type="button"
                      onClick={() => dismissDraft(d)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5"
                    >
                      <X className="w-3.5 h-3.5" /> Dismiss
                    </button>
                  </div>
                )}
              </GlassCard>
            ))}
          </div>
        </div>
      )}

      {manual.length > 0 && (
        <>
          <SectionLabel className="mb-3">Your reports</SectionLabel>
          <div className="grid md:grid-cols-3 gap-4 mb-8">
            {manual.map((r, i) => (
              <ReportCard key={r.id} report={r} index={i} canWrite={canWrite} onEdit={() => openEdit(r)} onDelete={() => del(r)} badge="Manual" />
            ))}
          </div>
        </>
      )}

      {manual.length === 0 && canWrite && (
        <div className="mb-8">
          <EmptyState title="No manual reports yet" body="Add your first report: weekly sales, production uptime, procurement status, or anything your team tracks." />
        </div>
      )}

      {auto.length > 0 && (
        <div className="mb-10" data-testid="week-over-week-trends">
          <SectionLabel className="mb-2">Week-over-week trends</SectionLabel>
          <p className="text-sm text-helm-muted mb-6 max-w-2xl leading-relaxed">
            Auto-generated from your data. Use these as a starting point for your own report.
          </p>
          <div className="grid gap-5 md:grid-cols-3">
            {auto.map((r, i) => (
              <ReportCard
                key={r.id}
                report={r}
                index={i}
                badge="Auto"
                canWrite={canWrite}
                onAddToReport={() => openFromTrend(r)}
              />
            ))}
          </div>
        </div>
      )}

      {canExportFinancials && (
        <GlassCard className="p-6 fade-up border-helm-line mb-6" data-testid="financial-export-card">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
            <div>
              <SectionLabel>Financial Export</SectionLabel>
              <p className="text-sm text-helm-muted max-w-xl mt-1">
                Income Statement, Cash Summary, and named line items for a selected month: the same figures as Financials, ready for your accountant. Not a balance sheet.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-end gap-3 shrink-0">
              <label className="text-xs text-helm-muted">
                Period
                <input
                  data-testid="financial-export-period"
                  type="month"
                  value={finPeriod}
                  onChange={(e) => setFinPeriod(e.target.value)}
                  className="mt-1 block rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  data-testid="financial-export-pdf-btn"
                  type="button"
                  onClick={() => downloadFinancialExport("pdf")}
                  disabled={Boolean(finExporting)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10 disabled:opacity-60"
                >
                  <Download className="w-3.5 h-3.5" />
                  {finExporting === "pdf" ? "Building PDF…" : "Download PDF"}
                </button>
                <button
                  data-testid="financial-export-xlsx-btn"
                  type="button"
                  onClick={() => downloadFinancialExport("xlsx")}
                  disabled={Boolean(finExporting)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10 disabled:opacity-60"
                >
                  <Download className="w-3.5 h-3.5" />
                  {finExporting === "xlsx" ? "Building Excel…" : "Download Excel"}
                </button>
              </div>
            </div>
          </div>
          {(finPreviewLoading || finPreview) && (
            <div className="mt-6" data-testid="financial-export-preview">
              {finPreviewLoading && !finPreview ? (
                <p className="text-xs text-helm-muted">Loading accountant view…</p>
              ) : (
                <FinancialExportPreview bundle={finPreview} />
              )}
            </div>
          )}
        </GlassCard>
      )}

      {canWrite && <ReportsDailyDigest canWrite={canWrite} />}

      <GlassCard className="p-6 fade-up border-helm-line">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
          <div>
            <SectionLabel>CEO Pack</SectionLabel>
            <p className="text-sm text-helm-muted max-w-xl mt-1">
              A one-page leadership update: what happened, what needs your attention, and what to do next.
              Trenston drafts it from the week-over-week trends above and any reports your team added.
            </p>
          </div>
          {canGeneratePack ? (
            <button data-testid="generate-pack-btn" onClick={generatePack} disabled={busy}
              className="inline-flex items-center gap-2 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60 shrink-0">
              <FileText className="w-4 h-4" />{busy ? "Drafting…" : "Draft CEO Pack"}
            </button>
          ) : (
            <p className="text-xs text-helm-muted shrink-0 max-w-xs text-right">
              {(user?.perms || []).includes("reports:pack")
                ? "CEO Pack needs a Growth plan or higher."
                : "Owner or executive access required to generate."}
            </p>
          )}
        </div>
        {pack && (
          <div className="mt-4 rounded-lg border border-helm-line bg-helm-ink/30 p-5" data-testid="pack-content">
            <AiSummaryMeta
              asOf={packAsOf}
              detailHref="/app/financials"
              detailLabel="Financials"
              className="mb-3"
            />
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <button
                data-testid="copy-pack-btn"
                type="button"
                onClick={copyPack}
                className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5"
              >
                <Copy className="w-3.5 h-3.5" />
                {copied ? "Copied" : "Copy"}
              </button>
              {canGeneratePack && (
                <button
                  data-testid="download-pack-pdf-btn"
                  type="button"
                  onClick={downloadPdf}
                  disabled={exporting}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10 disabled:opacity-60"
                >
                  <Download className="w-3.5 h-3.5" />
                  {exporting ? "Building PDF…" : "Download PDF"}
                </button>
              )}
            </div>
            <PackPreview content={pack} />
          </div>
        )}
      </GlassCard>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={closeForm} />
          <GlassCard className="relative w-full sm:max-w-lg m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="report-form">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg text-helm-fg font-light">{editing ? "Edit report" : publishingDraftId ? "Review department draft" : "Add a report"}</h3>
              <button onClick={closeForm} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <label className="text-xs text-helm-muted block">Title
                <input data-testid="report-title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Sales Performance" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-helm-muted">Type
                  <input value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))} placeholder="Sales" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
                </label>
                <label className="text-xs text-helm-muted">Period
                  <input value={form.period} onChange={(e) => setForm((f) => ({ ...f, period: e.target.value }))} placeholder="This week" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
                </label>
              </div>
              <label className="text-xs text-helm-muted block">Summary
                <textarea value={form.summary} onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))} rows={3} placeholder="What happened and why it matters…" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40 resize-none" />
              </label>
              <div className="grid grid-cols-3 gap-2">
                {form.metrics.map((m, i) => (
                  <div key={i}>
                    <input value={m.label} onChange={(e) => setForm((f) => { const metrics = [...f.metrics]; metrics[i] = { ...metrics[i], label: e.target.value }; return { ...f, metrics }; })} placeholder="Metric" className="w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-xs px-2 py-1.5 mb-1 focus:outline-none focus:border-helm-gold/40" />
                    <input value={m.value} onChange={(e) => setForm((f) => { const metrics = [...f.metrics]; metrics[i] = { ...metrics[i], value: e.target.value }; return { ...f, metrics }; })} placeholder="Value" className="w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-xs px-2 py-1.5 focus:outline-none focus:border-helm-gold/40" />
                  </div>
                ))}
              </div>
            </div>
            <button data-testid="submit-report-btn" onClick={submit} disabled={busy} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : editing ? "Save report" : publishingDraftId ? "Publish report" : "Add report"}</button>
          </GlassCard>
        </div>
      )}
    </div>
  );
}

function ReportCard({ report: r, index, canWrite, onEdit, onDelete, onAddToReport, badge, hideSummary }) {
  const isAuto = badge === "Auto" || badge === "Updated automatically" || r.source === "auto";
  const metrics = r.metrics || [];

  return (
    <GlassCard
      className={cn(
        "p-6 fade-up group relative flex flex-col h-full",
        isAuto && "border-helm-gold/25 shadow-sm",
      )}
      style={{ animationDelay: `${index * 60}ms` }}
      data-testid={`report-${r.id}`}
    >
      {canWrite && onEdit && (
        <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button type="button" onClick={onEdit} className="text-helm-muted hover:text-helm-gold p-1" aria-label="Edit report"><PenLine className="w-3.5 h-3.5" /></button>
          <CirDeleteBtn onClick={onDelete} title="Delete report" />
        </div>
      )}
      <div className="flex items-center gap-2.5 mb-3">
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-helm-gold/12 border border-helm-gold/25 shrink-0">
          <FileText className="w-3.5 h-3.5 text-helm-gold" />
        </span>
        <span className="text-[10px] uppercase tracking-wider text-helm-muted min-w-0 truncate">{r.type} · {r.period}</span>
        {badge && (
          <span className="text-[9px] uppercase tracking-wide rounded px-1.5 py-0.5 ml-auto shrink-0 text-helm-gold bg-helm-gold/12">
            {badge}
          </span>
        )}
      </div>
      <h3 className="text-helm-fg text-base font-medium tracking-tight pr-8">{r.title}</h3>
      {!hideSummary && r.summary && (
        <p className="text-sm text-helm-muted mt-2.5 leading-relaxed">{r.summary}</p>
      )}
      {metrics.length > 0 && (
        isAuto ? (
          <ul className="mt-5 pt-5 border-t border-helm-line space-y-4">
            {metrics.map((m) => (
              <li key={m.label} className="flex items-start justify-between gap-4 min-w-0">
                <div className="min-w-0">
                  <p className="text-[11px] leading-snug text-helm-muted">{m.label}</p>
                  {m.change && (
                    <p className="mt-1 text-[10px] leading-snug text-helm-muted/90">{m.change}</p>
                  )}
                </div>
                <p className="font-mono text-lg md:text-xl tracking-tight text-helm-fg tabular-nums leading-snug text-right shrink-0 max-w-[55%] break-words">
                  {m.value}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <div className={cn(
            "grid gap-4 mt-5 pt-5 border-t border-helm-line",
            metrics.length >= 3 ? "grid-cols-3" : "grid-cols-2",
          )}
          >
            {metrics.map((m) => (
              <div key={m.label} className="min-w-0">
                <p className="font-mono text-xl md:text-2xl tracking-tight text-helm-fg tabular-nums leading-none">{m.value}</p>
                <p className="mt-1.5 text-[11px] leading-snug text-helm-muted">{m.label}</p>
                {m.change && (
                  <p className="mt-1 text-[10px] leading-snug text-helm-muted">{m.change}</p>
                )}
              </div>
            ))}
          </div>
        )
      )}
      {canWrite && onAddToReport && (
        <button
          type="button"
          data-testid={`add-trend-to-report-${r.id}`}
          onClick={onAddToReport}
          className="mt-auto pt-5 inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2 hover:bg-helm-fg/5 hover:border-helm-fg/20 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> Add to report
        </button>
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


function formatExportMoney(n, currency = "usd") {
  if (n === null || n === undefined) return "—";
  const sym = currency === "gbp" ? "£" : currency === "eur" ? "€" : "$";
  return `${sym}${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
          const money = body.match(/^(.*?)(\s+[–—-]\s+)?([£$€]?[\d,]+\.?\d*\s*[KMB]?%?)\s*$/);
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
