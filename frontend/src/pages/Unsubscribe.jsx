import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { COMPANY_LOCATION, PUBLIC_CONTACT_EMAIL, PUBLIC_CONTACT_MAILTO } from "@/lib/marketingCopy";
import TrenstonMark from "@/components/HelmMark";
import { API } from "@/lib/api";

/**
 * Public unsubscribe confirmation. The email link points here with ?token=...
 * On load we POST to the API so suppression is written immediately (no second click).
 * Mail-client one-click uses POST /api/email/unsubscribe directly.
 */
export default function Unsubscribe() {
  const [params] = useSearchParams();
  const token = (params.get("token") || "").trim();
  const statusParam = (params.get("status") || "").trim();
  const [state, setState] = useState(() => {
    if (statusParam === "ok") return "ok";
    if (statusParam === "invalid") return "invalid";
    if (statusParam === "error") return "error";
    if (token) return "working";
    return "missing";
  });

  useEffect(() => {
    if (!token || statusParam) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API}/email/unsubscribe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (cancelled) return;
        if (res.ok) setState("ok");
        else if (res.status === 400) setState("invalid");
        else setState("error");
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, statusParam]);

  const title =
    state === "ok"
      ? "You're unsubscribed"
      : state === "working"
        ? "Unsubscribing…"
        : state === "invalid"
          ? "This link is invalid or expired"
          : state === "missing"
            ? "Missing unsubscribe link"
            : "Something went wrong";

  const body =
    state === "ok"
      ? "You will no longer receive Trenston weekly pack or catch-up reminder emails at this address. Transactional messages (invites, task assignments, and high-severity alerts) are unchanged."
      : state === "working"
        ? "One moment — we're updating your preferences."
        : state === "invalid"
          ? "Request a fresh link from a recent Trenston email, or contact us and we'll remove you manually."
          : state === "missing"
            ? "Open the Unsubscribe link from a Trenston email to opt out of product emails."
            : "Please try again in a moment, or email us and we'll help.";

  return (
    <div className="min-h-screen bg-helm-cream text-helm-navy">
      <div className="relative z-10 mx-auto max-w-lg px-6 py-16 md:py-24">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-helm-slate hover:text-helm-navy transition-colors mb-10">
          <TrenstonMark size={24} className="rounded" />
          Back to Trenston
        </Link>

        <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold mb-4">Email preferences</p>
        <h1 className="font-display text-3xl md:text-4xl font-medium tracking-tight text-helm-navy">{title}</h1>
        <p className="mt-4 text-[15px] text-helm-navy/80 leading-relaxed">{body}</p>
        <p className="mt-8 text-sm text-helm-slate leading-relaxed">
          Trenston · {COMPANY_LOCATION}
          <br />
          <a href={PUBLIC_CONTACT_MAILTO} className="text-helm-gold hover:underline">{PUBLIC_CONTACT_EMAIL}</a>
        </p>
      </div>
    </div>
  );
}
