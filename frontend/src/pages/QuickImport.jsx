import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Check, ChevronDown, FileSpreadsheet, Info, Loader2, Undo2, UploadCloud,
} from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCompanyQuery, useInvalidateCompany } from "@/hooks/useCompanyQuery";
import { useFetch } from "@/hooks/useFetch";
import { invalidateFetchQueries } from "@/lib/fetchInvalidation";
import { confirmAction } from "@/components/ConfirmHost";
import { PageHeader, GlassCard } from "@/components/kit";
import NoAccess from "@/components/NoAccess";
import { cn } from "@/lib/utils";
import { currencySymbol, formatMoney } from "@/lib/money";
import {
  ACCEPTED_FILES, MAX_FILE_BYTES, KIND_DESTINATION, COUNT_TO_KIND,
  buildConfirmPayload, countsSentence, fieldLabel, initialChoices, monthName,
  recordsLabel, sampleColumns, sheetRecords, totalSelected,
} from "@/lib/quickImport";

const GOLD_BTN =
  "inline-flex items-center justify-center gap-2 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover transition-colors disabled:opacity-60";
const LINE_BTN =
  "inline-flex items-center justify-center gap-2 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/[0.04] transition-colors disabled:opacity-60";

const EXAMPLES = [
  { title: "Monthly P&L or budget", body: "Line items down the side, months across the top." },
  { title: "Clients or sales list", body: "Names, deal values and where each one stands." },
  { title: "Operations lists", body: "Job orders, supplier orders or a to-do list." },
];

