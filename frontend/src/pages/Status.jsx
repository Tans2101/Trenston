import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight, RefreshCw } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { API } from "@/lib/api";
import {
  STATUS_COMPONENTS,
  STATUS_DISCLAIMER,
  STATUS_INCIDENTS,
  STATUS_TRACKING_STARTED,
} from "@/lib/statusConfig";
import { CATEGORY, PUBLIC_CONTACT_MAILTO } from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.6, ease, delay: i * 0.05 } }),
};

function toneFor(state) {
  if (state === "operational") return "text-helm-status-positive border-helm-status-positive/35 bg-helm-status-positive/10";
  if (state === "degraded") return "text-helm-gold border-helm-gold/35 bg-helm-gold/10";
  if (state === "down") return "text-helm-status-negative border-helm-status-negative/35 bg-helm-status-negative/10";
  return "text-helm-slate border-helm-navy/15 bg-helm-fg/[0.03]";
}

function labelFor(state) {
  if (state === "operational") return "Operational";
  if (state === "degraded") return "Degraded";
  if (state === "down") return "Unavailable";
  return "Checking…";
}

export default function Status() {
  const { authed, enter } = useMarketingAuth();
  const [rows, setRows] = useState(() =>
    STATUS_COMPONENTS.map((c) => ({ ...c, state: "checking", note: "" })),
  );
  const [checkedAt, setCheckedAt] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    const next = STATUS_COMPONENTS.map((c) => ({
      ...c,
      state: c.check === "page" ? "operational" : "checking",
      note: c.check === "page" ? "This page loaded successfully." : "",
    }));
    setRows(next);
    try {
      // Public probe — raw fetch so Clerk auth interceptors cannot block anonymous visitors.
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 8000);
      const res = await fetch(`${API}/health`, { signal: ctrl.signal, credentials: "omit" });
      clearTimeout(timer);
      const data = await res.json().catch(() => ({}));
      const apiOk = res.ok && data?.status === "ok";
      const mongoOk = Boolean(data?.mongo);
      setRows((prev) =>
        prev.map((row) => {
          if (row.check === "page") return row;
          if (row.check === "api") {
            return {
              ...row,
              state: apiOk ? "operational" : "down",
              note: apiOk
                ? `Responded OK${data?.mongo_source ? ` · Mongo source: ${data.mongo_source}` : ""}`
                : "Health endpoint did not report status ok.",
            };
          }
          if (row.check === "mongo") {
            return {
              ...row,
              state: apiOk && mongoOk ? "operational" : apiOk ? "degraded" : "down",
              note: !apiOk
                ? "Could not reach the API health probe."
                : mongoOk
                  ? "Atlas ping succeeded."
                  : "API is up but MongoDB ping failed.",
            };
          }
          return row;
        }),
      );
    } catch {
      setRows((prev) =>
        prev.map((row) => {
          if (row.check === "page") return row;
          return {
            ...row,
            state: "down",
            note: "Could not reach /api/health (network error or API offline).",
          };
        }),
      );
    } finally {
      setCheckedAt(new Date());
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
    refresh();
  }, [refresh]);

  const worst = rows.reduce((acc, r) => {
    const rank = { down: 3, degraded: 2, checking: 1, operational: 0 };
    return (rank[r.state] || 0) > (rank[acc] || 0) ? r.state : acc;
  }, "operational");

  return (
    <div className="min-h-screen overflow-x-hidden bg-helm-cream text-helm-navy">
      <MarketingNav authed={authed} onEnter={enter} active="/status" />

      <main>
        <section className="px-6 pb-12 pt-36 md:pb-16 md:pt-44">
          <div className="mx-auto max-w-3xl">
            <motion.p variants={fade} initial="hidden" animate="show" custom={0}
              className="font-mono text-xs uppercase tracking-[0.3em] text-helm-slate">
              {CATEGORY}
            </motion.p>
            <motion.h1 variants={fade} initial="hidden" animate="show" custom={1}
              className="font-display mt-8 text-5xl font-medium leading-[1.05] tracking-[-0.03em] md:text-6xl">
              Status
            </motion.h1>
            <motion.p variants={fade} initial="hidden" animate="show" custom={2}
              className="mt-6 max-w-2xl text-lg leading-relaxed text-helm-slate">
              Live checks against Trenston&apos;s production stack. No invented historical uptime charts.
            </motion.p>
            <motion.div variants={fade} initial="hidden" animate="show" custom={3}
              className={`mt-8 inline-flex items-center gap-3 rounded-full border px-4 py-2 text-sm ${toneFor(worst)}`}>
              <span className="font-medium">{labelFor(worst)}</span>
              <span className="text-xs opacity-80">overall</span>
            </motion.div>
          </div>
        </section>

        <section className="border-t border-helm-navy/[0.05] px-6 py-16">
          <div className="mx-auto max-w-3xl">
            <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
                Components
              </p>
              <button
                type="button"
                onClick={refresh}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-md border border-helm-navy/15 px-3 py-1.5 text-xs text-helm-navy hover:border-helm-navy/30 disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} aria-hidden />
                Refresh
              </button>
            </div>
            <ul className="space-y-3">
              {rows.map((row) => (
                <li
                  key={row.id}
                  className="rounded-xl border border-helm-navy/[0.07] bg-white p-5"
                  data-testid={`status-row-${row.id}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="text-sm font-medium text-helm-navy">{row.name}</h2>
                      <p className="mt-1 text-sm leading-relaxed text-helm-slate">{row.detail}</p>
                      {row.note ? (
                        <p className="mt-2 font-mono text-[11px] text-helm-slate/90">{row.note}</p>
                      ) : null}
                    </div>
                    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium ${toneFor(row.state)}`}>
                      {labelFor(row.state)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            {checkedAt ? (
              <p className="mt-4 font-mono text-[11px] text-helm-slate">
                Last checked {checkedAt.toLocaleString()}
              </p>
            ) : null}
            <p className="mt-8 text-sm leading-relaxed text-helm-slate">{STATUS_DISCLAIMER}</p>
          </div>
        </section>

        <section className="border-t border-helm-navy/[0.05] px-6 py-16">
          <div className="mx-auto max-w-3xl">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
              Incident history
            </p>
            <h2 className="font-display mt-3 text-2xl font-medium tracking-tight">
              Since {STATUS_TRACKING_STARTED}
            </h2>
            {STATUS_INCIDENTS.length === 0 ? (
              <p className="mt-4 text-sm leading-relaxed text-helm-slate">
                No public incidents recorded since status tracking began. When something material happens,
                we will list it here with a start time and resolution note — not a fabricated uptime percentage.
              </p>
            ) : (
              <ul className="mt-6 space-y-4">
                {STATUS_INCIDENTS.map((inc) => (
                  <li key={inc.date + inc.title} className="rounded-xl border border-helm-navy/[0.07] p-5">
                    <p className="font-mono text-[11px] text-helm-slate">{inc.date}</p>
                    <h3 className="mt-1 text-sm font-medium text-helm-navy">{inc.title}</h3>
                    <p className="mt-2 text-sm text-helm-slate">{inc.body}</p>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-8 text-sm text-helm-slate">
              Suspect an outage we have not listed?{" "}
              <a href={PUBLIC_CONTACT_MAILTO} className="text-helm-navy hover:text-helm-gold transition-colors">
                Contact us
              </a>
              {" · "}
              <Link to="/changelog" className="text-helm-navy hover:text-helm-gold transition-colors">
                Changelog
              </Link>
            </p>
          </div>
        </section>

        <section className="px-6 pb-24">
          <div className="mx-auto max-w-3xl text-center">
            <button
              type="button"
              onClick={enter}
              className="group inline-flex items-center gap-2 rounded-md bg-helm-cream px-6 py-3 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold"
            >
              {authed ? "Open cockpit" : "Get started"}
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </button>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}
