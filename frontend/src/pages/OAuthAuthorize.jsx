import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { Check, KeyRound, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { GlassCard } from "@/components/kit";

const PARAM_KEYS = [
  "client_id", "redirect_uri", "response_type", "code_challenge",
  "code_challenge_method", "state", "scope", "resource",
];

function errorText(e, fallback) {
  const data = e?.response?.data;
  if (data?.error_description) return data.error_description;
  const d = data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d.message === "string") return d.message;
  return fallback;
}

/**
 * Consent screen for connecting an AI assistant (OAuth authorization endpoint).
 * Nothing is granted until the person presses Approve. Access is read-only and
 * limited to what they can already see in this workspace.
 */
export default function OAuthAuthorize() {
  const location = useLocation();
  const params = useMemo(() => {
    const q = new URLSearchParams(location.search);
    const out = {};
    PARAM_KEYS.forEach((k) => {
      const v = q.get(k);
      if (v !== null) out[k] = v;
    });
    return out;
  }, [location.search]);

  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    let alive = true;
    api.get("/oauth/authorize/info", { params })
      .then(({ data }) => { if (alive) setInfo(data); })
      .catch((e) => { if (alive) setError(errorText(e, "This connection request is not valid. Start again from your AI assistant.")); });
    return () => { alive = false; };
  }, [params]);

  const decide = async (decision) => {
    if (busy) return;
    setBusy(decision);
    try {
      const { data } = await api.post("/oauth/authorize", { ...params, decision });
      window.location.assign(data.redirect);
    } catch (e) {
      setError(errorText(e, "Could not complete the connection. Please try again."));
      setBusy(null);
    }
  };

  const name = info?.client_name || "This app";

  return (
    <div className="mx-auto max-w-xl px-4 py-10" data-testid="oauth-authorize-page">
      <GlassCard className="p-6">
        <div className="mb-3 flex items-center gap-1.5 text-helm-gold">
          <KeyRound className="h-4 w-4" />
          <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Connect an AI assistant</span>
        </div>

        {error ? (
          <div data-testid="oauth-error">
            <h1 className="text-xl font-medium text-helm-fg">This connection can&apos;t continue</h1>
            <p className="mt-3 text-sm leading-relaxed text-helm-muted">{error}</p>
          </div>
        ) : !info ? (
          <p className="text-sm text-helm-muted">Checking the request…</p>
        ) : (
          <>
            <h1 className="text-xl font-medium text-helm-fg" data-testid="oauth-title">
              {name} wants to read your Trenston workspace
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-helm-muted">
              Signed in as <span className="text-helm-fg">{info.user?.name || info.user?.email}</span>, connecting{" "}
              <span className="text-helm-fg">{info.workspace?.name}</span>. To connect a different company, switch
              workspace first, then start again from your assistant.
            </p>

            <div className="mt-5 rounded-md border border-helm-line p-4">
              <p className="text-sm font-medium text-helm-fg">It will be able to read, never change:</p>
              <ul className="mt-3 space-y-2 text-sm text-helm-fg">
                {[
                  "Your briefing and team updates",
                  "Open decisions and Trenston's recommendations",
                  "Tasks and the work assigned to you",
                  ...(info.financials_access ? ["Financial summary (you have Financials access)"] : []),
                ].map((item) => (
                  <li key={item} className="flex gap-2">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-helm-gold" aria-hidden />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs leading-relaxed text-helm-muted">
                It sees only what you can see in Trenston. Disconnect any time in Settings, under API keys.
              </p>
            </div>

            <p className="mt-4 text-sm text-helm-muted">
              After you approve, you&apos;ll go back to <span className="font-mono text-helm-fg">{info.redirect_host}</span>.
            </p>
            {info.loopback && (
              <p className="mt-3 flex gap-2 rounded-md border border-helm-line p-3 text-sm text-helm-fg" data-testid="oauth-loopback-warning">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-helm-gold" aria-hidden />
                This app runs on your own computer. Only approve if you started this connection yourself.
              </p>
            )}

            {!info.allowed && (
              <p className="mt-4 text-sm text-helm-fg" data-testid="oauth-plan-gate">
                {info.plan_message}{" "}
                <a href="/app/billing" className="text-helm-gold hover:text-helm-gold-hover">See plans →</a>
              </p>
            )}

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => decide("approve")}
                disabled={!!busy || !info.allowed}
                className="rounded-md bg-helm-gold px-4 py-2.5 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold-hover disabled:opacity-60"
                data-testid="oauth-approve"
              >
                {busy === "approve" ? "Connecting…" : `Allow ${name}`}
              </button>
              <button
                type="button"
                onClick={() => decide("deny")}
                disabled={!!busy}
                className="rounded-md border border-helm-line px-4 py-2.5 text-sm text-helm-fg hover:bg-helm-fg/5 disabled:opacity-60"
                data-testid="oauth-deny"
              >
                {busy === "deny" ? "Cancelling…" : "Cancel"}
              </button>
            </div>
          </>
        )}
      </GlassCard>
    </div>
  );
}