function Notice({ children, tone = "info" }) {
  return (
    <p
      className={cn(
        "flex gap-2 rounded-md border px-3 py-2 text-xs leading-relaxed",
        tone === "warn"
          ? "border-helm-status-warning/35 bg-helm-status-warning/10 text-helm-fg"
          : "border-helm-line bg-helm-fg/[0.03] text-helm-muted",
      )}
    >
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

function SummaryLine({ sheet, money }) {
  const s = sheet.summary || {};
  if (sheet.kind === "financial" || sheet.kind === "financial_wide") {
    const range = s.first_month
      ? (s.first_month === s.last_month ? monthName(s.first_month) : `${monthName(s.first_month)} to ${monthName(s.last_month)}`)
      : "";
    return (
      <p className="text-sm text-helm-muted">
        Revenue {money(s.revenue || 0)} · Expenses {money(s.expenses || 0)}{range ? ` · ${range}` : ""}
      </p>
    );
  }
  if (sheet.kind === "deals") {
    return (
      <p className="text-sm text-helm-muted">
        Open pipeline {money(s.open_value || 0)}{s.won ? ` · ${s.won} won` : ""}
      </p>
    );
  }
  if (sheet.kind === "tasks") {
    return <p className="text-sm text-helm-muted">{s.open || 0} still open</p>;
  }
  return null;
}

const LINE_OPTIONS = [
  { id: "revenue", label: "Revenue" },
  { id: "expense", label: "Expense" },
  { id: "skip", label: "Leave out" },
];

function LineTypes({ sheet, choice, onChange }) {
  const [open, setOpen] = useState(false);
  const lines = sheet.line_types || [];
  if (!lines.length) return null;
  const current = (label, fallback) => choice.lineTypes?.[label] || fallback;
  const left = lines.filter((l) => current(l.label, l.type) === "skip").length;
  return (
    <div className="mt-4 border-t border-helm-line pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left text-sm text-helm-fg"
        data-testid={`qi-lines-toggle-${sheet.index}`}
      >
        <ChevronDown className={cn("h-4 w-4 text-helm-muted transition-transform", open && "rotate-180")} aria-hidden />
        Check how each line is counted
        <span className="ml-auto text-xs text-helm-muted">
          {lines.length} lines{left ? `, ${left} left out` : ""}
        </span>
      </button>
      {open && (
        <ul className="mt-3 divide-y divide-helm-line">
          {lines.map((l) => {
            const value = current(l.label, l.type);
            return (
              <li key={l.label} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
                <span className={cn("text-sm", value === "skip" ? "text-helm-muted line-through decoration-helm-muted/50" : "text-helm-fg")}>
                  {l.label}
                </span>
                <div className="inline-flex shrink-0 rounded-md border border-helm-line p-0.5" role="radiogroup" aria-label={`How to count ${l.label}`}>
                  {LINE_OPTIONS.map((o) => (
                    <button
                      key={o.id}
                      type="button"
                      role="radio"
                      aria-checked={value === o.id}
                      onClick={() => onChange(l.label, o.id)}
                      className={cn(
                        "rounded px-2.5 py-1 text-xs transition-colors",
                        value === o.id ? "bg-helm-gold text-helm-navy font-medium" : "text-helm-muted hover:text-helm-fg",
                      )}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-2 text-xs text-helm-muted">Totals, profit and margin lines are left out so nothing is counted twice.</p>
    </div>
  );
}

function SheetCard({ sheet, choice, onToggle, onLineType, money, onYear, year, busy }) {
  const importable = sheet.kind !== "skip" && (sheet.records || []).length > 0;
  const records = sheetRecords(sheet, { ...choice, include: true });
  const cols = sampleColumns(sheet.kind, money);
  const mapping = Object.entries(sheet.columns || {});
  const [showSkipped, setShowSkipped] = useState(false);

  if (!importable) {
    return (
      <GlassCard className="p-4" data-testid={`qi-sheet-${sheet.index}`}>
        <div className="flex items-start gap-3">
          <FileSpreadsheet className="mt-0.5 h-4 w-4 shrink-0 text-helm-muted" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm text-helm-fg">
              <span className="font-medium">{sheet.name}</span>
              <span className="text-helm-muted"> · not imported</span>
            </p>
            <p className="mt-0.5 text-xs text-helm-muted">
              {sheet.kind === "skip"
                ? "We couldn't tell what this sheet holds, so it's left out."
                : "No rows we could use were found on this sheet."}
            </p>
          </div>
        </div>
      </GlassCard>
    );
  }

  return (
    <GlassCard
      className={cn("p-5 transition-opacity", !choice.include && "opacity-60")}
      data-testid={`qi-sheet-${sheet.index}`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={choice.include}
          onChange={(e) => onToggle(e.target.checked)}
          className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-helm-gold"
          aria-label={`Import sheet ${sheet.name}`}
          data-testid={`qi-include-${sheet.index}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <p className="font-medium text-helm-fg">{sheet.name}</p>
            <span className="rounded border border-helm-line px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide text-helm-muted">
              {sheet.kind_label}
            </span>
            {sheet.confidence === "low" && (
              <span className="rounded border border-helm-status-warning/40 bg-helm-status-warning/10 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide text-helm-fg">
                Please check
              </span>
            )}
          </div>
          <p className="mt-2 font-display text-2xl tracking-tight text-helm-fg">
            {recordsLabel(sheet.kind, records.length)}
          </p>
          <SummaryLine sheet={sheet} money={money} />
        </div>
      </div>

      {mapping.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5" aria-label="How columns were matched">
          {mapping.map(([field, header]) => (
            <span key={field} className="rounded-full border border-helm-line bg-helm-fg/[0.03] px-2.5 py-1 text-xs text-helm-muted">
              {header} <span aria-hidden>→</span><span className="sr-only">is used as</span> <span className="text-helm-fg">{fieldLabel(sheet.kind, field)}</span>
            </span>
          ))}
        </div>
      )}

      {records.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-md border border-helm-line">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-helm-line bg-helm-fg/[0.03]">
                {cols.map((c) => (
                  <th key={c.key} className={cn("px-3 py-2 text-left text-[10px] font-mono uppercase tracking-wide text-helm-muted", c.num && "text-right", c.optional && "hidden sm:table-cell")}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.slice(0, 5).map((r, i) => (
                <tr key={i} className="border-b border-helm-line last:border-0">
                  {cols.map((c) => (
                    <td key={c.key} className={cn("max-w-[180px] truncate whitespace-nowrap px-3 py-2 text-helm-fg", c.num && "text-right tabular-nums", c.optional && "hidden sm:table-cell")}>
                      {c.get(r) || <span className="text-helm-muted">·</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {records.length > 5 && (
            <p className="border-t border-helm-line px-3 py-1.5 text-xs text-helm-muted">
              and {(records.length - 5).toLocaleString()} more
            </p>
          )}
        </div>
      )}

      {sheet.kind === "financial_wide" && (
        <LineTypes sheet={sheet} choice={choice} onChange={onLineType} />
      )}

      <div className="mt-4 space-y-2">
        {sheet.assumed_year ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-helm-muted">
            <span>These months have no year. Read them as</span>
            <select
              value={year || sheet.assumed_year}
              onChange={(e) => onYear(Number(e.target.value))}
              disabled={busy}
              className="rounded-md border border-helm-line bg-helm-card px-2 py-1 text-xs text-helm-fg"
              aria-label="Year for months without a year"
            >
              {[0, 1, 2, 3].map((d) => {
                const y = new Date().getFullYear() - d;
                return <option key={y} value={y}>{y}</option>;
              })}
            </select>
          </div>
        ) : null}
        {(sheet.notes || []).filter((n) => !/read as \d{4}/.test(n)).map((n) => (
          <Notice key={n}>{n}</Notice>
        ))}
        {sheet.department && !sheet.department_enabled && (
          <Notice>This turns on the {sheet.department === "production" ? "Production" : "Procurement"} department so these rows have a home.</Notice>
        )}
        {sheet.unused_columns?.length > 0 && (
          <p className="text-xs text-helm-muted">Not used: {sheet.unused_columns.join(", ")}</p>
        )}
        {sheet.skipped_count > 0 && (
          <div>
            <button
              type="button"
              onClick={() => setShowSkipped((v) => !v)}
              className="text-xs text-helm-muted underline underline-offset-2 hover:text-helm-fg"
            >
              {sheet.skipped_count} row{sheet.skipped_count === 1 ? "" : "s"} skipped{showSkipped ? "" : ", see why"}
            </button>
            {showSkipped && (
              <ul className="mt-1.5 space-y-0.5 text-xs text-helm-muted">
                {sheet.skipped.map((s) => (
                  <li key={`${s.row}-${s.reason}`}>Row {s.row}: {s.reason}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </GlassCard>
  );
}

function DropZone({ onFile, busy }) {
  const inputRef = useRef(null);
  const [over, setOver] = useState(false);
  const pick = (file) => {
    if (!file) return;
    const name = (file.name || "").toLowerCase();
    if (name.endsWith(".xls")) {
      toast.error("Old .xls files aren't supported. In Excel, use File > Save As > .xlsx");
      return;
    }
    if (!/\.(xlsx|xlsm|csv)$/.test(name)) {
      toast.error("Choose an Excel (.xlsx) or CSV file");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      toast.error("That file is over 5 MB. Remove extra sheets and try again");
      return;
    }
    onFile(file);
  };
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!busy) pick(e.dataTransfer.files?.[0]);
      }}
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors",
        over ? "border-helm-gold bg-helm-gold/10" : "border-helm-line bg-helm-card",
      )}
      data-testid="qi-dropzone"
    >
      {busy ? (
        <>
          <Loader2 className="h-8 w-8 animate-spin text-helm-gold" aria-hidden />
          <p className="mt-4 font-display text-xl tracking-tight text-helm-fg" role="status">Reading your file</p>
          <p className="mt-1 text-sm text-helm-muted">Finding the tables and matching columns. This takes a few seconds.</p>
        </>
      ) : (
        <>
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-helm-line bg-helm-navy/5">
            <UploadCloud className="h-6 w-6 text-helm-gold" aria-hidden />
          </span>
          <p className="mt-4 font-display text-xl tracking-tight text-helm-fg">Drop a spreadsheet here</p>
          <p className="mt-1 text-sm text-helm-muted">Excel (.xlsx) or CSV, up to 5 MB. Any layout, any number of sheets.</p>
          <button type="button" className={cn(GOLD_BTN, "mt-5")} onClick={() => inputRef.current?.click()} data-testid="qi-choose">
            Choose a file
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_FILES}
            className="hidden"
            onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }}
            data-testid="qi-file-input"
          />
        </>
      )}
    </div>
  );
}

function RecentImports({ onUndone }) {
  const { data, reload } = useFetch("/quick-import/recent");
  const [busy, setBusy] = useState(null);
  const rows = data?.imports || [];
  if (!rows.length) return null;
  const undo = async (row) => {
    const ok = await confirmAction({
      title: "Undo this import?",
      description: `Everything added from ${row.filename || "this file"} is removed, including any changes made to those rows since.`,
      confirmLabel: "Undo import",
      destructive: true,
    });
    if (!ok) return;
    setBusy(row.id);
    try {
      await api.delete(`/quick-import/${row.id}`);
      toast.success("Import undone");
      reload();
      onUndone?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not undo the import"));
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="mt-10" aria-label="Recent imports">
      <p className="text-[11px] font-mono uppercase tracking-wider text-helm-muted">Recent imports</p>
      <ul className="mt-2 divide-y divide-helm-line border-y border-helm-line">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="truncate text-sm text-helm-fg">{r.filename || "Spreadsheet"}</p>
              <p className="text-xs text-helm-muted">{countsSentence(r.counts)}</p>
            </div>
            <button type="button" onClick={() => undo(r)} disabled={busy === r.id} className={cn(LINE_BTN, "px-3 py-1.5 text-xs")}>
              <Undo2 className="h-3.5 w-3.5" aria-hidden />
              {busy === r.id ? "Undoing…" : "Undo"}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function QuickImport() {
  const { user } = useAuth();
  const { data: company } = useCompanyQuery();
  const invalidateCompany = useInvalidateCompany();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [year, setYear] = useState(null);
  const [preview, setPreview] = useState(null);
  const [choices, setChoices] = useState({});
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(null);

  const isOwner = user?.role === "owner" || user?.pack === "owner";
  const symbol = currencySymbol(preview?.currency || company?.currency);
  const money = useMemo(() => (v) => formatMoney(v, symbol, { compact: Math.abs(Number(v)) >= 10000 }), [symbol]);
  const selected = useMemo(() => totalSelected(preview, choices), [preview, choices]);

  if (!isOwner) {
    return (
      <NoAccess
        title="Set up from a file"
        who="Only the company owner can import files."
        next="Ask your CEO to import the spreadsheet, or add entries on each page."
      />
    );
  }

  const readFile = async (f, y = null) => {
    setBusy(true);
    setDone(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      if (y) fd.append("year", String(y));
      const { data } = await api.post("/quick-import/preview", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setFile(f);
      setPreview(data);
      setChoices((prev) => {
        const fresh = initialChoices(data);
        // Keep the owner's ticks when only the year changed.
        if (y && prev) {
          for (const k of Object.keys(fresh)) if (prev[k]) fresh[k] = { ...fresh[k], include: prev[k].include };
        }
        return fresh;
      });
      const usable = (data.sheets || []).filter((s) => s.kind !== "skip" && s.records?.length).length;
      if (!usable) toast.error("We couldn't find anything to import in that file");
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not read that file"));
    } finally {
      setBusy(false);
    }
  };

  const onYear = (y) => {
    setYear(y);
    if (file) readFile(file, y);
  };

  const confirm = async () => {
    const payload = buildConfirmPayload(preview, choices);
    if (!payload.sheets.length) {
      toast.error("Tick at least one sheet to import");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/quick-import/confirm", payload);
      setDone(data.batch);
      setPreview(null);
      invalidateCompany();
      invalidateFetchQueries(queryClient);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      toast.error(apiErrorMessage(e, "Import failed. Nothing was added"));
    } finally {
      setSaving(false);
    }
  };

  const undoDone = async () => {
    const ok = await confirmAction({
      title: "Undo this import?",
      description: "Everything this import added is removed.",
      confirmLabel: "Undo import",
      destructive: true,
    });
    if (!ok) return;
    try {
      await api.delete(`/quick-import/${done.id}`);
      toast.success("Import undone. Nothing from that file is left");
      setDone(null);
      setFile(null);
      invalidateFetchQueries(queryClient);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not undo the import"));
    }
  };

  const reset = () => {
    setPreview(null);
    setFile(null);
    setYear(null);
    setChoices({});
  };

  if (done) {
    const destinations = Object.entries(done.counts || {})
      .filter(([, n]) => n > 0)
      .map(([k, n]) => ({ kind: COUNT_TO_KIND[k], n }));
    return (
      <div className="max-w-3xl" data-testid="qi-done">
        <GlassCard className="p-6 sm:p-8">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-helm-gold text-helm-navy">
            <Check className="h-5 w-5" strokeWidth={3} aria-hidden />
          </span>
          <h1 className="mt-5 font-display text-3xl tracking-tight text-helm-fg">Your company is in Trenston</h1>
          <p className="mt-2 text-helm-muted">
            Added {countsSentence(done.counts)} from {done.filename || "your file"}.
          </p>
          <ul className="mt-6 divide-y divide-helm-line border-y border-helm-line">
            {destinations.map((d) => {
              const dest = KIND_DESTINATION[d.kind];
              return (
                <li key={d.kind}>
                  <Link to={dest.to} className="flex items-center justify-between py-3 text-sm text-helm-fg hover:text-helm-gold">
                    <span>{recordsLabel(d.kind, d.n)}</span>
                    <span className="inline-flex items-center gap-1 text-helm-muted">
                      {dest.label} <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          <div className="mt-6 flex flex-wrap gap-2">
            <button type="button" className={GOLD_BTN} onClick={() => navigate("/app")} data-testid="qi-open-briefing">
              Open your Briefing <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
            <button type="button" className={LINE_BTN} onClick={() => { setDone(null); reset(); }}>
              Import another file
            </button>
            <button type="button" className="px-2 text-sm text-helm-muted underline underline-offset-2 hover:text-helm-fg" onClick={undoDone} data-testid="qi-undo">
              Undo this import
            </button>
          </div>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className={cn("max-w-4xl", preview && "pb-28")}>
      <PageHeader
        title="Set up from a file"
        subtitle="Drop in a spreadsheet you already keep. Trenston reads it, shows you what it found, and fills in your company once you approve."
      />

      {company?.template === "sample" && (
        <div className="mb-6">
          <Notice tone="warn">
            Your workspace still has the sample company. Remove it first in{" "}
            <Link to="/app/settings#clear-sample" className="underline underline-offset-2">Settings</Link>
            {" "}so its numbers don&apos;t mix with yours.
          </Notice>
        </div>
      )}

      {!preview ? (
        <>
          <DropZone onFile={(f) => readFile(f, null)} busy={busy} />
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            {EXAMPLES.map((ex) => (
              <div key={ex.title} className="rounded-lg border border-helm-line p-4">
                <p className="text-sm font-medium text-helm-fg">{ex.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-helm-muted">{ex.body}</p>
              </div>
            ))}
          </div>
          <p className="mt-5 text-xs leading-relaxed text-helm-muted">
            Nothing is saved until you review it, and one click undoes the whole import. Trenston never makes up numbers:
            every value comes from your file. To match columns, a few sample rows may be read by AI. Your full file is not sent.
          </p>
          <RecentImports />
        </>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1">
            <FileSpreadsheet className="h-4 w-4 text-helm-gold" aria-hidden />
            <p className="text-sm text-helm-fg">
              Here&apos;s what we found in <span className="font-medium">{preview.filename}</span>
            </p>
            <button type="button" onClick={reset} className="text-xs text-helm-muted underline underline-offset-2 hover:text-helm-fg">
              Choose a different file
            </button>
          </div>
          <div className="space-y-4" aria-busy={busy}>
            {preview.sheets.map((s) => (
              <SheetCard
                key={`${s.index}-${s.name}`}
                sheet={s}
                choice={choices[s.index] || { include: false, lineTypes: {} }}
                money={money}
                busy={busy}
                year={year}
                onYear={onYear}
                onToggle={(v) => setChoices((c) => ({ ...c, [s.index]: { ...c[s.index], include: v } }))}
                onLineType={(label, t) => setChoices((c) => ({
                  ...c,
                  [s.index]: { ...c[s.index], lineTypes: { ...(c[s.index]?.lineTypes || {}), [label]: t } },
                }))}
              />
            ))}
          </div>
          <div className="fixed inset-x-0 bottom-0 z-30 lg:left-[var(--sidebar-w,0px)] border-t border-helm-line bg-helm-card/95 backdrop-blur supports-[backdrop-filter]:bg-helm-card/80">
            <div className="mx-auto flex max-w-4xl flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-helm-muted">
                {selected ? <>Ready to add <span className="text-helm-fg">{selected.toLocaleString()}</span> rows</> : "Tick a sheet to import it"}
              </p>
              <div className="flex gap-2">
                <button type="button" className={LINE_BTN} onClick={reset} disabled={saving}>Cancel</button>
                <button
                  type="button"
                  className={GOLD_BTN}
                  onClick={confirm}
                  disabled={saving || busy || !selected}
                  data-testid="qi-confirm"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
                  {saving ? "Adding…" : "Add to Trenston"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
