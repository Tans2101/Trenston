import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { toast } from "sonner";
import {
  AreaChart, Area, BarChart, Bar, Cell, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Plus, Wallet, X, PenLine, History, Upload, Sparkles, FileText, AlertTriangle, FileSpreadsheet, Sheet, ArrowRight, Plug, ChevronDown } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { PageHeader, GlassCard, SectionLabel, ErrorScreen, EmptyState, SkeletonKPIRow, SkeletonChart, SkeletonCardList, Delta } from "@/components/kit";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/context/ThemeContext";
import { cn } from "@/lib/utils";
import { formatAxisMoney } from "@/lib/formatAxisMoney";
import { thisMonthISO } from "@/lib/dates";
import { useWorkspaceTimezone } from "@/hooks/useWorkspaceTimezone";
import { useWorkspaceCurrency } from "@/hooks/useWorkspaceCurrency";
import { formatMoney } from "@/lib/money";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { REVENUE_CATEGORIES as REV_CATS, EXPENSE_CATEGORIES as EXP_CATS, defaultRevenueCategory } from "@/lib/financeCategories";
import palette from "@/design/palette.json";
import { ACCENT, ACCENT_SCALE } from "@/lib/accent";
import { dealHref, departmentItemHref, highlightRecord } from "@/lib/signalRoute";
import { confirmAction } from "@/components/ConfirmHost";

const GOLD = ACCENT;
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

const fmt = (n, sym) => formatMoney(n, sym);

function ChartTooltip({ active, payload, label, symbol }) {
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

// Runway under this many months surfaces a quiet prompt to decide what to do about it.
const RUNWAY_WARN_MONTHS = 6;

const emptyForm = (tz, revenueCategory = REV_CATS[0]) => ({
  type: "revenue", category: revenueCategory, name: "", amount: "", month: thisMonthISO(tz),
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

// Month key "2026-10" to "Oct 2026" for captions.
function monthLabel(iso) {
  const [y, m] = String(iso || "").split("-").map(Number);
  if (!y || !m) return "";
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

// Ledger amount shown in home currency, net of tax when the server provides it.
function entryDisplayAmount(e) {
  const gross = Number(e.amount) || 0;
  const net = e.amount_net != null ? Number(e.amount_net) : null;
  const home = e.amount_home != null ? Number(e.amount_home) : null;
  const netHome = e.amount_net_home != null ? Number(e.amount_net_home) : null;
  let display;
  if (netHome != null) display = Math.abs(netHome);
  else if (net != null && home != null && gross) display = Math.abs(home) * (Math.abs(net) / Math.abs(gross));
  else if (home != null) display = Math.abs(home);
  else if (net != null) display = Math.abs(net);
  else display = Math.abs(gross);
  return { display, showNetHint: net != null && Math.abs(net) !== Math.abs(gross) };
}

const PILL_TONE = {
  positive: "border-helm-status-positive/30 bg-helm-status-positive/10 text-helm-status-positive",
  warning: "border-helm-status-warning/30 bg-helm-status-warning/10 text-helm-status-warning",
  negative: "border-helm-status-negative/30 bg-helm-status-negative/10 text-helm-status-negative",
};
const METER_TONE = {
  positive: "bg-helm-status-positive",
  warning: "bg-helm-status-warning",
  negative: "bg-helm-status-negative",
};

function StatusPill({ tone, children }) {
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider", PILL_TONE[tone])}>
      {children}
    </span>
  );
}

function runwayStatus(noBurn, months) {
  if (noBurn) return { tone: "positive", label: "Profitable" };
  if (months == null || !Number.isFinite(months)) return null;
  if (months < RUNWAY_WARN_MONTHS) return { tone: "negative", label: "Low" };
  if (months < 12) return { tone: "warning", label: "Watch" };
  return { tone: "positive", label: "Healthy" };
}

// Runway against a 24-month scale, tinted by status.
function RunwayMeter({ months, tone }) {
  const pct = Math.max(0, Math.min(months / 24, 1)) * 100;
  return (
    <div className="mt-5" aria-hidden data-testid="runway-meter">
      <div className="relative h-1.5 overflow-hidden rounded-full bg-helm-fg/10">
        <div className={cn("absolute inset-y-0 left-0 rounded-full", METER_TONE[tone] || "bg-helm-gold")} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[10px] text-helm-muted">
        <span>0</span><span>6m</span><span>12m</span><span>18m</span><span>24m+</span>
      </div>
    </div>
  );
}

const KPI_LABEL = "font-mono text-[11px] uppercase tracking-[0.15em] text-helm-muted";

function AddDataButton({ onClick, testId, large }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "mt-3 inline-flex items-center gap-1.5 font-mono text-helm-gold hover:text-helm-gold-hover",
        large ? "text-xl" : "text-lg",
      )}
    >
      Add data <ArrowRight className="h-4 w-4" />
    </button>
  );
}

const SOURCE_LABELS = {
  manual: "Manual",
  csv_import: "CSV",
  csv: "CSV",
  ai_upload: "AI upload",
  deal: "Deal",
  procurement: "Procurement",
};

function sourceLabel(src) {
  const s = String(src || "");
  if (SOURCE_LABELS[s]) return SOURCE_LABELS[s];
  if (s.startsWith("qbo") || s.includes("quickbooks")) return "QuickBooks";
  if (s.startsWith("xero")) return "Xero";
  if (s.startsWith("sap")) return "SAP B1";
  return s ? s.replace(/_/g, " ") : "Manual";
}

const LEDGER_PAGE = 15;

