/** Shared marketing copy — Landing surgical exports + re-export of About/Features/Help. */

export const TAGLINE = "Run the business. Don't chase it.";
export const CATEGORY = "CEO Operating System";
export const AUDIENCE = "Built for founders and owners running real operations — however lean the team.";
export const HERO_OUTCOME =
  "Open Trenston and see what changed, what needs a decision, and what you can hand off — synthesized from your live company data.";

export const HERO_SUB =
  "One clear view of money, people, work, and decisions — so you can make the call and get back to running the business.";

export const CEO_DAY = [
  { title: "Briefing", body: "What changed, what needs a decision, and what you can hand off — synthesized from your live data every time you open it." },
  { title: "Decision Center", body: "Pending approvals ranked by impact. Trenston recommends which to tackle first and why." },
  { title: "Ask Trenston", body: "\"What's our biggest risk this quarter?\" answered from your financials and pipeline, not the internet." },
  { title: "CEO Pack", body: "A summary of growth, cash, team pulse, and open decisions, generated in one click, ready to share with your leadership team." },
];

export const PRICING_FAQ = [
  { q: "Is there a free plan?", a: "Yes. Free includes 3 Trenston users, 5 AI document extracts to try it (then upgrade), Ask Trenston (10 messages/month), Google (Gmail & Calendar), and the AI briefing. Paid plans add higher monthly AI document extract and Ask Trenston limits, more users, and accounting integrations." },
  { q: "Is there a free trial?", a: "Yes. Starter, Growth, and Business include a 7-day free trial. Cancel before it ends and you will not be charged." },
  {
    q: "Can my leadership team use Trenston?",
    a: "Yes. Free supports up to 3 Trenston users, Starter up to 7, Growth up to 20, and Business up to 35, with role-based access packs. Trenston users are logins to the product — separate from your company's total employee headcount. A lean manufacturing company with serious revenue might only need a handful of users.",
  },
  {
    q: "What integrations are included?",
    a: "Google (Gmail & Calendar) is available on every plan, including Free. Starter adds QuickBooks, Xero, and SAP Business One. Growth and Business also add HubSpot and Slack webhook alerts.",
    link: { to: "/integrations", label: "See what each integration does" },
  },
  { q: "Can I cancel anytime?", a: "Yes. Manage billing through Paddle. Cancellation takes effect at the end of the current billing period. No refunds after payment. Use the trial to evaluate." },
];

export const PLANS = [
  {
    id: "free",
    label: "Free",
    price: 0,
    for: "Small teams trying Trenston",
    seats: 3,
    trialDays: 0,
    highlighted: false,
    includes: [
      "Up to 3 Trenston users",
      "5 AI document extracts to try it, then upgrade",
      "Ask Trenston (10 messages/month)",
      "AI briefing",
      "Dashboard & decisions",
      "Google integration (Gmail & Calendar)",
    ],
  },
  {
    id: "starter",
    label: "Starter",
    price: 15,
    for: "Small businesses",
    seats: 7,
    trialDays: 7,
    highlighted: true,
    includes: [
      "Up to 7 Trenston users",
      "AI document extracts (65/month)",
      "Ask Trenston (100 messages/month)",
      "Integrations: Google, QuickBooks, Xero, SAP Business One",
      "CEO Pack (shareable leadership summary)",
      "7-day free trial",
    ],
  },
  {
    id: "growth",
    label: "Growth",
    price: 39,
    for: "Growing businesses",
    seats: 20,
    trialDays: 7,
    highlighted: false,
    includes: [
      "Up to 20 Trenston users",
      "AI document extracts (150/month)",
      "Ask Trenston (200 messages/month)",
      "Everything in Starter",
      "Integrations: HubSpot, Slack",
      "Deeper reporting across a bigger team",
      "7-day free trial",
    ],
  },
  {
    id: "business",
    label: "Business",
    price: 99,
    for: "Larger companies",
    seats: 35,
    trialDays: 7,
    highlighted: false,
    includes: [
      "Up to 35 Trenston users",
      "AI document extracts (500/month)",
      "Ask Trenston (500 messages/month)",
      "Everything in Growth",
      "Priority support",
      "7-day free trial",
    ],
  },
];

/** @deprecated — use PLANS; kept for older imports */
export const PRO_PRICE = 15;
export const HELM_PRICE = PRO_PRICE;

/**
 * Point-of-purchase auto-renewal disclosure for paid plan CTAs (ARL / FTC proximity).
 * Cancellation is via Billing → Paddle customer portal (see Refunds / Billing).
 * Free plan returns "" — no trial, no charge, no disclosure required.
 */
export function paidPlanRenewalDisclosure(plan) {
  if (!plan || plan.id === "free" || !(Number(plan.price) > 0)) return "";
  const trial = Number(plan.trialDays ?? plan.trial_days ?? 0);
  if (!(trial > 0)) return "";
  const price = Number(plan.price);
  return (
    `${trial}-day free trial, then $${price}/mo unless you cancel before it ends. ` +
    "Cancel anytime in Billing through the Paddle customer portal."
  );
}

export const PRO_FEATURES = PLANS.find((p) => p.id === "starter").includes;
export const HELM_FEATURES = PRO_FEATURES;

export const PRODUCT_FACTS = [
  { v: "One open", l: "what changed, what to decide, what to hand off" },
  { v: "Ranked calls", l: "Decision Center puts the highest-impact approval first" },
  { v: "Live answers", l: "Ask Trenston from your financials and pipeline, not the internet" },
  { v: "Honest numbers", l: "missing cash shows as Add data — never a fake $0" },
];

export const HOW_IT_WORKS = [
  { n: "01", title: "Your team updates the work", body: "Finance, sales, operations, and other departments use their own simple queues. Connect the tools you already use, or enter it by hand — whatever's easiest." },
  { n: "02", title: "Trenston prepares your briefing", body: "Money, work, blockers, and open decisions are put in one short briefing. Missing information is called out plainly." },
  { n: "03", title: "You decide and hand off", body: "Approve, follow up, or assign the next step. Trenston keeps the owner and outcome visible so decisions do not disappear." },
];

export const FEATURE_HIGHLIGHTS = [
  { title: "Briefing", body: "What changed, what to decide, what to delegate, synthesized from your live company data." },
  { title: "Decision Center", body: "Approvals with AI recommendations on what to tackle first, plus a recently resolved list so calls do not disappear." },
  { title: "Cash & Spending", body: "Revenue, expenses, and cash tracking. Always know where the money stands." },
  { title: "Ask Trenston", body: "Your executive AI chief-of-staff, grounded in your live company data." },
];

export * from './marketingCopy.rest.js';
