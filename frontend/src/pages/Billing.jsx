import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { Check, ArrowLeft, ShieldCheck, ExternalLink, AlertTriangle } from "lucide-react";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { initPaddle } from "@/lib/paddle";
import { PLANS } from "@/lib/marketingCopy";
import { normalizePlan } from "@/lib/helmPlan";
import { GlassCard, SectionLabel, ErrorScreen, PageHeaderSkeleton, SkeletonCardList } from "@/components/kit";
import { RingChart } from "@/components/charts/ring-chart";
import { Ring } from "@/components/charts/ring";
import { RingCenter } from "@/components/charts/ring-center";
import { cn } from "@/lib/utils";
import palette from "@/design/palette.json";

const PLAN_RANK = { free: 0, starter: 1, growth: 2, business: 3 };

/** Poll until webhook has applied the purchased plan (or give up cleanly). */
async function waitForBillingPlan(targetPlan, { maxAttempts = 20, intervalMs = 1500 } = {}) {
  const target = normalizePlan(targetPlan);
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const { data: status } = await api.get("/billing/status");
      if (normalizePlan(status?.current_plan) === target) return true;
    } catch {
      /* webhook may still be in flight */
    }
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }
  return false;
}

function usageToneColor(used, limit) {
  if (!(limit > 0)) return palette.gold;
  if (used > limit) return palette.statusNegative;
  if (used >= limit || used / limit >= 0.8) return palette.statusWarning;
  return palette.gold;
}

function UsageRing({ label, used, limit, unit, testId }) {
  const safeLimit = Math.max(Number(limit) || 0, 1);
  const safeUsed = Math.max(0, Number(used) || 0);
  const over = Number(limit) > 0 && safeUsed > Number(limit);
  const atLimit = Number(limit) > 0 && safeUsed === Number(limit);
  // Ring stays full when over — do not let the chart overflow past 100%.
  const ringValue = Math.min(safeUsed, safeLimit);
  const color = usageToneColor(safeUsed, Number(limit));
  const unitLabel = unit || label.toLowerCase();
  const caption = over
    ? `${safeUsed} / ${limit} ${unitLabel} (over limit)`
    : `${safeUsed} / ${limit} ${unitLabel}`;
  const data = [{ label, value: ringValue, maxValue: safeLimit, color }];
  return (
    <div className="flex flex-col items-center gap-1.5" data-testid={testId}>
      <RingChart
        data={data}
        size={88}
        strokeWidth={9}
        ringGap={0}
        baseInnerRadius={28}
        className="text-helm-fg"
      >
        <Ring index={0} showGlow={false} animate />
        <RingCenter defaultLabel={label} />
      </RingChart>
      <p
        className={cn(
          "text-xs font-mono text-center max-w-[9.5rem] leading-snug",
          over ? "text-helm-status-negative" : atLimit ? "text-helm-status-warning" : "text-helm-muted",
        )}
        data-testid={`${testId}-caption`}
      >
        {caption}
      </p>
    </div>
  );
}

