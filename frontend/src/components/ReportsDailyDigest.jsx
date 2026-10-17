import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { api } from "@/lib/api";
import { fetchErrorMessage } from "@/hooks/useFetch";
import { GlassCard, SectionLabel, SkeletonCardList } from "@/components/kit";
import AiSummaryMeta from "@/components/AiSummaryMeta";
import { todayISO, addDaysISO } from "@/lib/dates";
import { useWorkspaceTimezone } from "@/hooks/useWorkspaceTimezone";

const REPORT_UPLOAD_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv",
  "application/csv",
];
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;

function acceptFile(file) {
  if (!file) return false;
  if (REPORT_UPLOAD_TYPES.includes(file.type)) return true;
  const name = (file.name || "").toLowerCase();
  return name.endsWith(".xlsx") || name.endsWith(".csv")
    || name.endsWith(".pdf") || name.endsWith(".png")
    || name.endsWith(".jpg") || name.endsWith(".jpeg");
}

function mimeForFile(file) {
  if (file.type && REPORT_UPLOAD_TYPES.includes(file.type)) return file.type;
  const name = (file.name || "").toLowerCase();
  if (name.endsWith(".xlsx")) return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  if (name.endsWith(".csv")) return "text/csv";
  if (name.endsWith(".pdf")) return "application/pdf";
  if (name.endsWith(".png")) return "image/png";
  if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
  return file.type || "application/octet-stream";
}

/**
 * Running daily digest of uploaded report files (xlsx/csv/pdf/images).
 * Distinct from Weekly CEO Pack and auto_fin/team/exec cards.
 */
/** Upload errors as plain text (FastAPI may send a string or a list). */
export function uploadErrorText(e, fallback) {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  return fallback;
}

