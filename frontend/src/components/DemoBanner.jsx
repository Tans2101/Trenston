import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

/**
 * Shown across the app while an owner is browsing the pre-setup demo company.
 * Leaving the demo wipes it and drops them into company setup.
 */
export default function DemoBanner() {
  const [busy, setBusy] = useState(false);

  const leave = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post("/workspace/clear-sample");
      window.location.href = "/app";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not leave the demo. Please try again.");
      setBusy(false);
    }
  };

  return (
    <div
      className="lg:pl-[240px] border-b border-helm-gold/30 bg-helm-gold/10 px-5 py-2.5"
      data-testid="demo-banner"
    >
      <div className="flex flex-col gap-2 text-sm text-helm-fg sm:flex-row sm:items-center sm:justify-between lg:px-5">
        <p>
          <span className="font-medium">You're exploring a demo company.</span>{" "}
          <span className="text-helm-muted">Nothing here is yours yet.</span>
        </p>
        <button
          type="button"
          data-testid="demo-banner-setup-btn"
          onClick={leave}
          disabled={busy}
          className="self-start whitespace-nowrap rounded-md bg-helm-gold px-3.5 py-1.5 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold-hover disabled:opacity-50 sm:self-auto"
        >
          {busy ? "One moment…" : "Set up my company"}
        </button>
      </div>
    </div>
  );
}