export default function Billing() {
  const { data, loading, error, reload } = useFetch("/billing/plans");
  const [busy, setBusy] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const notice = location.state?.billingNotice;
    if (!notice) return;
    toast.message(String(notice));
    navigate(location.pathname, { replace: true, state: {} });
  }, [location.state, location.pathname, navigate]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto">
        <PageHeaderSkeleton />
        <SkeletonCardList count={1} className="mb-8" />
        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <SkeletonCardList count={1} />
          <SkeletonCardList count={1} />
          <SkeletonCardList count={1} />
          <SkeletonCardList count={1} />
        </div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load billing"
        message={fetchErrorMessage(error, "Billing data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  const billingEnforced = data.billing_enforced === true;
  const currentPlan = normalizePlan(data.current_plan);
  const pendingPlan = data.pending_plan ? normalizePlan(data.pending_plan) : null;
  const plans = (data.plans?.length ? data.plans : PLANS).map((p) => ({
    ...p,
    includes: p.includes || PLANS.find((x) => x.id === p.id)?.includes || [],
    for: p.for || PLANS.find((x) => x.id === p.id)?.for,
    trial_days: p.trial_days ?? p.trialDays ?? 0,
    seats: p.seats ?? PLANS.find((x) => x.id === p.id)?.seats,
    ai_extracts_mo: p.ai_extracts_mo ?? PLANS.find((x) => x.id === p.id)?.ai_extracts_mo,
  }));
  const pastDue = billingEnforced && data.subscription_status === "past_due";
  const trialing = data.subscription_status === "trialing";
  const extractsUsed = data.ai_extracts_used ?? 0;
  const extractsLimit = data.ai_extracts_limit ?? 0;
  const askUsed = data.ask_helm_used ?? 0;
  const askLimit = data.ask_helm_limit ?? data.ask_helm_mo ?? 0;
  const seatsUsed = data.seats_used ?? 0;
  const seatsLimit = data.seats_limit;
  const seatsOver = seatsLimit > 0 && seatsUsed > seatsLimit;
  const extractsOver = extractsLimit > 0 && extractsUsed > extractsLimit;
  const askOver = askLimit > 0 && askUsed > askLimit;
  const askAtLimit = askLimit > 0 && askUsed >= askLimit;
  const periodEndLabel = data.usage_period_end
    ? new Date(data.usage_period_end).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    : null;

  const activatePaddle = async (planId) => {
    if (planId === "free") return;
    const tier = plans.find((p) => p.id === planId);
    if (tier && tier.checkout_available === false) {
      toast.error(`${tier.label} checkout isn’t set up yet. Add PADDLE_PRICE_ID_${planId.toUpperCase()} on Render`);
      return;
    }
    setBusy(planId);
    try {
      const { data: cfg } = await api.post("/billing/paddle/config", { plan: planId });
      const Paddle = await initPaddle(
        cfg.client_token,
        cfg.environment,
        (ev) => {
        if (ev?.name !== "checkout.completed") return;
        toast.success("Payment received. Activating your plan…");
        setBusy(planId);
        void (async () => {
          const activated = await waitForBillingPlan(cfg.plan || planId);
          if (activated) {
            toast.success("Plan activated");
            window.location.reload();
            return;
          }
          setBusy(null);
          toast.message("Payment received — this can take a minute to reflect. Refresh shortly.");
          reload();
        })();
      },
        cfg.paddle_customer_id,
      );
      Paddle.Checkout.open({
        settings: { displayMode: "overlay", theme: "dark" },
        items: [{ priceId: cfg.price_id, quantity: 1 }],
        customData: {
          workspace_id: cfg.workspace_id,
          user_id: cfg.user_id,
          checkout_nonce: cfg.checkout_nonce,
          plan: cfg.plan,
        },
        ...(cfg.email ? { customer: { email: cfg.email } } : {}),
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start Paddle checkout");
    } finally {
      setBusy(null);
    }
  };

  const scheduleDowngrade = async (planId) => {
    setBusy(`down-${planId}`);
    try {
      const { data: res } = await api.post("/billing/schedule-plan", { plan: planId });
      toast.success(res.message || "Downgrade scheduled for end of billing period");
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not schedule downgrade");
    } finally {
      setBusy(null);
    }
  };

  const openPortal = async () => {
    setBusy("portal");
    try {
      const { data: res } = await api.post("/payments/paddle/portal");
      if (res?.url) window.location.href = res.url;
      else toast.error("Could not open billing portal");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not open billing portal");
    } finally {
      setBusy(null);
    }
  };

  const resetDemo = async () => {
    try {
      await api.post("/demo/reset-plan");
      toast.success("Reverted to Free (demo)");
      setTimeout(() => window.location.reload(), 600);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Demo reset is disabled");
    }
  };

  const planAction = (plan) => {
    const isCurrent = currentPlan === plan.id;
    const isPaid = plan.id !== "free";
    const rank = PLAN_RANK[plan.id] ?? 0;
    const currentRank = PLAN_RANK[currentPlan] ?? 0;

    if (isCurrent) {
      return (
        <div className="text-center text-xs font-mono uppercase tracking-wide text-helm-gold border border-helm-gold/35 bg-helm-gold/12 rounded-md py-2.5">
          {isPaid ? "Current plan" : "On Free"}
        </div>
      );
    }
    if (pendingPlan === plan.id) {
      return (
        <div className="text-center text-[11px] text-helm-muted border border-helm-line rounded-md py-2.5 px-2">
          Scheduled. Takes effect next billing period
        </div>
      );
    }
    if (rank > currentRank) {
      return (
        <button
          type="button"
          data-testid={`upgrade-${plan.id}`}
          onClick={() => activatePaddle(plan.id)}
          disabled={!!busy || plan.checkout_available === false}
          className="w-full bg-helm-gold text-helm-navy font-medium rounded-md py-2.5 text-sm transition-colors hover:bg-helm-gold-hover disabled:opacity-60"
        >
          {busy === plan.id
            ? "Starting…"
            : plan.checkout_available === false
              ? "Coming soon"
              : currentPlan === "free"
                ? `Start ${plan.trial_days || 7}-day trial`
                : `Upgrade to ${plan.label}`}
        </button>
      );
    }
    // Downgrade (including to Free)
    return (
      <button
        type="button"
        data-testid={`downgrade-${plan.id}`}
        onClick={() => scheduleDowngrade(plan.id)}
        disabled={!!busy}
        className="w-full border border-helm-line text-helm-fg font-medium rounded-md py-2.5 text-sm hover:bg-helm-fg/5 disabled:opacity-60"
      >
        {busy === `down-${plan.id}` ? "Scheduling…" : `Downgrade at period end`}
      </button>
    );
  };

  return (
    <div className="max-w-5xl mx-auto">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-helm-muted hover:text-helm-fg mb-6 transition-colors" data-testid="billing-back">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      {pastDue && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-helm-status-warning/35 bg-helm-status-warning/12 px-4 py-3 text-sm text-helm-fg" data-testid="past-due-banner">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-helm-status-warning">Payment past due</p>
            <p className="text-helm-status-warning/80 mt-0.5">Update your payment method to keep paid features.</p>
            {data.portal_available && (
              <button onClick={openPortal} disabled={!!busy} className="mt-2 text-xs font-medium text-helm-status-warning underline hover:no-underline">
                Manage billing
              </button>
            )}
          </div>
        </div>
      )}

      {trialing && (
        <div className="mb-6 rounded-lg border border-helm-gold/35 bg-helm-gold/12 px-4 py-3 text-sm text-helm-gold" data-testid="trialing-banner">
          You’re on a free trial. Cancel anytime before it ends to avoid being charged.
        </div>
      )}

      {pendingPlan && (
        <div className="mb-6 rounded-lg border border-helm-line bg-helm-fg/[0.03] px-4 py-3 text-sm text-helm-fg" data-testid="pending-downgrade-banner">
          Downgrade to <span className="text-helm-fg">{pendingPlan}</span> is scheduled
          {data.pending_plan_effective_at
            ? ` for ${new Date(data.pending_plan_effective_at).toLocaleDateString()}`
            : " for the end of this billing period"}
          . No refund for the remaining period.
        </div>
      )}

      {!billingEnforced && (
        <div className="mb-6 rounded-lg border border-helm-status-positive/35 bg-helm-status-positive/12 px-4 py-3 text-sm text-helm-fg" data-testid="billing-standby-banner">
          <p className="font-medium text-helm-status-positive">Billing is paused</p>
          <p className="text-helm-status-positive/80 mt-0.5">
            Feature gates are open while you build. Set <code className="font-mono text-xs">BILLING_ENFORCED=true</code> when ready.
            Configure <code className="font-mono text-xs">PADDLE_PRICE_ID_STARTER</code>, <code className="font-mono text-xs">PADDLE_PRICE_ID_GROWTH</code>, and <code className="font-mono text-xs">PADDLE_PRICE_ID_BUSINESS</code>.
          </p>
        </div>
      )}

      <div className="text-center mb-8 fade-up">
        <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold mb-3">Pricing</p>
        <h1 className="font-display text-3xl md:text-4xl font-normal tracking-tight text-helm-fg">Choose your Trenston plan</h1>
        <p className="text-helm-muted mt-3">
          Paid plans include a <span className="text-helm-fg">7-day free trial</span>. Downgrades take effect next billing cycle.
        </p>
      </div>

      {/* Usage indicator */}
      <GlassCard className="p-4 mb-8 fade-up" data-testid="usage-indicator">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <SectionLabel>
              {data.ai_extracts_kind === "lifetime" ? "Free AI extracts (one-time)" : "Usage this billing period"}
            </SectionLabel>
            <p className={cn("text-sm mt-1", extractsOver || askOver ? "text-helm-status-negative" : "text-helm-muted")}>
              {data.ai_extracts_kind === "lifetime"
                ? extractsOver
                  ? `${extractsUsed} / ${extractsLimit} free AI extracts (over limit)`
                  : `${extractsUsed} of ${extractsLimit} free AI extracts used, then upgrade to continue`
                : extractsLimit > 0
                  ? extractsOver
                    ? `${extractsUsed} / ${extractsLimit} document uploads (over limit)`
                    : `${extractsUsed} of ${extractsLimit} document uploads used`
                  : currentPlan === "free"
                    ? "5 AI document extracts to try it, then upgrade"
                    : "No document upload quota on this plan"}
              {askLimit > 0 && (
                <span className="block mt-1" data-testid="ask-helm-usage-copy">
                  {askOver || askAtLimit
                    ? `Ask Trenston ${askUsed} / ${askLimit} messages${periodEndLabel ? ` — resets ${periodEndLabel}` : ""}`
                    : `Ask Trenston ${askUsed} of ${askLimit} messages used${periodEndLabel ? ` (resets ${periodEndLabel})` : ""}`}
                </span>
              )}
            </p>
          </div>
          <p
            className={cn(
              "text-xs font-mono",
              seatsOver ? "text-helm-status-negative" : "text-helm-muted",
            )}
          >
            {seatsOver
              ? `Seats ${seatsUsed} / ${seatsLimit} (over limit)`
              : `Seats ${seatsUsed}/${seatsLimit ?? "—"}`}
          </p>
        </div>
        {(seatsLimit > 0 || extractsLimit > 0 || askLimit > 0) && (
          <div className="flex flex-wrap items-center gap-6 pt-1" data-testid="usage-rings">
            {seatsLimit > 0 && (
              <UsageRing
                label="Seats"
                unit="seats"
                used={seatsUsed}
                limit={seatsLimit}
                testId="seats-usage-ring"
              />
            )}
            {extractsLimit > 0 && (
              <UsageRing
                label="Extracts"
                unit="extracts"
                used={extractsUsed}
                limit={extractsLimit}
                testId="usage-bar"
              />
            )}
            {askLimit > 0 && (
              <UsageRing
                label="Ask Trenston"
                unit="messages"
                used={askUsed}
                limit={askLimit}
                testId="ask-helm-usage-ring"
              />
            )}
          </div>
        )}
      </GlassCard>

      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
        {plans.map((plan) => {
          const isCurrent = currentPlan === plan.id;
          const highlighted = plan.id === "starter" || plan.highlighted;
          const price = plan.price ?? 0;
          return (
            <GlassCard
              key={plan.id}
              glow={highlighted && !isCurrent}
              className={cn(
                "p-5 fade-up flex flex-col",
                isCurrent && "border-helm-gold/35",
                highlighted && !isCurrent && "border-helm-gold/35",
              )}
              data-testid={`plan-card-${plan.id}`}
            >
              <div className="flex items-center justify-between gap-2">
                <SectionLabel>{plan.label}</SectionLabel>
                {isCurrent && (
                  <span className="text-[10px] font-mono uppercase tracking-wide text-helm-gold bg-helm-gold/12 border border-helm-gold/35 rounded px-1.5 py-0.5">
                    Current
                  </span>
                )}
              </div>
              <p className="font-mono text-3xl text-helm-fg mt-3">
                {price === 0 ? "$0" : `$${price}`}
                <span className="text-sm text-helm-muted">{price === 0 ? "" : "/mo"}</span>
              </p>
              <p className="text-xs text-helm-muted mt-1 min-h-[2.5rem]">{plan.for}</p>
              {plan.id !== "free" && (plan.trial_days || 7) > 0 && (
                <p className="text-[11px] text-helm-gold/80 font-mono mt-1">{plan.trial_days || 7}-day free trial</p>
              )}
              <ul className="mt-4 space-y-2 flex-1">
                {(plan.includes || []).map((f) => (
                  <li key={f} className="flex items-start gap-2 text-xs text-helm-fg">
                    <Check className="w-3.5 h-3.5 text-helm-gold shrink-0 mt-0.5" /> {f}
                  </li>
                ))}
              </ul>
              <div className="mt-5">{planAction(plan)}</div>
            </GlassCard>
          );
        })}
      </div>

      {data.portal_available && currentPlan !== "free" && (
        <button
          data-testid="manage-billing-btn"
          onClick={openPortal}
          disabled={!!busy}
          className="w-full max-w-md mx-auto flex items-center justify-center gap-2 border border-helm-line text-helm-fg rounded-md py-2.5 text-sm hover:bg-helm-fg/5 transition-colors disabled:opacity-60 mb-4"
        >
          <ExternalLink className="w-4 h-4" /> Manage billing in Paddle
        </button>
      )}

      {data.demo_reset_enabled && currentPlan !== "free" && (
        <button onClick={resetDemo} data-testid="reset-demo-btn" className="w-full max-w-md mx-auto block border border-helm-line text-helm-muted rounded-md py-2.5 text-sm hover:bg-helm-fg/5 transition-colors mb-4">
          Revert to Free (demo)
        </button>
      )}

      <p className="text-center text-[11px] text-helm-muted mt-6 leading-relaxed max-w-xl mx-auto">
        Payments by Paddle (Merchant of Record). Upgrades via checkout; downgrades take effect at period end (no mid-cycle refunds).{" "}
        <Link to="/terms" className="text-helm-muted hover:text-helm-fg transition-colors">Terms</Link>
        {" · "}
        <Link to="/privacy" className="text-helm-muted hover:text-helm-fg transition-colors">Privacy</Link>
        {" · "}
        <Link to="/security" className="text-helm-muted hover:text-helm-fg transition-colors">Security</Link>
        {" · "}
        <Link to="/refunds" className="text-helm-muted hover:text-helm-fg transition-colors">Refunds</Link>
      </p>
      <div className="flex items-center justify-center gap-1.5 text-[11px] text-helm-muted mt-3">
        <ShieldCheck className="w-3.5 h-3.5 text-helm-gold/70" /> Secure checkout by Paddle
      </div>
    </div>
  );
}
