import { useState } from "react";
import { toast } from "sonner";
import { Building2, KeyRound, ArrowRight, LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { GlassCard } from "@/components/kit";
import { consumeReferralCode, withReferralPayload } from "@/lib/referral";
import TrenstonMark from "@/components/HelmMark";

export default function WorkspaceGate() {
  const { user, logout } = useAuth();
  const [mode, setMode] = useState(null); // "create" | "join"
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [ageConfirmed, setAgeConfirmed] = useState(Boolean(user?.age_confirmed));

  const create = async () => {
    if (!name.trim()) { toast.error("Name your company"); return; }
    if (!ageConfirmed && !user?.age_confirmed) {
      toast.error("Confirm you are 18+ (or using Trenston under a parent/guardian)");
      return;
    }
    setBusy(true);
    try {
      if (!user?.age_confirmed) {
        await api.patch("/account/age-confirmation", { confirmed: true });
      }
      await api.post("/workspaces", withReferralPayload({ name: name.trim() }));
      consumeReferralCode();
      window.location.href = "/app";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create company");
      setBusy(false);
    }
  };

  const join = async () => {
    if (!code.trim()) { toast.error("Enter your invite code"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/workspaces/join", { code: code.trim() });
      if (data.ok) window.location.href = "/app";
    } catch (e) { toast.error(e?.response?.data?.detail || "Invalid invite code"); setBusy(false); }
  };

  return (
    <div className="min-h-screen grain flex flex-col items-center justify-center px-5 py-12">
      <div className="w-full max-w-xl">
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-2.5">
            <TrenstonMark size={36} className="rounded-md" />
            <div>
              <p className="text-helm-fg font-semibold tracking-tight leading-none">Trenston</p>
              <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-helm-muted mt-1">Company Workspace</p>
            </div>
          </div>
          <button data-testid="gate-logout" onClick={logout} className="text-helm-muted hover:text-helm-fg flex items-center gap-1.5 text-sm"><LogOut className="w-4 h-4" /> Sign out</button>
        </div>

        <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold">Welcome, {user?.name?.split(" ")[0] || "there"}</p>
        <h1 className="font-display mt-3 text-3xl md:text-4xl font-normal tracking-tight text-helm-fg">Join your company on Trenston.</h1>
        <p className="mt-3 text-helm-muted">If your team already uses Trenston, join with an invite code. Starting fresh? Create your company.</p>

        {!mode && (
          <div className="mt-10 grid sm:grid-cols-2 gap-4 fade-up">
            <button data-testid="gate-join-choice" onClick={() => setMode("join")}
              className="text-left rounded-xl border border-helm-line bg-helm-fg/[0.02] p-6 transition-colors hover:border-helm-gold/35 group">
              <div className="w-11 h-11 rounded-xl bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center"><KeyRound className="w-5 h-5 text-helm-gold" /></div>
              <h3 className="mt-4 text-lg text-helm-fg tracking-tight">Join with a code</h3>
              <p className="mt-1.5 text-sm text-helm-muted leading-relaxed">Enter the invite code your admin shared, or use your email invite link.</p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-sm text-helm-gold">Enter code <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></span>
            </button>
            <button data-testid="gate-create-choice" onClick={() => setMode("create")}
              className="text-left rounded-xl border border-helm-line bg-helm-fg/[0.02] p-6 transition-colors hover:border-helm-gold/35 group">
              <div className="w-11 h-11 rounded-xl bg-helm-fg/[0.04] border border-helm-line flex items-center justify-center"><Building2 className="w-5 h-5 text-helm-gold" /></div>
              <h3 className="mt-4 text-lg text-helm-fg tracking-tight">Create a company</h3>
              <p className="mt-1.5 text-sm text-helm-muted leading-relaxed">Name your company now. You'll set up the rest (stage, team, industry) on the next screen.</p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-sm text-helm-gold">Get started <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></span>
            </button>
          </div>
        )}

        {mode === "join" && (
          <GlassCard className="mt-10 p-6 fade-up">
            <label className="text-xs text-helm-muted">Invite code
              <input data-testid="gate-code-input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Paste your invite code"
                onKeyDown={(e) => e.key === "Enter" && join()}
                autoCapitalize="off"
                autoCorrect="off"
                spellCheck={false}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 font-mono focus:outline-none focus:border-helm-gold/40" />
            </label>
            <div className="flex gap-2 mt-4">
              <button onClick={() => setMode(null)} className="rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/5">Back</button>
              <button data-testid="gate-join-btn" onClick={join} disabled={busy} className="flex-1 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Joining…" : "Join company"}</button>
            </div>
          </GlassCard>
        )}

        {mode === "create" && (
          <GlassCard className="mt-10 p-6 fade-up">
            <label className="text-xs text-helm-muted">Company name
              <input data-testid="gate-name-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Inc."
                onKeyDown={(e) => e.key === "Enter" && create()}
                className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/40" />
            </label>
            {!user?.age_confirmed && (
              <label className="mt-4 flex items-start gap-2.5 text-sm text-helm-muted cursor-pointer" data-testid="gate-age-confirm">
                <input
                  type="checkbox"
                  checked={ageConfirmed}
                  onChange={(e) => setAgeConfirmed(e.target.checked)}
                  className="mt-0.5 rounded border-helm-line"
                />
                <span>
                  I confirm I am 18 or older, or I am using Trenston under a parent or guardian&apos;s supervision.
                </span>
              </label>
            )}
            <div className="flex gap-2 mt-4">
              <button onClick={() => setMode(null)} className="rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/5">Back</button>
              <button
                data-testid="gate-create-btn"
                onClick={create}
                disabled={busy || (!user?.age_confirmed && !ageConfirmed)}
                className="flex-1 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
              >
                {busy ? "Creating…" : "Create company"}
              </button>
            </div>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
