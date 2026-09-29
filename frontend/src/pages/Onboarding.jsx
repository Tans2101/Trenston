import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import { ErrorScreen, SkeletonCardList } from "@/components/kit";
import { useDepartmentsQuery } from "@/hooks/useDepartmentsQuery";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { DEPARTMENTS_SECTION } from "@/lib/marketingCopy";
import { cn } from "@/lib/utils";

/** Auto-enabled on every workspace; shown as included, not removable in this step. */
const LOCKED_TYPES = new Set(["sales", "accounting_finance"]);

const DEPT_BLURB = Object.fromEntries(
  DEPARTMENTS_SECTION.items.map((d) => [d.name, d.body]),
);

function StepHeader({ step, title, body }) {
  return (
    <div>
      <p className="text-xs text-helm-muted">Step {step} of 3</p>
      <h1 className="font-display mt-2 text-3xl font-normal tracking-tight text-helm-fg">{title}</h1>
      <p className="mt-2 max-w-xl text-sm text-helm-muted leading-relaxed">{body}</p>
    </div>
  );
}

function Box({ checked }) {
  return (
    <span
      className={cn(
        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] border",
        checked ? "border-helm-fg bg-helm-fg text-helm-bg" : "border-helm-line",
      )}
      aria-hidden
    >
      {checked ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
    </span>
  );
}

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
      // Only POST newly chosen optional types; Sales/Finance are already on.
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
      toast.error(e?.response?.data?.detail || "Something went wrong. Please try again.");
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl py-8">
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
      <div className="max-w-3xl py-8" data-testid="onboarding-departments-step">
        <StepHeader
          step={2}
          title="Departments"
          body="Sales and Accounting & Finance are always on. Add the others your company runs today. You can turn any department on or off later in Settings."
        />

        <ul className="mt-10 border-t border-helm-line" data-testid="onboarding-department-catalog">
          {lockedDepts.map((dept) => (
            <li
              key={dept.type}
              className="flex items-start gap-4 border-b border-helm-line py-4"
              data-testid={`onboarding-dept-locked-${dept.type}`}
            >
              <Box checked />
              <div className="min-w-0 flex-1">
                <p className="text-sm text-helm-fg">{dept.name}</p>
                {DEPT_BLURB[dept.name] && (
                  <p className="mt-0.5 text-xs text-helm-muted leading-relaxed">{DEPT_BLURB[dept.name]}</p>
                )}
              </div>
              <span className="shrink-0 text-xs text-helm-muted">Included</span>
            </li>
          ))}

          {optionalDepts.map((dept) => {
            const checked = selected.has(dept.type);
            return (
              <li key={dept.type} className="border-b border-helm-line">
                <button
                  type="button"
                  data-testid={`onboarding-dept-toggle-${dept.type}`}
                  aria-pressed={checked}
                  onClick={() => toggleOptional(dept.type)}
                  className="flex w-full items-start gap-4 py-4 text-left transition-colors hover:bg-helm-fg/[0.02]"
                >
                  <Box checked={checked} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-helm-fg">{dept.name}</p>
                    {DEPT_BLURB[dept.name] && (
                      <p className="mt-0.5 text-xs text-helm-muted leading-relaxed">{DEPT_BLURB[dept.name]}</p>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>

        <div className="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-helm-muted">
            {selected.size === 0
              ? "No extra departments selected."
              : `${selected.size} extra department${selected.size === 1 ? "" : "s"} selected.`}
          </p>
          <button
            type="button"
            data-testid="onboarding-departments-continue"
            onClick={confirmDepartments}
            disabled={!!busy}
            className="rounded-md bg-helm-gold px-5 py-2.5 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold-hover disabled:opacity-50"
          >
            {busy === "departments" ? "Saving…" : "Continue"}
          </button>
        </div>
      </div>
    );
  }

  const options = [
    {
      id: "clean",
      testId: "onboarding-clean-btn",
      title: "Start with my own data",
      body: hasTeam
        ? "An empty workspace. Log your financials, invite your team and connect Google or your accounting system. The Briefing fills in as real numbers arrive."
        : "An empty workspace. Log your financials and connect Google or your accounting system. The Briefing fills in as real numbers arrive.",
      cta: "Start with my own data",
      busyLabel: "Setting up…",
      primary: true,
    },
    {
      id: "sample",
      testId: "onboarding-sample-btn",
      title: "Look around with sample data first",
      body: "Loads an example B2B software company with six months of financials, open decisions, tasks and a team, so you can see how each page works. You can remove it in one click from the Briefing.",
      cta: "Load sample company",
      busyLabel: "Loading…",
      primary: false,
    },
  ];

  return (
    <div className="max-w-3xl py-8" data-testid="onboarding-template-step">
      <StepHeader
        step={3}
        title="How do you want to start?"
        body="If you load the sample company, you can remove it later from the Briefing and start fresh."
      />

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
              onClick={() => choose(o.id)}
              disabled={!!busy}
              className={cn(
                "whitespace-nowrap rounded-md px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50",
                o.primary
                  ? "bg-helm-gold text-helm-navy hover:bg-helm-gold-hover"
                  : "border border-helm-line text-helm-fg hover:bg-helm-fg/[0.04]",
              )}
            >
              {busy === o.id ? o.busyLabel : o.cta}
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setStep("departments")}
        disabled={!!busy}
        className="mt-6 text-xs text-helm-muted underline-offset-2 hover:text-helm-fg hover:underline disabled:opacity-50"
      >
        Back to departments
      </button>
    </div>
  );
}
