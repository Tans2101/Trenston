import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Plus, Wallet, X, PenLine, History, Upload, Sparkles, FileText, AlertTriangle, FileSpreadsheet, Sheet } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, SkeletonKPIRow, SkeletonChart, SkeletonCardList } from "@/components/kit";
import { Gauge } from "@/components/charts/gauge";
import { cn } from "@/lib/utils";
import { formatAxisMoney } from "@/lib/formatAxisMoney";
import palette from "@/design/palette.json";

const GOLD = palette.gold;
const CREAM = palette.cream;
const PIE = [palette.gold, palette.navy, palette.slate, palette.inkCard, palette.ink, palette.cream];
const REV_CATS = ["Subscriptions", "Enterprise", "Services", "Other"];
const EXP_CATS = ["Payroll", "Cloud/Infra", "Sales & Mktg", "G&A", "R&D Tools", "Other"];
const ALLOWED_UPLOAD_TYPES = ["application/pdf", "image/png", "image/jpeg"];
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
const CURRENCY_OPTIONS = [
  { code: "usd", label: "USD ($)" },
  { code: "php", label: "PHP (₱)" },
  { code: "eur", label: "EUR (€)" },
  { code: "gbp", label: "GBP (£)" },
  { code: "sgd", label: "SGD (S$)" },
  { code: "inr", label: "INR (₹)" },
];

const thisMonth = () => new Date().toISOString().slice(0, 7);
const fmt = (n, sym = "$") => `${sym}${Number(n || 0).toLocaleString()}`;

function ChartTooltip({ active, payload, label, symbol = "$" }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-helm-line bg-helm-card px-3 py-2 text-xs">
      {label && <p className="text-helm-muted mb-1 font-mono">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="text-helm-fg font-mono">
          <span style={{ color: p.color }}>●</span> {p.name}: {fmt(p.value, symbol)}
        </p>
      ))}
    </div>
  );
}

const emptyForm = () => ({
  type: "revenue", category: "Subscriptions", name: "", amount: "", month: thisMonth(),
  recurring: true, recurrence: "monthly", note: "", source_document_id: null, extract_confidence: null,
});

function mapCategory(type, raw) {
  const cats = type === "revenue" ? REV_CATS : EXP_CATS;
  if (!raw) return "Other";
  const norm = String(raw).trim().toLowerCase();
  const exact = cats.find((c) => c.toLowerCase() === norm);
  if (exact) return exact;
  const partial = cats.find((c) => norm.includes(c.toLowerCase().split("/")[0]) || c.toLowerCase().includes(norm));
  return partial || "Other";
}

function itemNameFromExtract(extracted) {
  const name = String(extracted?.name || "").trim();
  if (name) return name;
  return String(extracted?.vendor || "").trim();
}