export default function ReportsDailyDigest({ canWrite }) {
  const tz = useWorkspaceTimezone();
  const today = todayISO(tz);
  const [date, setDate] = useState(() => todayISO(tz));
  const [retrying, setRetrying] = useState(null);
  const [digest, setDigest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  const loadDigest = useCallback(async (day) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get("/reports/digest", { params: { date: day } });
      setDigest(data);
    } catch (e) {
      setDigest(null);
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDigest(date);
  }, [date, loadDigest]);

  const processFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter(Boolean);
    if (!files.length) return;
    for (const file of files) {
      if (!acceptFile(file)) {
        toast.error(`${file.name}: use PDF, PNG, JPEG, XLSX, or CSV`);
        return;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        toast.error(`${file.name}: must be 15MB or smaller`);
        return;
      }
    }
    setUploading(true);
    let added = 0;
    // One bad file should not stop the rest: keep going and report each failure.
    for (const file of files) {
      try {
        const fd = new FormData();
        const blob = new File([file], file.name, { type: mimeForFile(file) });
        fd.append("file", blob);
        fd.append("report_date", date);
        const { data: uploaded } = await api.post("/reports/documents/upload", fd, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 60000,
        });
        try {
          await api.post(`/reports/documents/${uploaded.document_id}/summarize`, null, { timeout: 120000 });
          added += 1;
        } catch (e) {
          toast.error(`${file.name}: ${uploadErrorText(e, "saved, but could not be read yet. Try again from the list.")}`);
        }
      } catch (e) {
        toast.error(`${file.name}: ${uploadErrorText(e, "could not be uploaded")}`);
      }
    }
    if (added > 0) toast.success(added === 1 ? "File added to the day's summary" : `${added} files added`);
    setUploading(false);
    if (inputRef.current) inputRef.current.value = "";
    await loadDigest(date);
  };

  const retry = async (r) => {
    setRetrying(r.id);
    try {
      await api.post(`/reports/documents/${r.id}/summarize`, null, { timeout: 120000 });
      toast.success(`${r.filename} is ready`);
    } catch (e) {
      toast.error(uploadErrorText(e, "Could not read this file"));
    } finally {
      setRetrying(null);
      await loadDigest(date);
    }
  };

  const isToday = date === today;
  const reports = digest?.reports || [];
  const combined = (digest?.combined_digest || "").trim();

  return (
    <GlassCard className="p-5 fade-up border-helm-line" data-testid="reports-daily-digest">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <p className="text-sm text-helm-fg">{isToday ? "Today" : date}</p>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <input
            type="date"
            value={date}
            max={today}
            aria-label="Day"
            onChange={(e) => setDate(e.target.value || today)}
            data-testid="digest-date"
            className="rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-2.5 py-2 focus:outline-none focus:border-helm-gold/40"
          />
          {!isToday && (
            <button
              type="button"
              data-testid="digest-today-btn"
              onClick={() => setDate(today)}
              className="text-xs text-helm-gold hover:text-helm-gold-hover font-medium"
            >
              Today
            </button>
          )}
          <button
            type="button"
            data-testid="digest-yesterday-btn"
            onClick={() => setDate(addDaysISO(today, -1))}
            className="text-xs text-helm-muted hover:text-helm-fg font-medium"
          >
            Yesterday
          </button>
        </div>
      </div>

      {canWrite && (
        <div className="mb-5">
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.xlsx,.csv,application/pdf,image/png,image/jpeg,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            multiple
            className="hidden"
            data-testid="digest-file-input"
            onChange={(e) => processFiles(e.target.files)}
          />
          <button
            type="button"
            data-testid="digest-upload-btn"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
            className="inline-flex items-center gap-2 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
          >
            <Upload className="w-4 h-4" />
            {uploading ? "Reading files…" : "Add files"}
          </button>
          <p className="text-[11px] text-helm-muted mt-2">PDF, PNG, JPEG, XLSX, or CSV. Multiple files at once are fine.</p>
        </div>
      )}

      {loading && !digest ? (
        <SkeletonCardList count={2} />
      ) : error && !digest ? (
        <p className="text-sm text-helm-muted">
          {fetchErrorMessage(error, "Could not load this day's files.")}{" "}
          <button type="button" className="text-helm-gold hover:underline" onClick={() => loadDigest(date)}>Retry</button>
        </p>
      ) : reports.length === 0 ? (
        <p className="text-sm text-helm-muted leading-relaxed" data-testid="digest-empty">
          No files for this day yet.
          {canWrite ? " Add one and Trenston will summarize what is in it, using only the numbers in the file." : ""}
        </p>
      ) : (
        <>
          {combined ? (
            <div className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-4 mb-5" data-testid="digest-combined">
              <AiSummaryMeta
                asOf={digest?.data_as_of}
                detailHref="/app/reports"
                detailLabel="uploaded reports"
                className="mb-2"
              />
              <p className="text-[10px] font-mono uppercase tracking-wider text-helm-muted mb-2">Summary of the day</p>
              <div className="text-sm text-helm-fg leading-relaxed whitespace-pre-wrap">{combined}</div>
            </div>
          ) : (
            <p className="text-sm text-helm-muted mb-5">
              {uploading
                ? "Reading files…"
                : "The day's summary appears once at least one file below has been read."}
            </p>
          )}

          <SectionLabel className="mb-3">Files</SectionLabel>
          <ul className="space-y-3" data-testid="digest-file-list">
            {reports.map((r) => (
              <li
                key={r.id}
                className="rounded-lg border border-helm-line bg-helm-fg/[0.02] px-3 py-3"
                data-testid={`digest-file-${r.id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-helm-fg font-medium truncate">{r.filename}</p>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="text-[10px] font-mono uppercase text-helm-muted">
                      {r.status === "summarized" ? "Ready" : r.status === "failed" ? "Could not read" : "Not read yet"}
                    </span>
                    {canWrite && r.status !== "summarized" && (
                      <button
                        type="button"
                        data-testid={`digest-retry-${r.id}`}
                        disabled={retrying === r.id || uploading}
                        onClick={() => retry(r)}
                        className="text-xs text-helm-gold hover:text-helm-gold-hover disabled:opacity-60"
                      >
                        {retrying === r.id ? "Reading…" : "Try again"}
                      </button>
                    )}
                  </span>
                </div>
                {r.summary && (
                  <p className={`text-sm mt-1.5 leading-relaxed ${r.unclear ? "text-helm-status-warning" : "text-helm-muted"}`}>
                    {r.summary}
                  </p>
                )}
                {r.key_figures?.length > 0 && (
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                    {r.key_figures.map((f) => (
                      <span key={`${f.label}-${f.value}`} className="text-[11px] font-mono text-helm-muted">
                        <span className="text-helm-fg/80">{f.label}:</span> {f.value}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </GlassCard>
  );
}