export default function Financials() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data, loading, error, reload, isFetching } = useFetch("/financials");
  const { data: activityData, reload: reloadActs } = useFetch("/activities");
  const tz = useWorkspaceTimezone();
  const { currency: workspaceCurrency, symbol: workspaceSymbol } = useWorkspaceCurrency();
  const { data: company } = useCompanyQuery();
  const revCategory = defaultRevenueCategory(company?.industry);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(() => emptyForm(tz, revCategory));
  const [busy, setBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [cash, setCash] = useState("");
  const [gm, setGm] = useState("");
  const [reserve, setReserve] = useState("");
  const [currency, setCurrency] = useState("usd");
  const [csvPreview, setCsvPreview] = useState(null);
  const [csvBusy, setCsvBusy] = useState(false);
  const [sheetsBusy, setSheetsBusy] = useState(false);
  const [ledgerFilter, setLedgerFilter] = useState("all");
  // A deep link to one entry must not land on a row hidden behind "Show all".
  const [ledgerExpanded, setLedgerExpanded] = useState(() => (location.hash || "").startsWith("#entry-"));
  const { resolvedTheme } = useTheme();
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
        month: extracted.month || thisMonthISO(tz),
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
  }, [tz]);

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
        month: extracted.month || thisMonthISO(tz),
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
    if (!hash || loading || !data) return undefined;
    // #entry-<id> — scroll to and flash a ledger row (readable by everyone).
    if (hash.startsWith("entry-")) {
      // A just-booked row (e.g. from a won deal) may not be in the cached copy
      // yet — wait for the refetch before highlighting and clearing the hash.
      if (isFetching) return undefined;
      highlightRecord(decodeURIComponent(hash.slice("entry-".length)));
      navigate(location.pathname, { replace: true });
      return undefined;
    }
    if (!data.can_write) return undefined;
    if (hash === "log-mrr" || hash === "log-entry") {
      setForm(emptyForm(tz, revCategory));
      setShowForm(true);
      setShowSettings(false);
    } else if (hash === "cash" || hash === "reserve") {
      setReserve(data.min_cash_reserve != null ? String(data.min_cash_reserve) : "");
      setCash(data.cash_entered ? String(data.settings?.cash ?? 0) : "");
      setGm(data.settings?.gross_margin != null ? String(data.settings.gross_margin) : "");
      setCurrency(data.settings?.currency || data.currency || "usd");
      setShowSettings(true);
      setShowForm(false);
    } else {
      return undefined;
    }
    // Clear through the router (not history.replaceState) so location.hash
    // actually changes — otherwise every refetch re-opens the form.
    navigate(location.pathname, { replace: true });
    return undefined;
  }, [location.hash, location.pathname, loading, data, tz, navigate, isFetching, revCategory]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Financials" subtitle="Your finance team logs revenue and expenses here. Trenston turns it into live MRR, runway and burn across the whole cockpit." />
        <SkeletonKPIRow count={4} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
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
  const sym = data.currency_symbol || workspaceSymbol;

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
          const ok = await confirmAction({
            title: "This may be a duplicate",
            description: `A synced entry for about the same amount already exists in ${dup.month}`
              + `${dup.name ? ` (${dup.name})` : ""}. Manual duplicates can inflate MRR, burn, and cash.`,
            confirmLabel: "Save anyway",
          });
          if (!ok) return;
        }
      }
      await api.post("/financials/entries", payload);
      toast.success("Entry logged");
      setForm(emptyForm(tz, revCategory));
      setShowForm(false);
      reload();
      reloadActs();
    } catch (e) { toast.error(fetchErrorMessage(e, "Could not save")); }
    finally { setBusy(false); }
  };

  const del = async (id) => {
    if (!(await confirmAction({ title: "Remove this entry?", description: "This can't be undone.", confirmLabel: "Remove", destructive: true }))) return;
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
    const reserveRaw = String(reserve ?? "").trim();
    const reserveValue = reserveRaw === "" ? null : parseFloat(reserveRaw);
    if (reserveValue != null && (!Number.isFinite(reserveValue) || reserveValue < 0)) {
      toast.error("Enter a minimum cash reserve of zero or more");
      return;
    }
    const currentReserve = data.min_cash_reserve ?? null;
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
      if (reserveValue !== currentReserve) {
        await api.put("/financials/min-reserve", { value: reserveValue });
      }
      toast.success("Updated");
      setShowSettings(false);
      reload();
      reloadActs();
    } catch (e) { toast.error(fetchErrorMessage(e, "Could not save")); }
    finally { setBusy(false); }
  };

  const openSettings = () => {
    setReserve(data.min_cash_reserve != null ? String(data.min_cash_reserve) : "");
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
        const ok = await confirmAction({
          title: "Some rows may be duplicates",
          description: `${overlaps.length} CSV row${overlaps.length === 1 ? "" : "s"} look similar to entries already synced from ${accountingLabel}. Manual duplicates can inflate MRR, burn, and cash.`,
          confirmLabel: "Import anyway",
        });
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

  const expenseBreakdown = data.expense_breakdown || [];
  const scenarios = data.scenarios || [];
  const burnSeries = data.burn_series || [];
  // Future-dated entries come back separately (they don't count toward totals
  // yet). Show them at the top of the ledger, marked Upcoming, so they are not
  // invisible after saving.
  const postedEntries = data.entries || [];
  const postedIds = new Set(postedEntries.map((e) => e.id));
  const scheduledEntries = (data.scheduled_entries || [])
    .filter((e) => e && e.id && !postedIds.has(e.id))
    .map((e) => ({ ...e, scheduled: true }))
    .sort((a, b) => String(b.month || "").localeCompare(String(a.month || "")));
  const entries = [...scheduledEntries, ...postedEntries];
  const runwayMonths = data.runway_months != null ? Number(data.runway_months) : null;
  const runwayLow = runwayMonths != null && Number.isFinite(runwayMonths) && runwayMonths < RUNWAY_WARN_MONTHS;

  const openEntryForm = () => { setForm(emptyForm(tz, revCategory)); setShowForm(true); };

  // Average net burn over the last three ledger months, matching the server's runway basis.
  const recentBurn = burnSeries.slice(-3).map((b) => Math.max(Number(b.burn) || 0, 0));
  const avgBurn = recentBurn.length ? recentBurn.reduce((s, v) => s + v, 0) / recentBurn.length : null;
  const latestLabel = monthLabel(data.latest_month);
  const latestTotals = (data.ledger_months || []).slice(-1)[0] || null;
  const burnValue = data.burn_value != null ? Number(data.burn_value) : null;
  const netPositive = burnValue != null && burnValue < 0;
  const status = runwayStatus(data.runway_no_burn, runwayMonths);
  const cashMissing = data.cash_entered === false;
  const cashZero = data.cash_state === "zero_confirmed";
  const mrrMissing = data.mrr_known === false;
  const gmMissing = !data.gross_margin || data.gross_margin === "—";
  const currencyCode = (data.currency || workspaceCurrency).toUpperCase();

  const dark = resolvedTheme === "dark";
  const gridStroke = dark ? "rgba(244, 244, 244, 0.06)" : "rgba(10, 10, 10, 0.06)";
  const axisStroke = dark ? "rgba(244, 244, 244, 0.5)" : palette.slate;
  const expenseStroke = dark ? "rgba(244, 244, 244, 0.45)" : palette.slate;
  const cursorFill = dark ? "rgba(244, 244, 244, 0.04)" : "rgba(10, 10, 10, 0.04)";
  const swatches = dark ? ACCENT_SCALE.dark : ACCENT_SCALE.light;

  const filteredEntries = ledgerFilter === "all" ? entries : entries.filter((e) => e.type === ledgerFilter);
  const visibleEntries = ledgerExpanded ? filteredEntries : filteredEntries.slice(0, LEDGER_PAGE);
  const revenueCount = entries.filter((e) => e.type === "revenue").length;

  const importLabel = uploadBusy ? "Reading bill…" : csvBusy ? "Reading CSV…" : "Import";
  const menuItemClass = "cursor-pointer items-start gap-3 rounded-sm px-2.5 py-2.5 text-sm text-helm-fg focus:bg-helm-fg/5 focus:text-helm-fg";

  const actions = canWrite ? (
    <div className="flex flex-wrap items-center gap-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            data-testid="import-menu-btn"
            disabled={uploadBusy || csvBusy}
            className="inline-flex items-center gap-1.5 rounded-md border border-helm-line px-3 py-2 text-sm font-medium text-helm-fg transition-colors hover:bg-helm-fg/5 disabled:opacity-60"
          >
            <Upload className="h-4 w-4" /> {importLabel} <ChevronDown className="h-3.5 w-3.5 text-helm-muted" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={6} className="w-72 rounded-md border border-helm-line bg-helm-card p-1 text-helm-fg shadow-xl">
          <DropdownMenuItem data-testid="upload-bill-btn" className={menuItemClass} onSelect={() => fileInputRef.current?.click()}>
            <Upload className="mt-0.5 h-4 w-4 text-helm-muted" />
            <span>
              <span className="block">{hasAccountingSync ? "Upload a one-off bill" : "Upload a bill"}</span>
              <span className="block text-xs text-helm-muted">PDF, PNG or JPEG up to 15MB. Read and pre-filled for you to confirm.</span>
            </span>
          </DropdownMenuItem>
          <DropdownMenuItem data-testid="import-drive-btn" className={menuItemClass} onSelect={importFromDrive}>
            <FileText className="mt-0.5 h-4 w-4 text-helm-muted" />
            <span>
              <span className="block">From Google Drive</span>
              <span className="block text-xs text-helm-muted">Pick a bill or invoice stored in Drive.</span>
            </span>
          </DropdownMenuItem>
          <DropdownMenuItem data-testid="import-csv-btn" className={menuItemClass} onSelect={() => csvInputRef.current?.click()}>
            <FileSpreadsheet className="mt-0.5 h-4 w-4 text-helm-muted" />
            <span>
              <span className="block">{hasAccountingSync ? "Import one-off CSV" : "Import CSV"}</span>
              <span className="block text-xs text-helm-muted">Preview every row before anything is saved.</span>
            </span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <button
        type="button"
        data-testid="add-entry-btn"
        onClick={openEntryForm}
        className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold px-3.5 py-2 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold-hover"
      >
        <Plus className="h-4 w-4" /> {hasAccountingSync ? "Add one-off entry" : "Log entry"}
      </button>
    </div>
  ) : null;

  const onPageDragOver = (e) => {
    if (!canWrite || !Array.from(e.dataTransfer?.types || []).includes("Files")) return;
    e.preventDefault();
    setDragOver(true);
  };
  const onPageDragLeave = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false);
  };
  const onPageDrop = (e) => {
    if (!canWrite) return;
    onDrop(e);
  };

  return (
    <div
      data-testid="bill-dropzone"
      onDragOver={onPageDragOver}
      onDragLeave={onPageDragLeave}
      onDrop={onPageDrop}
      className="relative"
    >
      <PageHeader
        title="Financials"
        subtitle={
          hasAccountingSync
            ? `Synced from ${accountingLabel}. Add entries here only for items that will not appear in your books.`
            : "Log revenue and expenses, or connect your accounting system under Integrations. Trenston turns them into MRR, burn and runway."
        }
        action={actions}
      />

      {canWrite && (
        <>
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
        </>
      )}

      {dragOver && canWrite && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-helm-ink/60 p-6" data-testid="bill-drop-overlay">
          <div className="rounded-xl border border-dashed border-helm-gold/50 bg-helm-card px-10 py-8 text-center shadow-xl">
            <Upload className="mx-auto h-6 w-6 text-helm-gold" />
            <p className="mt-3 text-sm text-helm-fg">Drop a bill to read it</p>
            <p className="mt-1 text-xs text-helm-muted">PDF, PNG or JPEG up to 15MB. You confirm before it is saved.</p>
          </div>
        </div>
      )}

      {uploadBusy && (
        <GlassCard className="mb-6 flex items-center gap-3 px-4 py-3 fade-up" data-testid="bill-reading">
          <Sparkles className="h-4 w-4 text-helm-gold" />
          <p className="text-sm text-helm-fg">Reading your bill. This can take up to a minute.</p>
        </GlassCard>
      )}

      {csvPreview && (
        <GlassCard className="p-5 mb-6 fade-up" data-testid="csv-import-preview">
          {hasAccountingSync && (
            <p className="mb-3 text-xs text-helm-muted leading-relaxed" data-testid="csv-accounting-sync-note">
              Your financials sync from {accountingLabel}. Import only rows that are not already in synced books.
            </p>
          )}
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <SectionLabel>CSV import preview</SectionLabel>
              <p className="text-sm text-helm-muted mt-1">
                {csvPreview.valid_count} ready · {csvPreview.skipped_count} skipped
                {csvPreview.filename ? ` · ${csvPreview.filename}` : ""}. Nothing is saved until you confirm.
              </p>
            </div>
            <button type="button" aria-label="Close preview" onClick={() => setCsvPreview(null)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button>
          </div>
          {csvPreview.valid?.length > 0 && (
            <div className="overflow-x-auto mb-4 max-h-56 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] font-mono uppercase tracking-wider text-helm-muted border-b border-helm-line">
                    <th className="py-2 pr-3 font-medium">Month</th><th className="py-2 pr-3 font-medium">Type</th>
                    <th className="py-2 pr-3 font-medium">Name</th><th className="py-2 pr-3 font-medium">Category</th>
                    <th className="py-2 pr-3 font-medium text-right">Amount</th>
                    <th className="py-2 font-medium">Note</th>
                  </tr>
                </thead>
                <tbody>
                  {csvPreview.valid.slice(0, 50).map((r, i) => (
                    <tr key={i} className="border-b border-helm-line/60" data-testid={`csv-valid-${i}`}>
                      <td className="py-2 pr-3 font-mono text-helm-muted">{r.month}</td>
                      <td className="py-2 pr-3 text-helm-fg capitalize">{r.type}</td>
                      <td className="py-2 pr-3 text-helm-fg">{r.name || r.category}</td>
                      <td className="py-2 pr-3 text-helm-muted">{r.category}</td>
                      <td className="py-2 pr-3 text-right font-mono text-helm-fg tabular-nums">{fmt(r.amount, sym)}</td>
                      <td className="py-2 text-helm-muted truncate max-w-[140px]">{r.note || ""}</td>
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

      {!data.has_data ? (
        <>
          <EmptyState icon={Wallet} title="No financials logged yet"
            body={
              hasAccountingSync
                ? `Connect and sync ${accountingLabel} under Integrations, or add a one-off entry for anything sync will not include.`
                : "Log your revenue and expenses and Trenston computes MRR, ARR, runway and burn automatically. You can also drop a bill anywhere on this page."
            }
            action={canWrite ? (
              <div className="flex flex-wrap items-center justify-center gap-2">
                <button data-testid="empty-upload-bill-btn" onClick={() => fileInputRef.current?.click()} disabled={uploadBusy}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg font-medium text-sm px-4 py-2 hover:bg-helm-fg/5 disabled:opacity-60">
                  <Upload className="w-4 h-4" /> {hasAccountingSync ? "Upload one-off bill" : "Upload a bill"}
                </button>
                <button data-testid="empty-add-entry-btn" onClick={openEntryForm}
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
          {!hasAccountingSync && data.can_manage && (
            <p className="-mt-6 mb-10 text-center text-xs text-helm-muted" data-testid="empty-connect-accounting">
              <button type="button" onClick={() => navigate("/app/integrations")} className="inline-flex items-center gap-1 hover:text-helm-fg">
                <Plug className="w-3 h-3" /> Or connect QuickBooks, Xero, or SAP Business One to sync automatically
              </button>
            </p>
          )}
        </>
      ) : (
        <>
          {/* Where you stand: cash, runway, and this month's result */}
          <section className="mb-10 fade-up" aria-labelledby="fin-position-heading">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
              <SectionLabel><span id="fin-position-heading">Where you stand</span></SectionLabel>
              <p className="text-[11px] text-helm-muted" data-testid="fin-totals-basis">
                Figures net of tax, in {currencyCode}
                {data.scheduled_count > 0 && (
                  <> · {data.scheduled_count} future-dated entr{data.scheduled_count === 1 ? "y" : "ies"} not counted until their month</>
                )}
              </p>
            </div>

            <GlassCard className="grid grid-cols-1 divide-y divide-helm-line md:grid-cols-3 md:divide-x md:divide-y-0">
              <div className="p-6" data-testid="fin-Cash">
                <div className="flex items-center justify-between gap-2">
                  <p className={KPI_LABEL}>Cash in bank</p>
                  {canWrite && (
                    <button
                      type="button"
                      data-testid="edit-settings-btn"
                      onClick={openSettings}
                      className="inline-flex items-center gap-1 text-xs text-helm-muted hover:text-helm-fg"
                    >
                      <PenLine className="h-3.5 w-3.5" /> Edit
                    </button>
                  )}
                </div>
                {cashMissing ? (
                  canWrite ? <AddDataButton large onClick={openSettings} testId="fin-Cash-add" /> : <p className="mt-3 font-mono text-xl text-helm-muted">Not set</p>
                ) : (
                  <p className="mt-3 font-mono text-3xl text-helm-fg tabular-nums md:text-4xl">{data.cash}</p>
                )}
                <p className="mt-3 text-xs leading-relaxed text-helm-muted">
                  {cashMissing
                    ? "Add your bank balance to calculate runway."
                    : cashZero
                      ? `Set to ${sym}0. Update it so runway reflects your real balance.`
                      : data.min_cash_reserve != null
                        ? `Entered manually. Reserve floor ${fmt(data.min_cash_reserve, sym)}.`
                        : "Entered manually. Update it whenever your balance moves."}
                </p>
              </div>

              <div className="p-6" data-testid="fin-Runway">
                <div className="flex items-center justify-between gap-2">
                  <p className={KPI_LABEL}>Runway</p>
                  {status && <StatusPill tone={status.tone}>{status.label}</StatusPill>}
                </div>
                {runwayMonths != null ? (
                  <p className="mt-3 font-mono text-3xl text-helm-fg tabular-nums md:text-4xl">
                    {runwayMonths} <span className="text-lg text-helm-muted">month{runwayMonths === 1 ? "" : "s"}</span>
                  </p>
                ) : data.runway_no_burn ? (
                  <p className="mt-3 font-mono text-3xl text-helm-fg md:text-4xl">No burn</p>
                ) : canWrite ? (
                  <AddDataButton large onClick={cashMissing ? openSettings : openEntryForm} testId="fin-Runway-add" />
                ) : (
                  <p className="mt-3 font-mono text-xl text-helm-muted">Not enough data</p>
                )}
                {runwayMonths != null && <RunwayMeter months={runwayMonths} tone={status?.tone} />}
                <p className="mt-3 text-xs leading-relaxed text-helm-muted">
                  {data.runway_no_burn
                    ? "Revenue covers expenses over the last 3 months."
                    : cashZero && runwayMonths != null
                      ? "Shows 0 because cash in bank is set to zero."
                      : runwayMonths != null && avgBurn
                      ? `Cash divided by ${fmt(avgBurn, sym)} a month, the average net burn over the last 3 months.`
                      : cashMissing
                        ? "Needs cash in bank and at least one month of entries."
                        : "Appears once expenses outpace revenue."}
                </p>
              </div>

              <div className="p-6" data-testid="fin-Net Burn">
                <div className="flex items-center justify-between gap-2">
                  <p className={KPI_LABEL}>{netPositive ? "Net income" : "Net burn"}</p>
                  {latestLabel && <span className="font-mono text-[11px] text-helm-muted">{latestLabel}</span>}
                </div>
                {data.burn_known === false ? (
                  canWrite ? <AddDataButton large onClick={openEntryForm} testId="fin-Net Burn-add" /> : <p className="mt-3 font-mono text-xl text-helm-muted">Not set</p>
                ) : (
                  <p className={cn("mt-3 font-mono text-3xl tabular-nums md:text-4xl", netPositive ? "text-helm-status-positive" : "text-helm-fg")}>
                    {netPositive ? `+${fmt(Math.abs(burnValue), sym)}` : data.burn}
                  </p>
                )}
                {latestTotals && (
                  <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-helm-line pt-3 text-xs">
                    <div>
                      <dt className="text-helm-muted">Revenue</dt>
                      <dd className="mt-0.5 font-mono text-sm text-helm-fg tabular-nums">{fmt(latestTotals.revenue, sym)}</dd>
                    </div>
                    <div>
                      <dt className="text-helm-muted">Expenses</dt>
                      <dd className="mt-0.5 font-mono text-sm text-helm-fg tabular-nums">{fmt(latestTotals.expenses, sym)}</dd>
                    </div>
                  </dl>
                )}
              </div>
            </GlassCard>

            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <GlassCard className="p-5" data-testid="fin-MRR">
                <div className="flex items-center justify-between gap-2">
                  <p className={KPI_LABEL}>MRR</p>
                  {!mrrMissing && <Delta value={data.mrr_delta} />}
                </div>
                {mrrMissing ? (
                  canWrite ? <AddDataButton onClick={openEntryForm} testId="fin-MRR-add" /> : <p className="mt-3 font-mono text-lg text-helm-muted">Not set</p>
                ) : (
                  <p className="mt-3 font-mono text-2xl text-helm-fg tabular-nums">{data.mrr}</p>
                )}
                <p className="mt-2 text-xs text-helm-muted">
                  {mrrMissing ? "Mark revenue as recurring to track it." : "Recurring revenue this month."}
                </p>
              </GlassCard>
              <GlassCard className="p-5" data-testid="fin-ARR">
                <p className={KPI_LABEL}>ARR</p>
                {mrrMissing ? (
                  canWrite ? <AddDataButton onClick={openEntryForm} testId="fin-ARR-add" /> : <p className="mt-3 font-mono text-lg text-helm-muted">Not set</p>
                ) : (
                  <p className="mt-3 font-mono text-2xl text-helm-fg tabular-nums">{data.arr}</p>
                )}
                <p className="mt-2 text-xs text-helm-muted">MRR × 12, annualised.</p>
              </GlassCard>
              <GlassCard className="p-5" data-testid="fin-Gross Margin">
                <p className={KPI_LABEL}>Gross margin</p>
                {gmMissing ? (
                  canWrite ? <AddDataButton onClick={openSettings} testId="fin-Gross Margin-add" /> : <p className="mt-3 font-mono text-lg text-helm-muted">Not set</p>
                ) : (
                  <p className="mt-3 font-mono text-2xl text-helm-fg tabular-nums">{data.gross_margin}</p>
                )}
                <p className="mt-2 text-xs text-helm-muted">Set by you in cash and margin settings.</p>
              </GlassCard>
            </div>
          </section>

          {runwayLow && (
            <GlassCard className="mb-10 border-helm-status-warning/35 p-4 fade-up" data-testid="runway-warning">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 items-start gap-2.5">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-helm-status-warning" />
                  <p className="text-sm text-helm-fg">
                    {cashZero
                      ? "Runway shows 0 months because cash in bank is set to zero."
                      : `Runway is ${runwayMonths} month${runwayMonths === 1 ? "" : "s"} at current net burn.`}
                    <span className="text-helm-muted">
                      {cashZero ? " Update your balance if that is not right." : " Worth a deliberate call on spend or revenue."}
                    </span>
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {cashZero && canWrite ? (
                    <button
                      type="button"
                      data-testid="runway-update-cash-btn"
                      onClick={openSettings}
                      className="inline-flex items-center gap-1.5 rounded-md border border-helm-line px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-fg/5"
                    >
                      <PenLine className="h-3.5 w-3.5" /> Update cash
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        data-testid="runway-ask-btn"
                        onClick={() => navigate("/app/ask", {
                          state: {
                            prefill: `Our runway is ${runwayMonths} months at ${data.burn} net burn with ${data.cash} cash. What are the most realistic ways to extend it, based on our current expenses and revenue?`,
                          },
                        })}
                        className="inline-flex items-center gap-1.5 rounded-md border border-helm-line px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-fg/5"
                      >
                        <Sparkles className="h-3.5 w-3.5 text-helm-gold" /> Ask Trenston
                      </button>
                      <button
                        type="button"
                        data-testid="runway-decision-btn"
                        onClick={() => navigate("/app/decisions", {
                          state: {
                            openAdd: true,
                            prefill: {
                              title: `Extend runway beyond ${runwayMonths} month${runwayMonths === 1 ? "" : "s"}`,
                              description: `Runway is ${runwayMonths} month${runwayMonths === 1 ? "" : "s"} at ${data.burn} net burn with ${data.cash} cash in bank. Decide what to change on spend or revenue.`,
                              category: "Finance",
                            },
                          },
                        })}
                        className="inline-flex items-center gap-1.5 rounded-md border border-helm-status-warning/35 bg-helm-status-warning/12 px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-status-warning/20"
                      >
                        Log a decision <ArrowRight className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </GlassCard>
          )}

          {/* Trends */}
          <section className="mb-10 fade-up" aria-label="Trends">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <GlassCard className="p-6 lg:col-span-2">
                <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <SectionLabel>Revenue vs expenses</SectionLabel>
                    <p className="mt-1 text-xs text-helm-muted">Monthly totals, last {data.revenue_series?.length || 0} months with entries.</p>
                  </div>
                  <div className="flex items-center gap-4 font-mono text-[11px] text-helm-muted" data-testid="revenue-expenses-legend">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="inline-block h-0.5 w-4 rounded-full" style={{ background: GOLD }} />
                      Revenue
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: expenseStroke }} />
                      Expenses
                    </span>
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={data.revenue_series} margin={{ left: -8, right: 8, top: 8 }}>
                    <CartesianGrid stroke={gridStroke} vertical={false} />
                    <XAxis dataKey="month" stroke={axisStroke} fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke={axisStroke} fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => formatAxisMoney(v, { symbol: sym })} width={52} />
                    <Tooltip content={<ChartTooltip symbol={sym} />} />
                    <Area type="monotone" dataKey="revenue" name="Revenue" stroke={GOLD} strokeWidth={2} fill={GOLD} fillOpacity={0.08} />
                    <Area type="monotone" dataKey="expenses" name="Expenses" stroke={expenseStroke} strokeWidth={1.5} fill="none" strokeDasharray="4 4" />
                  </AreaChart>
                </ResponsiveContainer>
              </GlassCard>

              <GlassCard className="flex flex-col p-6" data-testid="expense-mix">
                <SectionLabel>Where money goes</SectionLabel>
                <p className="mt-1 text-xs text-helm-muted">Share of expenses by category.</p>
                {expenseBreakdown.length > 0 ? (
                  <ul className="mt-5 space-y-4">
                    {expenseBreakdown.slice(0, 6).map((e, i) => (
                      <li key={e.name} data-testid={`expense-mix-${e.name}`}>
                        <div className="flex items-baseline justify-between gap-3 text-sm">
                          <span className="truncate text-helm-fg">{e.name}</span>
                          <span className="shrink-0 font-mono text-xs text-helm-muted tabular-nums">{e.value}%</span>
                        </div>
                        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-helm-fg/10">
                          <div className="h-full rounded-full" style={{ width: `${Math.max(e.value, 2)}%`, background: swatches[Math.min(i, swatches.length - 1)] }} />
                        </div>
                      </li>
                    ))}
                    {expenseBreakdown.length > 6 && (
                      <li className="text-xs text-helm-muted">+{expenseBreakdown.length - 6} smaller categories</li>
                    )}
                  </ul>
                ) : (
                  <p className="flex flex-1 items-center justify-center py-10 text-center text-sm text-helm-muted">Log expenses to see where money goes.</p>
                )}
              </GlassCard>
            </div>

            {burnSeries.length > 0 && (
              <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
                <GlassCard className="p-6 lg:col-span-2">
                  <SectionLabel>Monthly net burn</SectionLabel>
                  <p className="mt-1 mb-5 text-xs text-helm-muted">Expenses minus revenue. Bars below zero are months you made money.</p>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={burnSeries} margin={{ left: -8, right: 8 }}>
                      <CartesianGrid stroke={gridStroke} vertical={false} />
                      <XAxis dataKey="month" stroke={axisStroke} fontSize={11} tickLine={false} axisLine={false} />
                      <YAxis stroke={axisStroke} fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => formatAxisMoney(v, { symbol: sym })} width={52} />
                      <Tooltip content={<ChartTooltip symbol={sym} />} cursor={{ fill: cursorFill }} />
                      <ReferenceLine y={0} stroke={axisStroke} strokeOpacity={0.4} />
                      <Bar dataKey="burn" name="Net burn" radius={[3, 3, 3, 3]} maxBarSize={44}>
                        {burnSeries.map((b) => (
                          <Cell key={b.month} fill={Number(b.burn) > 0 ? GOLD : palette.statusPositive} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </GlassCard>
                {data.modeling_allowed ? (
                  <GlassCard className="flex flex-col p-6" data-testid="modeling-link-card">
                    <SectionLabel>Runway scenarios</SectionLabel>
                    <p className="mt-2 flex-1 text-sm leading-relaxed text-helm-muted">
                      Test hires, revenue growth and a funding round against these numbers, then save and compare scenarios.
                    </p>
                    <Link
                      to="/app/modeling"
                      className="mt-5 inline-flex items-center gap-1.5 self-start rounded-md bg-helm-gold px-3.5 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover"
                    >
                      Open Financial Modeling <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </GlassCard>
                ) : (
                  <GlassCard className="p-6">
                    <SectionLabel>Runway scenarios</SectionLabel>
                    <p className="mt-1 mb-4 text-xs text-helm-muted">Simple multiples of your current burn.</p>
                    {scenarios.length === 0 && (
                      <div className="py-6 text-center" data-testid="scenarios-empty">
                        {data.runway_no_burn ? (
                          <p className="text-sm text-helm-muted">Revenue covers expenses on average, so there is no runway to model.</p>
                        ) : !data.cash_entered ? (
                          <>
                            <p className="text-sm text-helm-muted">Add cash in bank to model runway at current, trimmed and scaled burn.</p>
                            {canWrite && (
                              <button type="button" onClick={openSettings} className="mt-2 inline-flex items-center gap-1 text-xs text-helm-gold hover:text-helm-gold-hover">
                                Add cash in bank <ArrowRight className="h-3 w-3" />
                              </button>
                            )}
                          </>
                        ) : (
                          <p className="text-sm text-helm-muted">Scenarios appear once expenses outpace revenue.</p>
                        )}
                      </div>
                    )}
                    <div className="space-y-4">
                      {scenarios.map((s) => (
                        <div key={s.name} data-testid={`scenario-${s.name}`}>
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="text-sm text-helm-fg">{s.name}</span>
                            <span className="font-mono text-sm text-helm-fg tabular-nums">{s.runway} mo</span>
                          </div>
                          <p className="mt-0.5 text-xs text-helm-muted">{s.desc}</p>
                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-helm-fg/10">
                            <div className="h-full rounded-full bg-helm-gold" style={{ width: `${Math.min((Number(s.runway) || 0) / 36 * 100, 100)}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                    {scenarios.length > 0 && (
                      <p className="mt-4 text-xs text-helm-muted">
                        Detailed scenarios are in <Link to="/app/modeling" className="text-helm-gold hover:text-helm-gold-hover">Financial Modeling</Link> on Growth and Business.
                      </p>
                    )}
                  </GlassCard>
                )}
              </div>
            )}
          </section>

          {/* Ledger */}
          <GlassCard className="mb-10 fade-up" data-testid="ledger">
            <div className="flex flex-col gap-3 border-b border-helm-line px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <SectionLabel>Ledger</SectionLabel>
                <p className="mt-0.5 text-xs text-helm-muted">
                  {entries.length} entr{entries.length === 1 ? "y" : "ies"} · {revenueCount} revenue · {entries.length - revenueCount} expense{entries.length - revenueCount === 1 ? "" : "s"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex rounded-md border border-helm-line p-0.5" role="tablist" aria-label="Filter ledger">
                  {[["all", "All"], ["revenue", "Revenue"], ["expense", "Expenses"]].map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      role="tab"
                      aria-selected={ledgerFilter === key}
                      data-testid={`ledger-filter-${key}`}
                      onClick={() => setLedgerFilter(key)}
                      className={cn(
                        "rounded px-2.5 py-1 text-xs transition-colors",
                        ledgerFilter === key ? "bg-helm-fg/10 text-helm-fg" : "text-helm-muted hover:text-helm-fg",
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {canWrite && (
                  <button
                    type="button"
                    data-testid="export-sheets-btn"
                    disabled={sheetsBusy || !data.has_data}
                    onClick={exportToSheets}
                    className="inline-flex items-center gap-1.5 rounded-md border border-helm-line px-2.5 py-1.5 text-xs text-helm-muted transition-colors hover:bg-helm-fg/5 hover:text-helm-fg disabled:opacity-60"
                  >
                    <Sheet className="h-3.5 w-3.5" /> {sheetsBusy ? "Creating Sheet…" : "Export to Sheets"}
                  </button>
                )}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left font-mono text-[10px] uppercase tracking-wider text-helm-muted">
                    <th className="py-3 pl-6 pr-4 font-medium">Month</th>
                    <th className="py-3 pr-4 font-medium">Item</th>
                    <th className="hidden py-3 pr-4 font-medium md:table-cell">Category</th>
                    <th className="hidden py-3 pr-4 font-medium sm:table-cell">Source</th>
                    <th className="py-3 pr-4 text-right font-medium">Amount</th>
                    <th className="py-3 pr-6"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {visibleEntries.map((e) => {
                    const { display, showNetHint } = entryDisplayAmount(e);
                    const isRevenue = e.type === "revenue";
                    const cadence = e.recurring
                      ? (isRevenue ? "Recurring" : ((e.recurrence || "monthly") === "annual" ? "Annual" : "Monthly"))
                      : "One-off";
                    return (
                      <tr
                        key={e.id}
                        className={cn("border-t border-helm-line/70 transition-colors hover:bg-helm-fg/[0.02]", e.scheduled && "opacity-75")}
                        data-testid={`entry-${e.id}`}
                        data-deeplink={e.id}
                      >
                        <td className="whitespace-nowrap py-3.5 pl-6 pr-4 align-top font-mono text-xs text-helm-muted">
                          {e.month}
                          {e.scheduled && (
                            <span className="mt-1 block font-mono text-[9px] uppercase tracking-wide text-helm-gold">Upcoming</span>
                          )}
                        </td>
                        <td className="py-3.5 pr-4 align-top">
                          <div className="flex items-start gap-2.5">
                            <span
                              className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", isRevenue ? "bg-helm-status-positive" : "bg-helm-muted")}
                              aria-hidden
                            />
                            <div className="min-w-0">
                              <p className="truncate text-helm-fg">{e.name || e.category}</p>
                              <p className="mt-0.5 text-xs text-helm-muted">
                                {isRevenue ? "Revenue" : "Expense"} · {cadence}
                                {isRevenue && e.recurring ? " · counts to MRR" : ""}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="hidden py-3.5 pr-4 align-top text-xs text-helm-muted md:table-cell">{e.category}</td>
                        <td className="hidden py-3.5 pr-4 align-top sm:table-cell">
                          {e.source === "ai_upload" && e.source_document_id ? (
                            <button
                              type="button"
                              data-testid={`entry-doc-${e.id}`}
                              onClick={() => openDocument(e.source_document_id)}
                              className="inline-flex items-center gap-1 text-xs text-helm-gold transition-colors hover:text-helm-gold-hover"
                              title="View original document"
                            >
                              <Sparkles className="h-3 w-3" /> AI upload
                            </button>
                          ) : e.source === "deal" && e.source_deal_id ? (
                            <Link
                              to={dealHref(e.source_deal_id)}
                              data-testid={`entry-deal-${e.id}`}
                              className="inline-flex items-center gap-1 text-xs text-helm-gold transition-colors hover:text-helm-gold-hover"
                              title="Open the won deal behind this entry"
                            >
                              Deal <ArrowRight className="h-3 w-3" />
                            </Link>
                          ) : e.source === "procurement" && e.source_procurement_request_id ? (
                            <Link
                              to={departmentItemHref("procurement", e.source_procurement_request_id)}
                              data-testid={`entry-procurement-${e.id}`}
                              className="inline-flex items-center gap-1 text-xs text-helm-gold transition-colors hover:text-helm-gold-hover"
                              title="Open the procurement request behind this entry"
                            >
                              Procurement <ArrowRight className="h-3 w-3" />
                            </Link>
                          ) : (
                            <span className="text-xs text-helm-muted">{sourceLabel(e.source)}</span>
                          )}
                        </td>
                        <td className="whitespace-nowrap py-3.5 pr-4 text-right align-top">
                          <span className={cn("font-mono tabular-nums", isRevenue ? "text-helm-status-positive" : "text-helm-fg")}>
                            {isRevenue ? "+" : "−"}{fmt(display, sym)}
                          </span>
                          {showNetHint && <span className="block text-[10px] text-helm-muted">net of tax</span>}
                        </td>
                        <td className="py-3 pr-6 text-right align-top">
                          {canWrite && <CirDeleteBtn onClick={() => del(e.id)} data-testid={`del-${e.id}`} title="Delete entry" />}
                        </td>
                      </tr>
                    );
                  })}
                  {visibleEntries.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-10 text-center text-sm text-helm-muted">
                        No {ledgerFilter === "revenue" ? "revenue" : "expense"} entries yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {filteredEntries.length > LEDGER_PAGE && (
              <div className="border-t border-helm-line px-6 py-3">
                <button
                  type="button"
                  data-testid="ledger-toggle-all"
                  onClick={() => setLedgerExpanded((v) => !v)}
                  className="text-xs text-helm-muted hover:text-helm-fg"
                >
                  {ledgerExpanded ? "Show fewer" : `Show all ${filteredEntries.length} entries`}
                </button>
              </div>
            )}
          </GlassCard>

          {finActs.length > 0 && (
            <GlassCard className="mb-6 p-6 fade-up" data-testid="financials-activity">
              <div className="mb-4 flex items-center gap-2">
                <History className="h-4 w-4 text-helm-muted" />
                <SectionLabel>Recent activity</SectionLabel>
              </div>
              <ul className="divide-y divide-helm-line/70">
                {finActs.map((a) => (
                  <li key={a.activity_id} className="flex items-center gap-3 py-2.5 text-sm" data-testid={`fin-activity-${a.activity_id}`}>
                    <span className="flex-1 truncate text-helm-fg">{a.summary}</span>
                    <span className="hidden shrink-0 text-xs text-helm-muted sm:inline">{a.actor_name} · {a.ago}</span>
                  </li>
                ))}
              </ul>
            </GlassCard>
          )}
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
                    category: t === "revenue" ? revCategory : EXP_CATS[0],
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
            <div className="flex items-center justify-between mb-5"><h3 className="text-lg text-helm-fg font-light">Cash, reserve & margin</h3><button onClick={() => setShowSettings(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button></div>
            <label className="text-xs text-helm-muted block">Cash in bank
              <input data-testid="settings-cash" type="number" value={cash} onChange={(e) => setCash(e.target.value)} placeholder="3100000" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
            </label>
            <label className="text-xs text-helm-muted block mt-3">Minimum cash reserve (optional)
              <input data-testid="settings-reserve" type="number" min="0" value={reserve} onChange={(e) => setReserve(e.target.value)} placeholder="Cash you never want to go below" className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              <span className="mt-1 block text-[11px] leading-relaxed">Trenston warns you before cash is projected to fall below this. Leave blank to turn those warnings off.</span>
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
