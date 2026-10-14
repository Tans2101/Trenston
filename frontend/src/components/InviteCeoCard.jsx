import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Copy, Handshake } from "lucide-react";
import { api } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { GlassCard } from "@/components/kit";

const STATUS_LABEL = {
  sent: "Sent",
  signed_up: "Signed up",
  converted: "Converted",
};

export default function InviteCeoCard() {
  const { data, error, loading, setData } = useFetch("/referrals");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [trackError, setTrackError] = useState("");
  const copyTimer = useRef(null);

  useEffect(() => () => {
    if (copyTimer.current) clearTimeout(copyTimer.current);
  }, []);

  const shareUrl = data?.share_url || "";
  const rows = data?.referrals || [];

  const copyLink = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      toast.success("Referral link copied");
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy. Select the link instead");
    }
  };

  const trackEmail = async () => {
    const trimmed = email.trim();
    if (!trimmed) {
      setTrackError("");
      return;
    }
    setBusy(true);
    setTrackError("");
    try {
      const { data: res } = await api.post("/referrals", { email: trimmed });
      setEmail("");
      if (res) setData(res);
      toast.success("Invite recorded");
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const raw = typeof detail === "string" && detail.trim() ? detail : "Could not record invite";
      // Referrer-profile failures are not about the typed email — keep copy generic.
      const message = /user not found|referral profile unavailable/i.test(raw)
        ? "Could not record invite"
        : raw;
      setTrackError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const linkValue = shareUrl
    || (loading ? "Generating link…" : "Could not load referral link");

  return (
    <GlassCard className="p-5 mb-4 fade-up" data-testid="invite-ceo-card">
      <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
        <Handshake className="w-4 h-4" />
        <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Refer a founder</span>
      </div>
      <p className="text-sm text-helm-muted mb-4 leading-relaxed">
        Share Trenston with another business owner you know. This is a tracking link only, so no discount or credit is applied.
      </p>
      {error && (
        <p className="text-xs text-helm-muted mb-3" data-testid="referral-load-hint">
          Referral link unavailable right now. Try again later from Account settings.
        </p>
      )}
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          data-testid="referral-link-input"
          aria-label="Your invite link"
          readOnly
          value={linkValue}
          className="flex-1 rounded-md border border-helm-line bg-helm-card px-3 py-2.5 text-sm text-helm-fg font-mono truncate"
        />
        <button
          data-testid="copy-referral-link"
          type="button"
          onClick={copyLink}
          disabled={!shareUrl}
          className="inline-flex items-center justify-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-2.5 hover:bg-helm-fg/5 disabled:opacity-50"
        >
          <Copy className="w-3.5 h-3.5" />
          {copied ? "Copied" : "Copy link"}
        </button>
      </div>
      <div className="flex flex-col sm:flex-row gap-2 mt-3">
        <input
          data-testid="referral-email-input"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setTrackError("");
          }}
          onKeyDown={(e) => e.key === "Enter" && trackEmail()}
          placeholder="Optional: their email to track this invite"
          className="flex-1 rounded-md border border-helm-line bg-helm-card px-3 py-2.5 text-sm text-helm-fg placeholder:text-helm-muted"
        />
        <button
          data-testid="referral-track-btn"
          type="button"
          onClick={trackEmail}
          disabled={busy || !email.trim()}
          className="rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold font-medium text-sm px-4 py-2.5 hover:bg-helm-gold/10 disabled:opacity-50"
        >
          {busy ? "Saving…" : "Track invite"}
        </button>
      </div>
      {trackError ? (
        <p className="text-xs text-helm-status-negative mt-2" data-testid="referral-track-error">{trackError}</p>
      ) : null}
      {rows.length > 0 && (
        <div className="mt-4 border-t border-helm-line pt-3" data-testid="referral-list">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-helm-muted mb-2">Your referrals</p>
          <ul className="space-y-1.5">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 text-sm" data-testid="referral-row">
                <span className="text-helm-fg truncate">{r.referred_email || "Link signup"}</span>
                <span className="shrink-0 font-mono text-[11px] uppercase tracking-wider text-helm-muted">
                  {STATUS_LABEL[r.status] || r.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </GlassCard>
  );
}
