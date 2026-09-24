import { useState } from "react";
import { toast } from "sonner";
import {
  Building2, Users, Target, ChevronRight, ChevronLeft, Check,
  Crown, Rocket, Handshake, Briefcase, Award,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { GlassCard } from "@/components/kit";
import { cn } from "@/lib/utils";
import {
  FOUNDER_ROLES, COMPANY_STAGES, INDUSTRIES, TEAM_SIZES, SETUP_STEPS,
} from "@/lib/companySetupCopy";
import TrenstonMark from "@/components/HelmMark";
import { CURRENCY_SYMBOLS } from "@/lib/money";

// New companies are Philippines-first; the backend stores php on new workspaces.
const DEFAULT_SETUP_CURRENCY = "php";

const ROLE_ICONS = {
  CEO: Crown,
  Founder: Rocket,
  "Co-founder": Handshake,
  "Managing Director": Briefcase,
  President: Award,
};

export default function CompanySetup({ company }) {
  const { user, setUser } = useAuth();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [hasTeamTouched, setHasTeamTouched] = useState(
    typeof company?.has_team === "boolean",
  );
  const [form, setForm] = useState({
    founder_title: company?.founder_title || "CEO",
    display_name: (user?.name || "").trim(),
    name: company?.name || "",
    industry: company?.industry || "",
    stage: COMPANY_STAGES.includes(company?.stage) ? company.stage : "",
    employees: company?.employees > 0 ? company.employees : null,
    has_team: typeof company?.has_team === "boolean"
      ? company.has_team
      : null,
    founded: /^\d{4}$/.test(company?.founded || "") ? company.founded : "",
    mission: company?.mission || "",
    currency: CURRENCY_SYMBOLS[company?.currency] ? company.currency : DEFAULT_SETUP_CURRENCY,
  });

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const setEmployees = (value) => {
    setForm((f) => ({
      ...f,
      employees: value,
      // Suggest Yes/No from headcount until the founder overrides explicitly.
      has_team: hasTeamTouched ? f.has_team : value > 1,
    }));
  };

  const setHasTeam = (value) => {
    setHasTeamTouched(true);
    set("has_team", value);
  };

  const teamSizeLabel = () => {
    const match = TEAM_SIZES.find((t) => t.value === form.employees);
    return match?.label || `${form.employees} people`;
  };

  const canNext = () => {
    if (step === 0) {
      if (!form.founder_title) return false;
      if (form.display_name.trim().length < 1) return false;
      return true;
    }
    if (step === 1) return form.name.trim().length >= 2 && form.industry && form.stage;
    if (step === 2) {
      return (
        !!form.employees
        && form.founded?.length === 4
        && typeof form.has_team === "boolean"
      );
    }
    return true;
  };

  const submit = async () => {
    if (!form.name.trim()) {
      toast.error("Company name is required");
      setStep(1);
      return;
    }
    if (typeof form.has_team !== "boolean") {
      toast.error("Tell us whether you have people you can hand work to");
      setStep(2);
      return;
    }
    setBusy(true);
    try {
      if (!user?.age_confirmed) {
        await api.patch("/account/age-confirmation", { confirmed: true });
      }
      // Always write the onboarding name to the same display-name field the rest of the app reads.
      const nextName = form.display_name.trim();
      if (nextName) {
        const { data: profile } = await api.patch("/account/profile", { name: nextName });
        if (setUser && profile?.name) {
          setUser((u) => (u ? { ...u, name: profile.name } : u));
        }
      }
      await api.patch("/company", {
        name: form.name.trim(),
        industry: form.industry,
        stage: form.stage,
        employees: form.employees,
        has_team: form.has_team,
        founded: form.founded,
        mission: form.mission.trim(),
        founder_title: form.founder_title,
        currency: form.currency,
        company_setup_done: true,
      });
      window.location.href = "/app";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save company profile");
      setBusy(false);
    }
  };

  const firstName = (form.display_name || user?.name || "").trim().split(" ")[0] || "there";

  return (
    <div className="min-h-screen grain flex flex-col">
      <div className="flex-1 flex flex-col items-center justify-center px-5 py-10 md:py-14">
        <div className="w-full max-w-2xl">
          {/* Header */}
          <div className="flex items-center gap-2.5 mb-8">
            <TrenstonMark size={36} className="rounded-md" />
            <div>
              <p className="text-helm-fg font-semibold tracking-tight leading-none">Trenston</p>
              <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-helm-muted mt-1">Set up your company</p>
            </div>
          </div>

          <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold">Welcome, {firstName}</p>
          <h1 className="font-display mt-3 text-3xl md:text-4xl font-normal tracking-tight text-helm-fg">
            Let's set up your company.
          </h1>
          <p className="mt-3 text-helm-muted text-sm leading-relaxed max-w-lg">
            A few details so Trenston can tailor your briefing, decisions, and AI to how you actually run the business.
          </p>

          {/* Progress */}
          <div className="mt-8 flex items-center gap-2">
            {SETUP_STEPS.map((s, i) => (
              <div key={s.id} className="flex-1 flex items-center gap-2">
                <div
                  className={cn(
                    "h-1 flex-1 rounded-full transition-colors",
                    i <= step ? "bg-helm-gold" : "bg-helm-fg/10",
                  )}
                />
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] font-mono uppercase tracking-wider text-helm-muted">
            Step {step + 1} of {SETUP_STEPS.length} · {SETUP_STEPS[step].label}
          </p>

          <GlassCard className="mt-6 p-6 md:p-8 fade-up" glow>
            {/* Step 0: Role */}
            {step === 0 && (
              <div>
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center">
                    <Crown className="w-5 h-5 text-helm-gold" />
                  </div>
                  <div>
                    <h2 className="text-lg text-helm-fg tracking-tight">What's your role?</h2>
                    <p className="text-xs text-helm-muted mt-0.5">Trenston is built for leaders who run the company.</p>
                  </div>
                </div>
                <label className="block text-xs text-helm-muted mb-5">
                  What should we call you?
                  <input
                    data-testid="setup-display-name"
                    value={form.display_name}
                    onChange={(e) => set("display_name", e.target.value)}
                    placeholder="Your first name"
                    className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/40"
                  />
                  {!needsDisplayName && (
                    <span className="mt-1 block text-[11px] text-helm-muted">
                      From your sign-in — edit if you prefer a different name in Trenston.
                    </span>
                  )}
                </label>
                <div className="grid gap-2">
                  {FOUNDER_ROLES.map((role) => {
                    const Icon = ROLE_ICONS[role.id] || Crown;
                    const on = form.founder_title === role.id;
                    return (
                      <button
                        key={role.id}
                        type="button"
                        data-testid={`role-${role.id}`}
                        onClick={() => set("founder_title", role.id)}
                        className={cn(
                          "flex items-start gap-3 rounded-lg border px-4 py-3.5 text-left transition-colors",
                          on
                            ? "border-helm-gold/35 bg-helm-gold/12"
                            : "border-helm-line bg-helm-fg/[0.02] hover:border-helm-fg/20",
                        )}
                      >
                        <Icon className={cn("w-4 h-4 shrink-0 mt-0.5", on ? "text-helm-gold" : "text-helm-muted")} />
                        <div className="min-w-0 flex-1">
                          <p className={cn("text-sm font-medium", on ? "text-helm-fg" : "text-helm-fg")}>{role.label}</p>
                          <p className="text-xs text-helm-muted mt-0.5">{role.hint}</p>
                        </div>
                        {on && <Check className="w-4 h-4 text-helm-gold shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Step 1: Company */}
            {step === 1 && (
              <div>
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center">
                    <Building2 className="w-5 h-5 text-helm-gold" />
                  </div>
                  <div>
                    <h2 className="text-lg text-helm-fg tracking-tight">About your company</h2>
                    <p className="text-xs text-helm-muted mt-0.5">Name, industry, and how established you are: the basics for your cockpit.</p>
                  </div>
                </div>
                <div className="space-y-5">
                  <label className="block text-xs text-helm-muted">
                    Company name
                    <input
                      data-testid="setup-company-name"
                      value={form.name}
                      onChange={(e) => set("name", e.target.value)}
                      placeholder="Acme Inc."
                      className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/40"
                    />
                  </label>
                  <div>
                    <p className="text-xs text-helm-muted mb-2">Industry</p>
                    <div className="flex flex-wrap gap-2">
                      {INDUSTRIES.map((ind) => (
                        <button
                          key={ind}
                          type="button"
                          data-testid={`industry-${ind}`}
                          onClick={() => set("industry", ind)}
                          className={cn(
                            "rounded-full px-3 py-1.5 text-xs transition-colors border",
                            form.industry === ind
                              ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
                              : "border-helm-line text-helm-muted hover:border-helm-fg/20 hover:text-helm-fg",
                          )}
                        >
                          {ind}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-helm-muted mb-2">Company maturity</p>
                    <div className="flex flex-wrap gap-2">
                      {COMPANY_STAGES.map((st) => (
                        <button
                          key={st}
                          type="button"
                          data-testid={`stage-${st}`}
                          onClick={() => set("stage", st)}
                          className={cn(
                            "rounded-full px-3 py-1.5 text-xs transition-colors border",
                            form.stage === st
                              ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
                              : "border-helm-line text-helm-muted hover:border-helm-fg/20 hover:text-helm-fg",
                          )}
                        >
                          {st}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-helm-muted mb-2">Reporting currency</p>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(CURRENCY_SYMBOLS).map(([code, symbol]) => (
                        <button
                          key={code}
                          type="button"
                          data-testid={`currency-${code}`}
                          onClick={() => set("currency", code)}
                          className={cn(
                            "rounded-full px-3 py-1.5 text-xs transition-colors border font-mono",
                            form.currency === code
                              ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
                              : "border-helm-line text-helm-muted hover:border-helm-fg/20 hover:text-helm-fg",
                          )}
                        >
                          {code.toUpperCase()} ({symbol})
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Step 2: Team */}
            {step === 2 && (
              <div>
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center">
                    <Users className="w-5 h-5 text-helm-gold" />
                  </div>
                  <div>
                    <h2 className="text-lg text-helm-fg tracking-tight">Team & context</h2>
                    <p className="text-xs text-helm-muted mt-0.5">Trenston calibrates runway views and planning defaults to your size.</p>
                  </div>
                </div>
                <div className="space-y-5">
                  <div>
                    <p className="text-xs text-helm-muted mb-2">Team size</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {TEAM_SIZES.map((t) => (
                        <button
                          key={t.label}
                          type="button"
                          data-testid={`team-${t.label}`}
                          onClick={() => setEmployees(t.value)}
                          className={cn(
                            "rounded-lg border px-3 py-2.5 text-sm transition-colors",
                            form.employees === t.value
                              ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
                              : "border-helm-line text-helm-muted hover:border-helm-fg/20",
                          )}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-helm-muted mb-1">Do you have a team you can delegate to?</p>
                    <p className="text-[11px] text-helm-muted mb-2 leading-relaxed">
                      Hires, contractors, or co-founders who actually act on things — not just company headcount.
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { label: "Yes", value: true, testId: "has-team-yes" },
                        { label: "No", value: false, testId: "has-team-no" },
                      ].map((opt) => (
                        <button
                          key={opt.label}
                          type="button"
                          data-testid={opt.testId}
                          onClick={() => setHasTeam(opt.value)}
                          className={cn(
                            "rounded-lg border px-3 py-2.5 text-sm transition-colors",
                            form.has_team === opt.value
                              ? "border-helm-gold/35 bg-helm-gold/12 text-helm-gold"
                              : "border-helm-line text-helm-muted hover:border-helm-fg/20",
                          )}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <label className="block text-xs text-helm-muted">
                    Founded
                    <input
                      data-testid="setup-founded"
                      value={form.founded}
                      onChange={(e) => set("founded", e.target.value.replace(/\D/g, "").slice(0, 4))}
                      placeholder="1998"
                      className="mt-1 w-32 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 font-mono focus:outline-none focus:border-helm-gold/40"
                    />
                  </label>
                  <label className="block text-xs text-helm-muted">
                    Mission <span className="text-helm-muted">(optional)</span>
                    <textarea
                      data-testid="setup-mission"
                      value={form.mission}
                      onChange={(e) => set("mission", e.target.value)}
                      placeholder="What does your company do in one line?"
                      rows={2}
                      className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2.5 resize-none focus:outline-none focus:border-helm-gold/40"
                    />
                  </label>
                </div>
              </div>
            )}

            {/* Step 3: Review */}
            {step === 3 && (
              <div>
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center">
                    <Target className="w-5 h-5 text-helm-gold" />
                  </div>
                  <div>
                    <h2 className="text-lg text-helm-fg tracking-tight">Ready to go</h2>
                    <p className="text-xs text-helm-muted mt-0.5">Review your profile, then we'll set up your cockpit.</p>
                  </div>
                </div>
                <dl className="space-y-3 text-sm">
                  {[
                    ["Your name", form.display_name || user?.name || "—"],
                    ["Your role", form.founder_title],
                    ["Company", form.name],
                    ["Industry", form.industry],
                    ["Maturity", form.stage],
                    ["Team size", teamSizeLabel()],
                    ["Can delegate", form.has_team ? "Yes — I have people I can hand work to" : "No — just me for now"],
                    ["Founded", form.founded],
                    ...(form.mission ? [["Mission", form.mission]] : []),
                  ].map(([label, value]) => (
                    <div key={label} className="flex gap-4 py-2 border-b border-helm-fg/[0.04] last:border-0">
                      <dt className="w-28 shrink-0 text-helm-muted text-xs font-mono uppercase tracking-wider pt-0.5">{label}</dt>
                      <dd className="text-helm-fg">{value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-5 text-xs text-helm-muted leading-relaxed">
                  Next you'll choose whether to explore with sample data or start clean, then activate Trenston when you're ready.
                </p>
              </div>
            )}

            {/* Navigation */}
            <div className="flex gap-2 mt-8 pt-6 border-t border-helm-line">
              {step > 0 ? (
                <button
                  type="button"
                  onClick={() => setStep((s) => s - 1)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:bg-helm-fg/5 transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" /> Back
                </button>
              ) : (
                <div />
              )}
              {step < SETUP_STEPS.length - 1 ? (
                <button
                  type="button"
                  data-testid="setup-next-btn"
                  onClick={() => canNext() && setStep((s) => s + 1)}
                  disabled={!canNext()}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover transition-colors disabled:opacity-40"
                >
                  Continue <ChevronRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  type="button"
                  data-testid="setup-finish-btn"
                  onClick={submit}
                  disabled={busy}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover transition-colors disabled:opacity-60"
                >
                  {busy ? "Saving…" : "Set up my cockpit"}
                </button>
              )}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
