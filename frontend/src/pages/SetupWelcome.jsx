import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import TrenstonMark from "@/components/HelmMark";

/**
 * First screen a new owner sees, before company details.
 * Demo: opens the real app on an example company. Setup: straight to the form.
 */
export default function SetupWelcome({ onSetup }) {
  const [busy, setBusy] = useState(false);

  const openDemo = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post("/workspace/apply-template", { template: "demo" });
      window.location.href = "/app";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not open the demo. Please try again.");
      setBusy(false);
    }
  };

  const options = [
    {
      id: "demo",
      testId: "welcome-demo-btn",
      title: "Explore a demo company",
      body: "Opens Trenston on an example company: six months of financials, open decisions, tasks and a team. Click around, then set up your own company when you're ready. Nothing you do in the demo carries over.",
      cta: busy ? "Opening…" : "Explore the demo",
      onClick: openDemo,
      primary: true,
    },
    {
      id: "setup",
      testId: "welcome-setup-btn",
      title: "Set up my company",
      body: "Go straight to your company details. Takes about two minutes.",
      cta: "Set up my company",
      onClick: onSetup,
      primary: false,
    },
  ];

  return (
    <div className="min-h-screen bg-helm-bg" data-testid="setup-welcome">
      <header className="border-b border-helm-line">
        <div className="mx-auto flex max-w-3xl items-center gap-2.5 px-5 py-4">
          <TrenstonMark size={28} className="rounded-md" />
          <span className="text-sm font-semibold tracking-tight text-helm-fg">Trenston</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 pt-12 pb-20">
        <h1 className="font-display text-3xl font-normal tracking-tight text-helm-fg">Welcome to Trenston</h1>
        <p className="mt-2 max-w-xl text-sm text-helm-muted leading-relaxed">
          See what it looks like first, or go straight to setting up your company.
        </p>

        <div className="mt-10 border-t border-helm-line">
          {options.map((o) => (
            <div
              key={o.id}
              className="grid gap-4 border-b border-helm-line py-6 sm:grid-cols-[1fr_auto] sm:items-center sm:gap-10"
            >
              <div>
                <p className="text-base text-helm-fg">{o.title}</p>
                <p className="mt-1 max-w-lg text-sm text-helm-muted leading-relaxed">{o.body}</p>
              </div>
              <button
                type="button"
                data-testid={o.testId}
                onClick={o.onClick}
                disabled={busy}
                className={cn(
                  "whitespace-nowrap rounded-md px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50",
                  o.primary
                    ? "bg-helm-gold text-helm-navy hover:bg-helm-gold-hover"
                    : "border border-helm-line text-helm-fg hover:bg-helm-fg/[0.04]",
                )}
              >
                {o.cta}
              </button>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
