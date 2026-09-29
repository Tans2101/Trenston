import { useState } from "react";
import { toast } from "sonner";
import { ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import {
  FOUNDER_ROLES, COMPANY_STAGES, INDUSTRIES, TEAM_SIZES,
} from "@/lib/companySetupCopy";
import TrenstonMark from "@/components/HelmMark";
import { CURRENCY_SYMBOLS } from "@/lib/money";

// New companies are Philippines-first; the backend stores php on new workspaces.
const DEFAULT_SETUP_CURRENCY = "php";

const INPUT =
  "w-full rounded-md border border-helm-line bg-helm-bg text-helm-fg text-sm px-3 py-2.5 focus:outline-none focus:border-helm-gold/50";

function Field({ label, hint, optional, children, htmlFor }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm text-helm-fg">
        {label}
        {optional && <span className="ml-1.5 text-helm-muted">(optional)</span>}
      </label>
      {hint && <p className="mt-0.5 text-xs text-helm-muted leading-relaxed">{hint}</p>}
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Select({ id, value, onChange, placeholder, options, testId }) {
  return (
    <div className="relative">
      <select
        id={id}
        data-testid={testId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(INPUT, "appearance-none pr-9", !value && "text-helm-muted")}
      >
        {placeholder && <option value="" disabled>{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-helm-muted" />
    </div>
  );
}

function Segmented({ options, value, onChange, testIdPrefix }) {
  return (
    <div className="inline-flex flex-wrap rounded-md border border-helm-line overflow-hidden">
      {options.map((o, i) => {
        const on = value === o.value;
        return (
          <button
            key={o.label}
            type="button"
            data-testid={`${testIdPrefix}-${o.testId || o.label}`}
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={cn(
              "px-3.5 py-2 text-sm transition-colors",
              i > 0 && "border-l border-helm-line",
              on ? "bg-helm-gold text-helm-navy" : "text-helm-muted hover:text-helm-fg hover:bg-helm-fg/[0.04]",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="grid gap-6 border-t border-helm-line py-8 md:grid-cols-[180px_1fr] md:gap-10">
      <h2 className="text-xs font-medium uppercase tracking-[0.14em] text-helm-muted pt-0.5">{title}</h2>
      <div className="space-y-6">{children}</div>
    </section>
  );
}

export default function CompanySetup({ company }) {
  const { user, setUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const [hasTeamTouched, setHasTeamTouched] = useState(
    typeof company?.has_team === "boolean",
  );
  const [form, setForm] = useState({
    founder_title: company?.founder_title || "Founder",
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

  const missing = [];
  if (form.display_name.trim().length < 1) missing.push("your name");
  if (form.name.trim().length < 2) missing.push("company name");
  if (!form.industry) missing.push("industry");
  if (!form.stage) missing.push("stage");
  if (!form.employees) missing.push("team size");
  if (typeof form.has_team !== "boolean") missing.push("whether you can delegate");
  // Founded is optional (backend accepts blank); only reject a partial year.
  const foundedInvalid = !!form.founded && form.founded.length !== 4;
  const canSubmit = missing.length === 0 && !foundedInvalid && !busy;

  const submit = async (e) => {
    e?.preventDefault();
    if (!canSubmit) return;
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
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save company profile");
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-helm-bg">
      <header className="border-b border-helm-line">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-2.5">
            <TrenstonMark size={28} className="rounded-md" />
            <span className="text-sm font-semibold tracking-tight text-helm-fg">Trenston</span>
          </div>
          <span className="text-xs text-helm-muted">Step 1 of 3</span>
        </div>
      </header>

      <form onSubmit={submit} className="mx-auto max-w-3xl px-5 pt-12 pb-20" data-testid="company-setup-form">
        <h1 className="font-display text-3xl font-normal tracking-tight text-helm-fg">Company details</h1>
        <p className="mt-2 max-w-xl text-sm text-helm-muted leading-relaxed">
          Trenston uses these to set currency, runway views and delegation defaults. You can change any of them later in Settings.
        </p>

        <div className="mt-10">
          <Section title="You">
            <div className="grid gap-6 sm:grid-cols-2">
              <Field label="Your name" htmlFor="setup-display-name">
                <input
                  id="setup-display-name"
                  data-testid="setup-display-name"
                  value={form.display_name}
                  onChange={(e) => set("display_name", e.target.value)}
                  placeholder="First name"
                  className={INPUT}
                />
              </Field>
              <Field label="Title" htmlFor="setup-title">
                <Select
                  id="setup-title"
                  testId="setup-title"
                  value={form.founder_title}
                  onChange={(v) => set("founder_title", v)}
                  options={FOUNDER_ROLES.map((r) => ({ value: r.id, label: r.label }))}
                />
              </Field>
            </div>
          </Section>

          <Section title="Company">
            <Field label="Company name" htmlFor="setup-company-name">
              <input
                id="setup-company-name"
                data-testid="setup-company-name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="Acme Inc."
                className={INPUT}
              />
            </Field>
            <div className="grid gap-6 sm:grid-cols-2">
              <Field label="Industry" htmlFor="setup-industry">
                <Select
                  id="setup-industry"
                  testId="setup-industry"
                  value={form.industry}
                  onChange={(v) => set("industry", v)}
                  placeholder="Select an industry"
                  options={INDUSTRIES.map((i) => ({ value: i, label: i }))}
                />
              </Field>
              <Field label="Stage" htmlFor="setup-stage">
                <Select
                  id="setup-stage"
                  testId="setup-stage"
                  value={form.stage}
                  onChange={(v) => set("stage", v)}
                  placeholder="Select a stage"
                  options={COMPANY_STAGES.map((s) => ({ value: s, label: s }))}
                />
              </Field>
            </div>
            <div className="grid gap-6 sm:grid-cols-2">
              <Field label="Reporting currency" htmlFor="setup-currency">
                <Select
                  id="setup-currency"
                  testId="setup-currency"
                  value={form.currency}
                  onChange={(v) => set("currency", v)}
                  options={Object.entries(CURRENCY_SYMBOLS).map(([code, symbol]) => ({
                    value: code,
                    label: `${code.toUpperCase()} (${symbol})`,
                  }))}
                />
              </Field>
              <Field label="Year founded" optional htmlFor="setup-founded">
                <input
                  id="setup-founded"
                  data-testid="setup-founded"
                  inputMode="numeric"
                  value={form.founded}
                  onChange={(e) => set("founded", e.target.value.replace(/\D/g, "").slice(0, 4))}
                  placeholder="2024"
                  className={cn(INPUT, "font-mono")}
                />
              </Field>
            </div>
            <Field label="What the company does" optional htmlFor="setup-mission">
              <input
                id="setup-mission"
                data-testid="setup-mission"
                value={form.mission}
                onChange={(e) => set("mission", e.target.value)}
                placeholder="One line, e.g. Contract manufacturer of packaging for food brands"
                className={INPUT}
              />
            </Field>
          </Section>

          <Section title="Team">
            <Field label="Team size">
              <Segmented
                testIdPrefix="team"
                options={TEAM_SIZES}
                value={form.employees}
                onChange={setEmployees}
              />
            </Field>
            <Field
              label="Do you have people you can hand work to?"
              hint="Hires, contractors or co-founders who act on things. This decides whether Trenston suggests delegating."
            >
              <Segmented
                testIdPrefix="has-team"
                options={[
                  { label: "Yes", value: true, testId: "yes" },
                  { label: "Not yet", value: false, testId: "no" },
                ]}
                value={form.has_team}
                onChange={setHasTeam}
              />
            </Field>
          </Section>
        </div>

        <div className="flex flex-col-reverse gap-3 border-t border-helm-line pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-helm-muted" data-testid="setup-missing">
            {foundedInvalid
              ? "Enter a four-digit year, or leave it blank."
              : missing.length
                ? `Still needed: ${missing.join(", ")}.`
                : "Next: choose departments."}
          </p>
          <button
            type="submit"
            data-testid="setup-finish-btn"
            disabled={!canSubmit}
            className="rounded-md bg-helm-gold px-5 py-2.5 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold-hover disabled:opacity-40"
          >
            {busy ? "Saving…" : "Continue"}
          </button>
        </div>
      </form>
    </div>
  );
}
