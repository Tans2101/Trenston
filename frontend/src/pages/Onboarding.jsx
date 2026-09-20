import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Sparkles, PenLine, ArrowRight, Check, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { GlassCard, ErrorScreen, SkeletonCardList } from "@/components/kit";
import { useDepartmentsQuery } from "@/hooks/useDepartmentsQuery";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { departmentIcon } from "@/lib/departmentIcons";
import { cn } from "@/lib/utils";

/** Auto-enabled on every workspace — shown on, not removable in this step. */
const LOCKED_TYPES = new Set(["sales", "accounting_finance"]);

export default function Onboarding() {
  const { data, loading, error, reload } = useDepartmentsQuery();
  const { data: company } = useCompanyQuery();
  const hasTeam = company?.has_team !== false;
  const [step, setStep] = useState("departments"); // departments | template
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(null);

  const departments = useMemo(
    () => data?.departments || [],
    [data?.departments],
  );
  const lockedDepts = useMemo(
    () => departments.filter((d) => LOCKED_TYPES.has(d.type)),
    [departments],
  );
  const optionalDepts = useMemo(
    () => departments.filter((d) => !LOCKED_TYPES.has(d.type)),
    [departments],
  );

  const toggleOptional = (type) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const confirmDepartments = async () => {
    if (busy) return;
    setBusy("departments");
    try {
      // Only POST newly chosen optional types — Sales/Finance are already on.
      const toEnable = optionalDepts.filter((d) => selected.has(d.type) && !d.enabled);
      for (const dept of toEnable) {
        try {
          await api.post("/departments", { type: dept.type });
        } catch (e) {
          // Idempotent enough: already-enabled is fine if another session raced.
          if (e?.response?.status !== 409) throw e;
        }
      }
      setStep("template");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not enable departments");
    } finally {
      setBusy(null);
    }
  };

  const choose = async (template) => {
    setBusy(template);
    try {
      await api.post("/workspace/apply-template", { template });
      window.location.href = "/app";
    } catch (e) {
      toast.error("Something went wrong. Please try again.");
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-8">
        <SkeletonCardList count={4} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load departments"
        message="Department options are unavailable right now."
        onRetry={reload}
      />
    );
  }

  if (step === "departments") {
    return (
      <div className="max-w-3xl mx-auto py-8 fade-up" data-testid="onboarding-departments-step">
        <div className="text-center">
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-helm-gold">Welcome to Trenston</p>
          <h1 className="font-display mt-4 text-3xl md:text-4xl font-normal tracking-tight text-helm-fg">
            Choose your departments.
          </h1>
          <p className="mt-3 text-helm-muted max-w-lg mx-auto">
            Sales and Accounting &amp; Finance are already on. Add any others you need now — you can change this later in Settings.
          </p>
        </div>

        <div className="mt-10 space-y-2" data-testid="onboarding-department-catalog">
          {lockedDepts.map((dept) => {
            const Icon = departmentIcon(dept.icon);
            return (
              <div
                key={dept.type}
                className="flex items-center gap-3 rounded-md border border-helm-gold/25 bg-helm-gold/[0.06] px-3 py-3"
                data-testid={`onboarding-dept-locked-${dept.type}`}
              >
                <Icon className="w-4 h-4 text-helm-gold shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-helm-fg truncate">{dept.name}</p>
                  <p className="text-[11px] text-helm-muted">Always included</p>
                </div>
                <Lock className="w-3.5 h-3.5 text-helm-muted shrink-0" aria-hidden />
                <span className="text-[11px] font-mono uppercase tracking-wide text-helm-status-positive shrink-0">
                  On
                </span>
              </div>
            );
          })}

          {optionalDepts.map((dept) => {
            const Icon = departmentIcon(dept.icon);
            const checked = selected.has(dept.type);
            return (
              <button
                key={dept.type}
                type="button"
                data-testid={`onboarding-dept-toggle-${dept.type}`}
                aria-pressed={checked}
                onClick={() => toggleOptional(dept.type)}
                className={cn(
                  "w-full flex items-center gap-3 rounded-md border px-3 py-3 text-left transition-colors",
                  checked
                    ? "border-helm-gold/35 bg-helm-gold/[0.08]"
                    : "border-helm-line bg-helm-fg/[0.02] hover:border-helm-fg/20",
                )}
              >
                <span
                  className={cn(
                    "flex h-4 w-4 items-center justify-center rounded border shrink-0",
                    checked
                      ? "border-helm-gold bg-helm-gold text-helm-navy"
                      : "border-helm-line bg-transparent",
                  )}
                  aria-hidden
                >
                  {checked ? <Check className="w-3 h-3" /> : null}
                </span>
                <Icon className="w-4 h-4 text-helm-muted shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-helm-fg truncate">{dept.name}</p>
                  <p className="text-[11px] text-helm-muted">Optional</p>
                </div>
              </button>
            );
          })}
        </div>

        <div className="mt-8 flex flex-col sm:flex-row sm:items-center gap-3">
          <button
            type="button"
            data-testid="onboarding-departments-continue"
            onClick={confirmDepartments}
            disabled={!!busy}
            className="group inline-flex items-center justify-center gap-2 rounded-lg bg-helm-gold text-helm-navy font-medium px-5 py-2.5 transition-colors hover:bg-helm-gold-hover disabled:opacity-60"
          >
            {busy === "departments" ? "Saving…" : "Continue"}
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
          </button>
          <p className="text-xs text-helm-muted">
            {selected.size === 0
              ? "No extras selected — you can enable more later."
              : `${selected.size} extra department${selected.size === 1 ? "" : "s"} selected.`}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto py-8 fade-up" data-testid="onboarding-template-step">
      <div className="text-center">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-helm-gold">Welcome to Trenston</p>
        <h1 className="font-display mt-4 text-3xl md:text-4xl font-normal tracking-tight text-helm-fg">Let&apos;s set up your cockpit.</h1>
        <p className="mt-3 text-helm-muted max-w-md mx-auto">Explore with a fully-loaded sample company, or start clean and bring in your own data.</p>
      </div>

      <div className="mt-12 grid md:grid-cols-2 gap-5">
        <GlassCard className="p-7 flex flex-col">
          <div className="w-11 h-11 rounded-xl bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-helm-gold" />
          </div>
          <h3 className="mt-5 text-xl text-helm-fg tracking-tight">Explore with sample data</h3>
          <p className="mt-2 text-sm text-helm-muted leading-relaxed flex-1">
            Load &quot;Northwind Robotics&quot;, a realistic company with financials, decisions, tasks and a team. See exactly how Trenston works in 10 seconds.
          </p>
          <ul className="mt-4 space-y-1.5">
            {["6 months of financials", "Live briefing & decisions", "Full team & telemetry"].map((f) => (
              <li key={f} className="flex items-center gap-2 text-xs text-helm-muted"><Check className="w-3.5 h-3.5 text-helm-gold" />{f}</li>
            ))}
          </ul>
          <button data-testid="onboarding-sample-btn" onClick={() => choose("sample")} disabled={!!busy}
            className="group mt-6 inline-flex items-center justify-center gap-2 rounded-lg bg-helm-gold text-helm-navy font-medium py-2.5 transition-colors hover:bg-helm-gold-hover disabled:opacity-60">
            {busy === "sample" ? "Loading…" : "Explore sample"}
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
          </button>
        </GlassCard>

        <GlassCard className="p-7 flex flex-col">
          <div className="w-11 h-11 rounded-xl bg-helm-fg/[0.04] border border-helm-line flex items-center justify-center">
            <PenLine className="w-5 h-5 text-helm-gold" />
          </div>
          <h3 className="mt-5 text-xl text-helm-fg tracking-tight">Start clean</h3>
          <p className="mt-2 text-sm text-helm-muted leading-relaxed flex-1">
            {hasTeam
              ? "Begin with an empty cockpit and make it yours. Log your financials, invite your team, and connect your tools. Trenston builds your command center around real data."
              : "Begin with an empty cockpit and make it yours. Log your own financials and connect your tools — Trenston builds your command center around real data."}
          </p>
          <ul className="mt-4 space-y-1.5">
            {(hasTeam
              ? ["Log financials in Trenston", "Invite your finance team", "Connect Google, QuickBooks & more"]
              : ["Log your own financials", "Connect Google, QuickBooks & more", "Build your briefing from real numbers"]
            ).map((f) => (
              <li key={f} className="flex items-center gap-2 text-xs text-helm-muted"><Check className="w-3.5 h-3.5 text-helm-muted" />{f}</li>
            ))}
          </ul>
          <button data-testid="onboarding-clean-btn" onClick={() => choose("clean")} disabled={!!busy}
            className="mt-6 inline-flex items-center justify-center gap-2 rounded-lg border border-helm-line text-helm-fg font-medium py-2.5 transition-colors hover:bg-helm-fg/5 disabled:opacity-60">
            {busy === "clean" ? "Setting up…" : "Start clean"}
          </button>
        </GlassCard>
      </div>
    </div>
  );
}