export default function Financials() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data, loading, error, reload } = useFetch("/financials");
  const { data: activityData, reload: reloadActs } = useFetch("/activities");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [busy, setBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [cash, setCash] = useState("");
  const [gm, setGm] = useState("");
  const [currency, setCurrency] = useState("usd");
  const [csvPreview, setCsvPreview] = useState(null);
  const [csvBusy, setCsvBusy] = useState(false);
  const [sheetsBusy, setSheetsBusy] = useState(false);
  const fileInputRef = useRef(null);
  const csvInputRef = useRef(null);

  const processBillFile = useCallback(async (file) => {
    if (!file) return;
    if (!ALLOWED_UPLOAD_TYPES.includes(file.type)) {
      toast.error("Use PDF, PNG, or JPEG only");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      toast.error("File must be 15MB or smaller");
      return;
    }
    setUploadBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data: uploaded } = await api.post("/documents/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 60000,
      });
      const { data: extracted } = await api.post(
        `/documents/${uploaded.document_id}/extract`,
        {},
        { timeout: 120000 },
      );
      if (extracted?.error === "not_financial") {
        toast.error("This doesn't look like a bill or invoice. Upload a financial document only.");
        return;
      }
      if (extracted?.error === "unparseable_amount") {
        toast.error("Couldn't read a clear amount from this document. Try entering it manually.");
        return;
      }
      const entryType = extracted.type === "revenue" ? "revenue" : "expense";
      const extractedName = itemNameFromExtract(extracted);
      const extraNote = String(extracted.note || "").trim();
      setForm({
        type: entryType,
        category: mapCategory(entryType, extracted.category),
        name: extractedName,
        amount: extracted.amount != null ? String(extracted.amount) : "",
        month: extracted.month || thisMonth(),
        recurring: entryType === "revenue",
        recurrence: "monthly",
        note: extraNote && extraNote !== extractedName ? extraNote : "",
        source_document_id: uploaded.document_id,
        extract_confidence: extracted.confidence || "medium",
      });
      setShowForm(true);
      toast.success("Review the extracted entry and save when it looks right");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not process document");
    } finally {
      setUploadBusy(false);
      setDragOver(false);
    }
  }, []);

  const onFilePick = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    processBillFile(file);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    processBillFile(file);
  };

  const importFromDrive = async () => {
    if (!data.google?.connected) {
      toast.error("Connect Google on Integrations to import from Drive");
      navigate("/app/integrations");
      return;
    }
    if (!data.google?.drive_file) {
      toast.error("Reconnect Google on Integrations to import from Drive");
      navigate("/app/integrations");
      return;
    }
    setUploadBusy(true);
    try {
      const { data: cfg } = await api.get("/integrations/google/picker");
      if (cfg?.access_denied) {
        toast.error("Only the teammate who connected Google (or an owner) can import from Drive");
        return;
      }
      if (cfg?.needs_reconnect) {
        toast.error("Reconnect Google on Integrations to import from Drive");
        navigate("/app/integrations");
        return;
      }
      if (!cfg?.configured) {
        toast.error("Drive import is not available yet");
        return;
      }
      const { pickDriveBill } = await import("@/lib/googlePicker");
      const picked = await pickDriveBill({
        apiKey: cfg.api_key,
        appId: cfg.app_id,
        accessToken: cfg.access_token,
      });
      if (!picked?.fileId) return;
      const { data: uploaded } = await api.post("/documents/from-drive", { file_id: picked.fileId }, { timeout: 60000 });
      const { data: extracted } = await api.post(
        `/documents/${uploaded.document_id}/extract`,
        {},
        { timeout: 120000 },
      );
      if (extracted?.error === "not_financial") {
        toast.error("This doesn't look like a bill or invoice. Pick a financial document.");
        return;
      }
      if (extracted?.error === "unparseable_amount") {
        toast.error("Couldn't read a clear amount from this document. Try entering it manually.");
        return;
      }
      const entryType = extracted.type === "revenue" ? "revenue" : "expense";
      const extractedName = itemNameFromExtract(extracted);
      const extraNote = String(extracted.note || "").trim();
      setForm({
        type: entryType,
        category: mapCategory(entryType, extracted.category),
        name: extractedName,
        amount: extracted.amount != null ? String(extracted.amount) : "",
        month: extracted.month || thisMonth(),
        recurring: entryType === "revenue",
        recurrence: "monthly",
        note: extraNote && extraNote !== extractedName ? extraNote : "",
        source_document_id: uploaded.document_id,
        extract_confidence: extracted.confidence || "medium",
      });
      setShowForm(true);
      toast.success("Review the extracted entry and save when it looks right");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || "Could not import from Drive");
    } finally {
      setUploadBusy(false);
    }
  };

  const exportToSheets = async () => {
    if (!data.google?.connected) {
      toast.error("Connect Google on Integrations to export to Sheets");
      navigate("/app/integrations");
      return;
    }
    if (!data.google?.sheets) {
      toast.error("Reconnect Google on Integrations to export to Sheets");
      navigate("/app/integrations");
      return;
    }
    setSheetsBusy(true);
    try {
      const { data: res } = await api.post("/financials/export-sheets", {}, { timeout: 45000 });
      if (res?.url) {
        window.open(res.url, "_blank", "noopener,noreferrer");
        toast.success("Opened a Google Sheet with this ledger");
      } else {
        toast.error("Sheet was created but no URL came back");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reconnect Google to export to Sheets");
    } finally {
      setSheetsBusy(false);
    }
  };

  const openDocument = async (docId) => {
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    try {
      const { data: doc } = await api.get(`/documents/${docId}`);
      if (doc?.presigned_url) {
        if (tab) tab.location.href = doc.presigned_url;
        else window.open(doc.presigned_url, "_blank", "noopener,noreferrer");
      } else {
        tab?.close();
        toast.error("Could not open document");
      }
    } catch {
      tab?.close();
      toast.error("Could not open document");
    }
  };

  // Deep links from Briefing "Add data" metrics (#log-mrr, #log-entry, #cash).
  // Must run before any early returns so hooks stay unconditional.
  useEffect(() => {
    const hash = (location.hash || "").replace(/^#/, "");
    if (!hash || loading || !data?.can_write) return undefined;
    if (hash === "log-mrr" || hash === "log-entry") {
      setForm(emptyForm());
      setShowForm(true);
      setShowSettings(false);
    } else if (hash === "cash") {
      setCash(data.cash_entered ? String(data.settings?.cash ?? 0) : "");
      setGm(data.settings?.gross_margin != null ? String(data.settings.gross_margin) : "");
      setCurrency(data.settings?.currency || data.currency || "usd");
      setShowSettings(true);
      setShowForm(false);
    } else {
      return undefined;
    }
    window.history.replaceState(null, "", location.pathname);
    return undefined;
  }, [location.hash, location.pathname, loading, data]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Financials" subtitle="Your finance team logs revenue and expenses here. Trenston turns it into live MRR, runway and burn across the whole cockpit." />
        <SkeletonKPIRow count={4} />
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
        label="Could not load financials"
        message={fetchErrorMessage(error, "Financial data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  const canWrite = data.can_write;
  const accounting = data.accounting || {};
  const hasAccountingSync = Boolean(accounting.connected);
  const accountingLabel = accounting.label || "your accounting system";
  const finActs = (activityData?.items || activityData?.activities || []).filter((a) => a.module === "financials").slice(0, 5);
  const sym = data.currency_symbol || "$";

  const findLikelySyncedDuplicate = (payload) => {
    const amount = Number(payload.amount);
    const month = payload.month;
    if (!Number.isFinite(amount) || !month) return null;
    return (data.entries || []).find((e) => {
      const src = String(e.source || "");
      if (!src.includes("sync") && !src.startsWith("qbo") && !src.startsWith("xero") && !src.startsWith("sap")) {
        return false;
      }
      if (e.month !== month) return false;
      return Math.abs(Number(e.amount) - amount) < 0.02;
    }) || null;
  };

  const submitEntry = async () => {
    if (!form.name?.trim() || !form.amount || !form.month) {
      toast.error("Add a name, amount, and month");
      return;
    }
    const amount = parseFloat(form.amount);
    if (!Number.isFinite(amount)) {
      toast.error("Enter a valid amount");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        type: form.type,
        category: form.category,
        name: form.name.trim(),
        amount,
        month: form.month,
        recurring: form.recurring,
        recurrence: form.recurring ? (form.type === "expense" ? form.recurrence : "monthly") : null,
        note: form.note,
      };
      if (form.source_document_id) payload.source_document_id = form.source_document_id;
      if (hasAccountingSync) {
        const dup = findLikelySyncedDuplicate(payload);
        if (dup) {
          const ok = window.confirm(
            `A synced entry for about the same amount already exists in ${dup.month}`
            + `${dup.name ? ` (${dup.name})` : ""}. Save anyway? Manual duplicates can inflate MRR, burn, and cash.`,
          );
          if (!ok) return;
        }
      }
      await api.post("/financials/entries", payload);
      toast.success("Entry logged");
      setForm(emptyForm());
      setShowForm(false);
      reload();
      reloadActs();
    } catch (e) { toast.error(fetchErrorMessage(e, "Could not save")); }
    finally { setBusy(false); }
  };

  const del = async (id) => {
    if (!window.confirm("Remove this entry? This can't be undone.")) return;
    try { await api.delete(`/financials/entries/${id}`); reload(); reloadActs(); toast.success("Entry removed"); }
    catch (e) { toast.error("Could not delete"); }
  };

  const saveSettings = async () => {
    const cashRaw = String(cash ?? "").trim();
    const cashValue = cashRaw === "" ? null : parseFloat(cashRaw);
    const gmValue = gm ? parseFloat(gm) : null;
    if (cashValue != null && !Number.isFinite(cashValue)) {
      toast.error("Enter a valid cash amount");
      return;
    }
    if (gmValue != null && !Number.isFinite(gmValue)) {
      toast.error("Enter a valid gross margin");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        gross_margin: gmValue,
        currency,
      };
      // Only send cash when the user entered a value — empty must not become confirmed $0.
      if (cashValue != null) {
        payload.cash = cashValue;
      }
      await api.put("/financials/settings", payload);
      toast.success("Updated");
      setShowSettings(false);
      reload();
      reloadActs();
    } catch (e) { toast.error(fetchErrorMessage(e, "Could not save")); }
    finally { setBusy(false); }
  };

  const openSettings = () => {
    setCash(data.cash_entered ? String(data.settings?.cash ?? 0) : "");
    setGm(data.settings?.gross_margin != null ? String(data.settings.gross_margin) : "");
    setCurrency(data.settings?.currency || data.currency || "usd");
    setShowSettings(true);
  };

  const previewCsv = async (file) => {
    if (!file) return;
    if (!file.name?.toLowerCase().endsWith(".csv") && file.type && !file.type.includes("csv") && file.type !== "text/plain") {
      toast.error("Please choose a .csv file");
      return;
    }
    setCsvBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data: preview } = await api.post("/financials/import-csv", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setCsvPreview(preview);
      toast.success(`Parsed ${preview.valid_count || 0} row(s). Review before importing`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not parse CSV");
    } finally {
      setCsvBusy(false);
    }
  };

  const confirmCsvImport = async () => {
    if (!csvPreview?.valid?.length) {
      toast.error("No valid rows to import");
      return;
    }
    if (hasAccountingSync) {
      const overlaps = csvPreview.valid.filter((row) => findLikelySyncedDuplicate(row));
      if (overlaps.length > 0) {
        const ok = window.confirm(
          `${overlaps.length} CSV row${overlaps.length === 1 ? "" : "s"} look similar to entries already synced from ${accountingLabel}. Import anyway? Manual duplicates can inflate MRR, burn, and cash.`,
        );
        if (!ok) return;
      }
    }
    setCsvBusy(true);
    try {
      const { data: res } = await api.post("/financials/import-csv/confirm", { entries: csvPreview.valid });
      toast.success(`Imported ${res.imported_count} entr${res.imported_count === 1 ? "y" : "ies"}`);
      setCsvPreview(null);
      reload();
      reloadActs();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import failed");
    } finally {
      setCsvBusy(false);
    }
  };

  const headline = [
    { label: "MRR", value: data.mrr_known === false ? "Add data" : data.mrr },
    { label: "ARR", value: data.mrr_known === false ? "Add data" : data.arr },
    {
      label: "Runway",
      value:
        data.runway_months != null
          ? `${data.runway_months} months`
          : data.runway_no_burn
            ? "No burn — cash growing"
            : "Add data",
    },
    { label: "Net Burn", value: data.burn_known === false ? "Add data" : data.burn },
    { label: "Cash", value: data.cash_entered === false ? "Add data" : data.cash },
    {
      label: "Gross Margin",
      value: !data.gross_margin || data.gross_margin === "—" ? "Add data" : data.gross_margin,
    },
  ];

  const actions = canWrite ? (
    <button
      type="button"
      data-testid="add-entry-btn"
      onClick={() => { setForm(emptyForm()); setShowForm(true); }}
      className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 transition-colors hover:bg-helm-gold-hover"
    >
      <Plus className="w-4 h-4" /> {hasAccountingSync ? "Add one-off entry" : "Log entry"}
    </button>
  ) : null;

  return (
    <div>
      <PageHeader
        title="Financials"
        subtitle={
          hasAccountingSync
            ? `Numbers sync from ${accountingLabel}. Use manual entry only for items that will not appear in your books.`
            : "Log revenue and expenses here — or connect QuickBooks, Xero, or SAP Business One under Integrations. Trenston turns it into live MRR, runway, and burn."
        }
        action={actions}
      />

      {csvPreview && (
        <GlassCard className="p-5 mb-6 fade-up" data-testid="csv-import-preview">
          {hasAccountingSync && (
            <p className="mb-3 text-xs text-helm-muted leading-relaxed" data-testid="csv-accounting-sync-note">
              Your financials sync from {accountingLabel}. Import only rows that are not already in synced books.
            </p>
          )}
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-helm-gold">CSV import preview</p>
              <p className="text-sm text-helm-muted mt-1">
                {csvPreview.valid_count} ready · {csvPreview.skipped_count} skipped
                {csvPreview.filename ? ` · ${csvPreview.filename}` : ""}. Nothing is saved until you confirm.
              </p>
            </div>
            <button type="button" onClick={() => setCsvPreview(null)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button>
          </div>
          {csvPreview.valid?.length > 0 && (
            <div className="overflow-x-auto mb-4 max-h-48 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] font-mono uppercase tracking-wider text-helm-muted border-b border-helm-line">
                    <th className="py-2 pr-3">Month</th><th className="py-2 pr-3">Type</th>
                    <th className="py-2 pr-3">Name</th><th className="py-2 pr-3">Category</th>
                    <th className="py-2 pr-3 text-right">Amount</th>
                    <th className="py-2">Note</th>
                  </tr>
                </thead>
                <tbody>
                  {csvPreview.valid.slice(0, 50).map((r, i) => (
                    <tr key={i} className="border-b border-helm-fg/[0.03]" data-testid={`csv-valid-${i}`}>
                      <td className="py-1.5 pr-3 font-mono text-helm-muted">{r.month}</td>
                      <td className="py-1.5 pr-3 text-helm-fg">{r.type}</td>
                      <td className="py-1.5 pr-3 text-helm-fg">{r.name || r.category}</td>
                      <td className="py-1.5 pr-3 text-helm-muted">{r.category}</td>
                      <td className="py-1.5 pr-3 text-right font-mono text-helm-fg">{fmt(r.amount, sym)}</td>
                      <td className="py-1.5 text-helm-muted truncate max-w-[140px]">{r.note || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {csvPreview.valid.length > 50 && (
                <p className="text-xs text-helm-muted mt-2">Showing first 50 of {csvPreview.valid.length} valid rows.</p>
              )}
            </div>
          )}
          {csvPreview.skipped?.length > 0 && (
            <div className="mb-4 rounded-lg border border-helm-status-warning/35 bg-helm-status-warning/12 p-3" data-testid="csv-skipped-list">
              <p className="text-xs text-helm-status-warning mb-2">Skipped rows</p>
              <ul className="space-y-1 max-h-28 overflow-y-auto">
                {csvPreview.skipped.map((s) => (
                  <li key={s.row} className="text-xs text-helm-muted font-mono">Row {s.row}: {s.reason}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              data-testid="confirm-csv-import-btn"
              disabled={csvBusy || !csvPreview.valid?.length}
              onClick={confirmCsvImport}
              className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover disabled:opacity-60"
            >
              {csvBusy ? "Importing…" : `Confirm import (${csvPreview.valid_count || 0})`}
            </button>
            <button type="button" onClick={() => setCsvPreview(null)} className="rounded-md border border-helm-line text-helm-muted text-sm px-4 py-2 hover:bg-helm-fg/5">
              Cancel
            </button>
          </div>
        </GlassCard>
      )}
      {canWrite && (
        <div className="mb-6 fade-up">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            className="hidden"
            data-testid="bill-file-input"
            onChange={onFilePick}
          />
          <input
            ref={csvInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            data-testid="csv-file-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              previewCsv(f);
            }}
          />
          <div
            data-testid="bill-dropzone"
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={cn(
              "rounded-xl border border-dashed px-4 py-4 sm:px-5 sm:py-5 transition-colors",
              dragOver ? "border-helm-gold/35 bg-helm-gold/12" : "border-helm-line bg-helm-fg/[0.02]",
              uploadBusy && "opacity-70 pointer-events-none",
            )}
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-3 min-w-0">
                <div className="w-9 h-9 rounded-lg bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center shrink-0">
                  <Upload className="w-4 h-4 text-helm-gold" />
                </div>
                <div className="min-w-0 text-left">
                  <p className="text-sm text-helm-fg">
                    {hasAccountingSync ? "Add a one-off not in your synced books" : "Add bills & ledger data"}
                  </p>
                  <p className="text-xs text-helm-muted mt-0.5 leading-relaxed">
                    {hasAccountingSync
                      ? `Financials sync from ${accountingLabel}. Use upload, CSV, or a manual entry only for reimbursements, cash payments, or other items sync will not catch.`
                      : "Drop a PDF, PNG, or JPEG here · up to 15MB · Claude reads it and pre-fills an entry to confirm"}
                  </p>
                </div>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center lg:justify-end shrink-0">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    data-testid="upload-bill-btn"
                    disabled={uploadBusy || csvBusy}
                    onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold font-medium text-sm px-3 py-2 transition-colors hover:bg-helm-gold/10 disabled:opacity-60"
                  >
                    <Upload className="w-4 h-4" />
                    {uploadBusy ? "Reading bill…" : (hasAccountingSync ? "Upload one-off bill" : "Upload a bill")}
                  </button>
                  <button
                    type="button"
                    data-testid="import-drive-btn"
                    disabled={uploadBusy || csvBusy}
                    onClick={importFromDrive}
                    className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg font-medium text-sm px-3 py-2 transition-colors hover:bg-helm-fg/5 disabled:opacity-60"
                  >
                    <FileText className="w-4 h-4" />
                    From Drive
                  </button>
                </div>
                <span className="hidden sm:block w-px h-5 bg-helm-line self-center" aria-hidden />
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    data-testid="import-csv-btn"
                    disabled={uploadBusy || csvBusy}
                    onClick={() => csvInputRef.current?.click()}
                    className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-muted font-medium text-sm px-3 py-2 transition-colors hover:bg-helm-fg/5 hover:text-helm-fg disabled:opacity-60"
                  >
                    <FileSpreadsheet className="w-4 h-4" />
                    {csvBusy ? "Reading CSV…" : (hasAccountingSync ? "Import one-off CSV" : "Import CSV")}
                  </button>
                  <button
                    type="button"
                    data-testid="export-sheets-btn"
                    disabled={sheetsBusy || !data.has_data}
                    onClick={exportToSheets}
                    className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-muted font-medium text-sm px-3 py-2 transition-colors hover:bg-helm-fg/5 hover:text-helm-fg disabled:opacity-60"
                  >
                    <Sheet className="w-4 h-4" />
                    {sheetsBusy ? "Creating Sheet…" : "Export Sheets"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {!data.has_data ? (
        <EmptyState icon={Wallet} title="No financials logged yet"
          body={
            hasAccountingSync
              ? `Connect and sync ${accountingLabel} under Integrations, or add a one-off entry for anything sync will not include.`
              : "Log your revenue and expenses and Trenston computes MRR, ARR, runway, and burn automatically."
          }
          action={canWrite ? (
            <div className="flex flex-wrap items-center justify-center gap-2">
              <button data-testid="empty-upload-bill-btn" onClick={() => fileInputRef.current?.click()} disabled={uploadBusy}
                className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold font-medium text-sm px-4 py-2 hover:bg-helm-gold/10 disabled:opacity-60">
                <Upload className="w-4 h-4" /> {hasAccountingSync ? "Upload one-off bill" : "Upload a bill"}
              </button>
              <button data-testid="empty-add-entry-btn" onClick={() => { setForm(emptyForm()); setShowForm(true); }}
                className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover">
                <Plus className="w-4 h-4" /> {hasAccountingSync ? "Add one-off entry" : "Log first entry"}
              </button>
              <button data-testid="empty-settings-btn" onClick={openSettings}
                className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg font-medium text-sm px-4 py-2 hover:bg-helm-fg/5">
                <PenLine className="w-4 h-4" /> Cash & currency
              </button>
            </div>
          ) : <p className="text-sm text-helm-muted">Ask a workspace owner or finance teammate to add data.</p>}
        />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
            {headline.map((h) => (
              <GlassCard key={h.label} className="p-4 fade-up" data-testid={`fin-${h.label}`}>
                <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-helm-muted">{h.label}</p>
                <p className="font-mono text-2xl text-helm-fg mt-2">{h.value}</p>
              </GlassCard>
            ))}
          </div>

          {finActs.length > 0 && (
            <GlassCard className="p-4 mb-6 fade-up" data-testid="financials-activity">
              <div className="flex items-center gap-1.5 mb-3 text-helm-gold">
                <History className="w-3.5 h-3.5" />
                <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Recent activity</span>
              </div>
              <div className="space-y-2">
                {finActs.map((a) => (
                  <div key={a.activity_id} className="flex items-center gap-2 text-sm" data-testid={`fin-activity-${a.activity_id}`}>
                    <span className="w-1.5 h-1.5 rounded-full bg-helm-gold/60 shrink-0" />
                    <span className="text-helm-fg flex-1 truncate">{a.summary}</span>
                    <span className="text-xs text-helm-muted font-mono shrink-0 hidden sm:inline">{a.actor_name} · {a.ago}</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          <div className="grid lg:grid-cols-3 gap-4 mb-6">
            <GlassCard className="p-5 lg:col-span-2 fade-up">
              <SectionLabel className="mb-4">Revenue vs Expenses</SectionLabel>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={data.revenue_series} margin={{ left: -8, right: 8, top: 8 }}>
                  <defs><linearGradient id="rev" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={GOLD} stopOpacity={0.35} /><stop offset="100%" stopColor={GOLD} stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="month" stroke={palette.slate} fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke={palette.slate} fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => formatAxisMoney(v, { symbol: sym })} width={48} />
                  <Tooltip content={<ChartTooltip symbol={sym} />} />
                  <Area type="monotone" dataKey="revenue" name="Revenue" stroke={GOLD} strokeWidth={2} fill="url(#rev)" />
                  <Area type="monotone" dataKey="expenses" name="Expenses" stroke={palette.slate} strokeWidth={1.5} fill="none" strokeDasharray="4 4" />
                </AreaChart>
              </ResponsiveContainer>
            </GlassCard>

            <GlassCard className="p-5 fade-up">
              <div className="flex items-center justify-between mb-2">
                <SectionLabel>Cash & margin</SectionLabel>
                {canWrite && <button data-testid="edit-settings-btn" onClick={openSettings} className="text-helm-muted hover:text-helm-gold"><PenLine className="w-3.5 h-3.5" /></button>}
              </div>
              {data.expense_breakdown.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={170}>
                    <PieChart><Pie data={data.expense_breakdown} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={44} outerRadius={72} paddingAngle={2} stroke="none">{data.expense_breakdown.map((_, i) => <Cell key={i} fill={PIE[i % PIE.length]} />)}</Pie><Tooltip content={<ChartTooltip symbol={sym} />} /></PieChart>
                  </ResponsiveContainer>
                  <div className="space-y-1 mt-1">
                    {data.expense_breakdown.map((e, i) => (
                      <div key={e.name} className="flex items-center gap-2 text-xs"><span className="w-2 h-2 rounded-sm" style={{ background: PIE[i % PIE.length] }} /><span className="text-helm-muted flex-1">{e.name}</span><span className="font-mono text-helm-fg">{e.value}%</span></div>
                    ))}
                  </div>
                </>
              ) : <p className="text-sm text-helm-muted py-8 text-center">Log expenses to see the breakdown.</p>}
            </GlassCard>
          </div>

          {data.scenarios.length > 0 && (
            <div className="grid lg:grid-cols-3 gap-4 mb-6">
              <GlassCard className="p-5 lg:col-span-2 fade-up">
                <SectionLabel className="mb-4">Monthly Net Burn</SectionLabel>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={data.burn_series} margin={{ left: -8, right: 8 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis dataKey="month" stroke={palette.slate} fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke={palette.slate} fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => formatAxisMoney(v, { symbol: sym })} width={48} />
                    <Tooltip content={<ChartTooltip symbol={sym} />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                    <Bar dataKey="burn" name="Net burn" fill={GOLD} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </GlassCard>
              <GlassCard className="p-5 fade-up">
                <SectionLabel className="mb-4">Runway Scenarios</SectionLabel>
                <div className="space-y-3">
                  {data.scenarios.map((s) => (
                    <div key={s.name} className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3" data-testid={`scenario-${s.name}`}>
                      <div className="flex items-center justify-between"><span className="text-sm text-helm-fg">{s.name}</span><span className="font-mono text-helm-gold text-sm">{s.runway} months</span></div>
                      <p className="text-xs text-helm-muted mt-1">{s.desc}</p>
                      <Gauge
                        orientation="linear"
                        value={Math.min((Number(s.runway) || 0) / 36 * 100, 100)}
                        totalNotches={36}
                        spacing={0}
                        notchCornerRadius={2}
                        linearHeight={8}
                        minWidth={80}
                        activeFill={GOLD}
                        inactiveFill={CREAM}
                        inactiveFillOpacity={0.12}
                        className="mt-2"
                      />
                    </div>
                  ))}
                </div>
              </GlassCard>
            </div>
          )}

          <GlassCard className="p-5 fade-up">
            <SectionLabel className="mb-4">Ledger · {data.entries.length} entries</SectionLabel>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] font-mono uppercase tracking-wider text-helm-muted border-b border-helm-line">
                    <th className="py-2 pr-4 font-medium">Month</th><th className="py-2 pr-4 font-medium">Type</th>
                    <th className="py-2 pr-4 font-medium">Name</th><th className="py-2 pr-4 font-medium">Category</th>
                    <th className="py-2 pr-4 font-medium text-right">Amount</th>
                    <th className="py-2 pr-4 font-medium">Source</th><th className="py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {data.entries.map((e) => (
                    <tr key={e.id} className="border-b border-helm-fg/[0.03]" data-testid={`entry-${e.id}`}>
                      <td className="py-2.5 pr-4 font-mono text-helm-muted">
                        {e.month}
                        {(e.scheduled || false) && (
                          <span className="ml-1.5 text-[9px] font-mono uppercase tracking-wide text-helm-gold/80">Upcoming</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4"><span className={cn("text-[10px] font-mono uppercase tracking-wide rounded px-1.5 py-0.5", e.type === "revenue" ? "text-helm-fg bg-helm-status-positive/12" : "text-helm-status-negative bg-helm-status-negative/12")}>{e.type}</span></td>
                      <td className="py-2.5 pr-4 text-helm-fg">
                        {e.name || e.category}
                        {e.recurring && e.type === "revenue" && (
                          <span className="ml-1.5 text-[9px] text-helm-gold/70 font-mono">MRR</span>
                        )}
                        {e.recurring && e.type === "expense" && (
                          <span className="ml-1.5 text-[9px] text-helm-gold/70 font-mono">
                            {(e.recurrence || "monthly") === "annual" ? "Annual" : "Monthly"}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className="text-[10px] font-mono uppercase tracking-wide rounded px-1.5 py-0.5 text-helm-muted bg-helm-fg/5 border border-helm-line">
                          {e.category}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono text-helm-fg">{fmt(e.amount, sym)}</td>
                      <td className="py-2.5 pr-4">
                        {e.source === "ai_upload" && e.source_document_id ? (
                          <button
                            type="button"
                            data-testid={`entry-doc-${e.id}`}
                            onClick={() => openDocument(e.source_document_id)}
                            className="inline-flex items-center gap-1 text-[10px] font-mono text-helm-gold hover:text-helm-gold-hover transition-colors"
                            title="View original document"
                          >
                            <Sparkles className="w-3 h-3" /> AI upload
                          </button>
                        ) : (
                          <span className="text-[10px] font-mono text-helm-muted">{e.source}</span>
                        )}
                      </td>
                      <td className="py-2.5 text-right">{canWrite && <CirDeleteBtn onClick={() => del(e.id)} data-testid={`del-${e.id}`} title="Delete entry" />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setShowForm(false)} />
          <GlassCard className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="entry-form">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg text-helm-fg font-light">
                {form.source_document_id
                  ? "Confirm extracted entry"
                  : hasAccountingSync
                    ? "Add a one-off entry"
                    : "Log a financial entry"}
              </h3>
              <button onClick={() => setShowForm(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button>
            </div>
            {hasAccountingSync && !form.source_document_id && (
              <p className="mb-4 text-xs text-helm-muted leading-relaxed" data-testid="accounting-sync-note">
                Your financials sync from {accountingLabel}. Use this only for items that will not appear in synced books
                (for example a cash reimbursement).
              </p>
            )}
            {form.extract_confidence === "low" && (
              <div className="mb-4 flex items-start gap-2 rounded-lg border border-helm-status-warning/35 bg-helm-status-warning/12 px-3 py-2.5 text-sm text-helm-fg" data-testid="low-confidence-banner">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>Double-check this one. I wasn&apos;t fully sure.</span>
              </div>
            )}
            {form.source_document_id && (
              <p className="mb-4 text-xs text-helm-muted flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-helm-gold" />
                Pre-filled from your upload. Edit anything before saving.
              </p>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 flex gap-2">
                {["revenue", "expense"].map((t) => (
                  <button key={t} data-testid={`type-${t}`} onClick={() => setForm((f) => ({
                    ...f,
                    type: t,
                    category: t === "revenue" ? REV_CATS[0] : EXP_CATS[0],
                    recurring: t === "revenue" ? true : f.recurring,
                    recurrence: f.recurrence || "monthly",
                  }))}
                    className={cn("flex-1 rounded-md py-2 text-sm capitalize transition-colors border", form.type === t ? "bg-helm-gold/12 border-helm-gold/35 text-helm-fg" : "border-helm-line text-helm-muted hover:bg-helm-fg/5")}>{t}</button>
                ))}
              </div>
              <label className="col-span-2 text-xs text-helm-muted">Category
                <select data-testid="entry-category" value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40">
                  {(form.type === "revenue" ? REV_CATS : EXP_CATS).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="col-span-2 text-xs text-helm-muted">What was this for?
                <input
                  data-testid="entry-name"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. MongoDB Database Subscription"
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                />
              </label>
              <label className="text-xs text-helm-muted">Amount ({(data.currency || "usd").toUpperCase()})
                <input data-testid="entry-amount" type="number" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} placeholder="50000" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <label className="text-xs text-helm-muted">Month
                <input data-testid="entry-month" type="month" value={form.month} onChange={(e) => setForm((f) => ({ ...f, month: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              {form.type === "revenue" && (
                <label className="col-span-2 flex items-center gap-2 text-sm text-helm-fg mt-1">
                  <input data-testid="entry-recurring" type="checkbox" checked={form.recurring} onChange={(e) => setForm((f) => ({ ...f, recurring: e.target.checked }))} className="accent-helm-gold w-4 h-4" />
                  Recurring (counts toward MRR)
                </label>
              )}
              {form.type === "expense" && (
                <div className="col-span-2 space-y-2 mt-1">
                  <label className="flex items-center gap-2 text-sm text-helm-fg">
                    <input
                      data-testid="entry-recurring"
                      type="checkbox"
                      checked={form.recurring}
                      onChange={(e) => setForm((f) => ({
                        ...f,
                        recurring: e.target.checked,
                        recurrence: e.target.checked ? (f.recurrence || "monthly") : f.recurrence,
                      }))}
                      className="accent-helm-gold w-4 h-4"
                    />
                    Recurring expense
                  </label>
                  {form.recurring && (
                    <label className="block text-xs text-helm-muted">
                      Cadence
                      <select
                        data-testid="entry-recurrence"
                        value={form.recurrence || "monthly"}
                        onChange={(e) => setForm((f) => ({ ...f, recurrence: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                      >
                        <option value="monthly">Monthly</option>
                        <option value="annual">Annual</option>
                      </select>
                      <span className="block mt-1.5 text-[11px] text-helm-muted leading-relaxed">
                        {form.recurrence === "annual"
                          ? "Annual amount is spread across months (÷12) for burn and runway."
                          : "Counts every month from the start month onward for burn and runway."}
                      </span>
                    </label>
                  )}
                </div>
              )}
              <label className="col-span-2 text-xs text-helm-muted">Note (optional)
                <input data-testid="entry-note" value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
            </div>
            <button data-testid="submit-entry-btn" onClick={submitEntry} disabled={busy} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm transition-colors hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : "Save entry"}</button>
          </GlassCard>
        </div>
      )}

      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setShowSettings(false)} />
          <GlassCard className="relative w-full max-w-sm m-4 rounded-2xl p-6" data-testid="settings-form">
            <div className="flex items-center justify-between mb-5"><h3 className="text-lg text-helm-fg font-light">Cash & margin</h3><button onClick={() => setShowSettings(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button></div>
            <label className="text-xs text-helm-muted block">Cash in bank
              <input data-testid="settings-cash" type="number" value={cash} onChange={(e) => setCash(e.target.value)} placeholder="3100000" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
            </label>
            <label className="text-xs text-helm-muted block mt-3">Gross margin % (optional)
              <input data-testid="settings-gm" type="number" value={gm} onChange={(e) => setGm(e.target.value)} placeholder="74" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
            </label>
            <label className="text-xs text-helm-muted block mt-3">Currency
              <select
                data-testid="settings-currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
              >
                {CURRENCY_OPTIONS.map((c) => (
                  <option key={c.code} value={c.code}>{c.label}</option>
                ))}
              </select>
            </label>
            <button data-testid="save-settings-btn" onClick={saveSettings} disabled={busy} className="mt-5 w-full rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm transition-colors hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : "Save"}</button>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
