/** Shared marketing copy — keep Landing, About, Features, and auth pages aligned. */

export const TAGLINE = "Run your business. Don't chase it.";
export const CATEGORY = "CEO Operating System";
export const AUDIENCE = "Built for founders and owners running real operations — from your first hire to your hundredth.";
export const FOUNDER_NAME = "Tansher Dhawan";
export const FOUNDER_ROLE = "Founder";
export const FOUNDER_CREDIT = `${FOUNDER_NAME}, ${FOUNDER_ROLE}`;
/** Public LinkedIn profile — also used as Person JSON-LD sameAs on /about. */
export const FOUNDER_LINKEDIN_URL = "https://www.linkedin.com/in/tansherdhawan/";
export const PUBLIC_CONTACT_EMAIL = "contact@trenston.com";
export const PUBLIC_CONTACT_MAILTO = `mailto:${PUBLIC_CONTACT_EMAIL}`;
export const PUBLIC_INSTAGRAM_HANDLE = "@usetrenston";
export const PUBLIC_INSTAGRAM_URL = "https://www.instagram.com/usetrenston/";
export const FOUNDED_DATE = "September 2026";
export const COMPANY_LOCATION = "BGC, Taguig, Philippines";
export const WHAT_TRENSTON_IS =
  "Trenston brings together what is happening across your company (money, sales, people, and day-to-day work) in one place, so you do not have to bounce between five tools or chase three people for a status update. It shows what needs a decision from you, lets you hand off what does not, and keeps a simple record of what happened.";
/** @deprecated use WHAT_TRENSTON_IS */
export const WHAT_HELM_IS = WHAT_TRENSTON_IS;
export const ABOUT_PROBLEM =
  "Owners running a business of this size often spend their mornings opening a dozen tools and asking people for status updates just to know what is happening. Trenston exists to close that gap.";
export const FOUNDER_NOTE =
  "Tansher Dhawan builds and ships Trenston himself — writing the code and handling day-to-day product work. There is no separate product team. What you see in the cockpit is what he is actively shipping.";

export const HERO_OUTCOME =
  "Open Trenston and see what changed, what needs a decision, and what you can hand off, synthesized from your live company data.";
export const HERO_SUB =
  "One clear view of money, people, work, and decisions, so you can make the call and get back to running the business.";

export const MISSION =
  "Trenston exists so an owner can open one place and see what the business is actually saying today: money, pipeline, people, and the work in motion, without reconstructing that picture from inboxes, spreadsheets, and status chases every morning.";

export const VISION =
  "The near direction is to deepen that same cockpit across every lane operators already run in Trenston (Briefing, Decisions, Financials, Production, Procurement, Legal, HR, Maintenance, Sales) so the morning open is the company, not another reconstruction project.";
export const ABOUT_DIFFERENTIATOR =
  "Trenston is grounded in the workspace's live data, not a generic chart library. Ask Trenston answers from actual financials and pipeline; Financials refuses to dress missing cash or runway up as $0; Decision Center keeps the call and its outcome visible instead of letting approvals vanish into chat; department status rolls into the Briefing so the morning picture is company-wide, not one lane at a time.";

export const ABOUT_STORY =
  "Running a company means your financials, your open decisions, your team's day-to-day work, and what is happening in each department all live in different places: a spreadsheet here, a person's head there, a chat thread nobody can find again. You are not choosing between competing dashboards. You do not have a single one that is honest about what needs you right now versus what can wait. Nobody has the whole picture, least of all the person responsible for it. That is the gap Trenston was built to close: pull money, decisions, people, and work into one place that shows what changed and what to decide, instead of making you assemble the picture yourself every time. What got built is a CEO operating system — Briefing, Decision Center, Financials and runway, Ask Trenston, and department workflows for Production, Procurement, Legal, HR, Maintenance, and Sales — synthesized into what needs the owner's attention.";

export const VALUES = [
  {
    title: "Signal over noise",
    body: "Briefing surfaces what changed across the company; Decision Center ranks what needs a call; department lanes keep operational detail where it belongs. The cockpit exists to help you decide or delegate, not to keep you scrolling through more charts.",
  },
  {
    title: "Quiet control",
    body: "Trenston does not run engagement loops or notification spam. You open Financials, Decisions, or a department board when you need them; the product is not designed to chase your attention through the day.",
  },
  {
    title: "Honest synthesis",
    body: "Missing cash, MRR, burn, or runway on Financials show as \"Add data,\" not $0. Ask Trenston answers from live workspace data and is told to admit gaps instead of inventing figures. Decision Center tracks real outcomes so a call does not disappear after you make it.",
  },
];

export const WHO_HELM_IS_FOR = [
  {
    title: "Founders and owners running real operations",
    body: "You are still close to the work, but you should not drown in status chasing. Trenston gives you a clear view to share with leadership without hiring a chief of staff.",
  },
  {
    title: "Owner-operators and traditional businesses",
    body: "Manufacturing, services, agencies, family companies. Trenston is a cockpit for running the operation, not a tool only venture-backed startups use.",
  },
  {
    title: "Leadership teams",
    body: "From a handful of people to a full leadership bench. Finance, sales, ops, and production keep their lanes. You get one synthesized view.",
  },
];

export const CEO_DAY = [
  { title: "Briefing", body: "What changed, what needs a decision, and what you can hand off, synthesized from your live data every time you open it." },
  { title: "Decision Center", body: "Pending approvals ranked by impact. Trenston recommends which to tackle first and why." },
  { title: "Ask Trenston", body: "\"What's our biggest risk this quarter?\" answered from your financials and pipeline, not the internet." },
  { title: "CEO Pack", body: "A summary of growth, cash, team pulse, and open decisions, generated in one click, ready to share with your leadership team." },
];

export const PRICING_FAQ = [
  { q: "Is there a free plan?", a: "Yes. Free includes 3 Trenston users, 5 AI document extracts to try it (then upgrade), Ask Trenston (10 messages/month), Google (Gmail & Calendar), and the AI briefing. Paid plans add higher monthly AI document extract and Ask Trenston limits, more users, and accounting integrations." },
  { q: "Is there a free trial?", a: "Yes. Starter, Growth, and Business include a 7-day free trial. Cancel before it ends and you will not be charged." },
  {
    q: "Can my leadership team use Trenston?",
    a: "Yes. Free supports up to 3 Trenston users, Starter up to 7, Growth up to 20, and Business up to 35, with role-based access packs. Trenston users are logins to the product, separate from your company's total employee headcount. A lean manufacturing company with serious revenue might only need a handful of users.",
  },
  {
    q: "What integrations are included?",
    a: "Google (Gmail & Calendar) is available on every plan, including Free. Starter adds QuickBooks, Xero, and SAP Business One. Growth and Business also add HubSpot and Slack webhook alerts.",
    link: { to: "/integrations", label: "See what each integration does" },
  },
  { q: "Can I cancel anytime?", a: "Yes. Manage billing through Paddle. Cancellation takes effect at the end of the current billing period. No refunds after payment. Use the trial to evaluate." },
];

/** Real, shipped integrations only — wordmarks for marketing showcase (no aspirational names). */
export const INTEGRATIONS_SHOWCASE = [
  { name: "Google", note: "Calendar & Gmail" },
  { name: "QuickBooks", note: "Accounting" },
  { name: "Xero", note: "Accounting" },
  { name: "SAP Business One", note: "ERP" },
  { name: "HubSpot", note: "CRM" },
  { name: "Slack", note: "Webhook alerts" },
];

/**
 * Short Features / Pricing pointer — full capability detail lives on /integrations
 * (sourced from backend/integrations_catalog.py + Slack webhook settings).
 */
export const INTEGRATIONS_PUBLIC_BLURB =
  "Connect the tools you already use so Financials, Briefing, Pipeline, and alerts stay current. Manual entry stays available for one-offs when an accounting system is connected.";

export const PUBLIC_INTEGRATIONS_INTRO =
  "Trenston connects to the tools your team already uses — nothing to migrate, nothing you must duplicate by hand.";

/** Public /integrations cards — text wordmarks only (vendor logos need written permission). */
export const PUBLIC_INTEGRATIONS = [
  {
    id: "google",
    name: "Google Calendar & Gmail",
    category: "Calendar & email",
    description:
      "Each teammate connects their own Google account. Sync your meetings into Trenston Calendar and your briefing — plus Gmail thread surfacing, Sheets export, calendar write, Gmail drafts, and Drive bill import. Teammates never see each other's Google data.",
    feeds: "Feeds Calendar & Briefing",
    scope:
      "Gmail is snippet-level thread surfacing (sender, subject, preview) plus optional draft replies you review and send in Gmail — not full inbox or message-body access.",
  },
  {
    id: "quickbooks",
    name: "QuickBooks",
    category: "Finance",
    description:
      "Pull purchases and invoices from your QuickBooks company into Financials. Use QuickBooks or Xero; you typically connect one accounting system.",
    feeds: "Feeds Financials & Decision Engine",
  },
  {
    id: "xero",
    name: "Xero",
    category: "Finance",
    description:
      "Pull invoices and bills from Xero into Financials, the global alternative to QuickBooks (UK, AU, NZ, and beyond).",
    feeds: "Feeds Financials & Decision Engine",
  },
  {
    id: "sap_b1",
    name: "SAP Business One",
    category: "Finance",
    description:
      "Pull A/R invoices and A/P purchase invoices from SAP Business One Service Layer into Financials.",
    feeds: "Feeds Financials & Decision Engine",
  },
  {
    id: "hubspot",
    name: "HubSpot",
    category: "Sales",
    description:
      "Pull HubSpot CRM deals into Trenston Pipeline and Telemetry, built for SMB and mid-market teams.",
    feeds: "Feeds Pipeline & Telemetry",
  },
  {
    id: "slack",
    name: "Slack",
    category: "Alerts",
    description:
      "Paste a Slack Incoming Webhook URL to post high-severity Trenston alerts to a channel.",
    feeds: "Delivers high-severity alerts",
    scope:
      "Webhook-based alerts only — not a full Slack app. No OAuth, no DMs, no slash commands.",
  },
];

export const PUBLIC_INTEGRATIONS_ATTRIBUTION =
  "Google, QuickBooks, Xero, SAP, HubSpot, and Slack are trademarks of their respective owners. Trenston is not affiliated with or endorsed by these companies.";

/** Not shipped — keep clearly labeled as coming soon on public pages. */
export const PUBLIC_INTEGRATIONS_COMING_SOON = [
  {
    id: "github",
    name: "GitHub",
    category: "Engineering",
    description:
      "Planned: track PR velocity and engineering delivery alongside business KPIs. Not available to connect today — do not treat this as a live Trenston integration.",
  },
];

export const FEATURE_CATEGORIES = [
  {
    id: "intelligence",
    label: "Executive intelligence",
    intro: "AI grounded in your company, not generic chatbot answers.",
    modules: [
      "Briefing",
      "Decision Center",
      "Ask Trenston",
      "CEO Pack",
      "Daily morning briefing",
      "Gmail thread surfacing + AI draft replies",
    ],
  },
  {
    id: "finance",
    label: "Finance & growth",
    intro: "Pipeline and financials are connected: won deals land as revenue, not a spreadsheet chase.",
    modules: [
      "Won deals become revenue",
      "Deal ownership & follow-ups",
      "Sales order book & monthly target",
      "Telemetry",
    ],
  },
  {
    id: "operations",
    label: "Production, procurement & maintenance",
    intro: "Not three separate trackers. When production is blocked, Trenston shows you exactly why, and jumps that item to the top of whichever queue is holding it up.",
    modules: [
      "Work order tracking",
      "Vendor memory",
      "Procurement spend visibility",
      "Equipment reliability alerts",
      "Maintenance operations",
      "Cross-department blocking",
    ],
  },
  {
    id: "people",
    label: "People & operations",
    intro: "Team access, department lanes, and integrations. Everyone contributes, you stay in control.",
    modules: ["Integrations", "Team & Access"],
  },
];

/** Canonical pricing — single source of truth for marketing, /pricing, prerender, and llms.txt.
 * Keep backend/plans.py seats/prices aligned. Do not duplicate dollar figures in docs/memory.
 */
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
  { v: "Honest numbers", l: "missing cash shows as Add data, never a fake $0" },
];

export const PROBLEMS = [
  {
    title: "The answer is scattered",
    body: "What needs your attention lives across Slack, the CRM, the finance sheet, the floor, and six dashboards. Nobody has the whole picture, least of all you.",
  },
  {
    title: "You react instead of lead",
    body: "By the time a problem reaches you, it is already a fire. Cash, delivery, and overload creep up silently between check-ins.",
  },
  {
    title: "Dashboards ≠ decisions",
    body: "More charts do not help. You need synthesis: the one number that moved, the one call to make, the one thing to hand off.",
  },
];

export const HOW_IT_WORKS = [
  { n: "01", title: "Your team updates the work", body: "Finance, sales, operations, and other departments use their own simple queues. Connect the tools you already use, or enter it by hand, whatever's easiest." },
  { n: "02", title: "Trenston prepares your briefing", body: "Money, work, blockers, and open decisions are put in one short briefing. Missing information is called out plainly." },
  { n: "03", title: "You decide and hand off", body: "Approve, follow up, or assign the next step. Trenston keeps the owner and outcome visible so decisions do not disappear." },
];

export const FEATURE_HIGHLIGHTS = [
  { title: "Briefing", body: "What changed, what to decide, what to delegate, synthesized from your live company data." },
  { title: "Decision Center", body: "Approvals with AI recommendations on what to tackle first, plus a recently resolved list so calls do not disappear." },
  { title: "Cash & Spending", body: "Revenue, expenses, and cash tracking. Always know where the money stands." },
  { title: "Ask Trenston", body: "Your executive AI chief-of-staff, grounded in your live company data." },
];

/** Department lanes — enable only what the company actually uses. */
export const DEPARTMENTS_SECTION = {
  label: "Departments",
  title: "Turn on only the departments your company actually needs.",
  intro:
    "Give each team its own lane (Procurement, Production, Accounting & Finance, Sales, Legal, HR, Engineering & Maintenance) while you see everything from the top. Disable what you do not use.",
  items: [
    {
      name: "Procurement",
      icon: "package",
      body: "A purchase request queue: requested, approved, ordered, delivered. Each request moves on its own.",
    },
    {
      name: "Production",
      icon: "factory",
      body: "An ordered production chain. Custom stages with status and owners; leads reorder the line as work flows.",
    },
    {
      name: "Accounting & Finance",
      icon: "landmark",
      body: "Your finance team logs revenue and expenses. Trenston turns that into live cash, revenue, and spend across the cockpit.",
    },
    {
      name: "Sales",
      icon: "briefcase",
      body: "Deal pipeline by stage: open value and wins roll straight into the briefing.",
    },
    {
      name: "Legal",
      icon: "scale",
      body: "A matter queue for contracts and reviews, from draft through signed and filed, with documents attached.",
    },
    {
      name: "HR",
      icon: "users",
      body: "Per-hire onboarding from a reusable template. Each new hire gets their own checklist with assignees.",
    },
    {
      name: "Engineering & Maintenance",
      icon: "wrench",
      body: "A ticket queue for equipment: reported, diagnosed, in repair, resolved. Assign a technician and track it.",
    },
  ],
};

export const FEATURE_MODULES = [
  {
    title: "Briefing",
    ceoValue: "Know what changed and what needs you whenever you open Trenston.",
    body: "Three columns: what changed, what to decide, what to delegate, plus AI synthesis when you need the full picture.",
    example: "Revenue is ahead of plan, but engineering capacity risk is rising. Approve the infra reservation.",
  },
  {
    title: "Decision Center",
    ceoValue: "Every open decision, ranked by impact.",
    body: "Approve, follow up, or delegate with AI confidence scores. Resolved calls stay visible with status and owner so they do not disappear after you act.",
    example: "Six pending approvals. Trenston recommends the $40K reservation first: 4.2-month payback.",
  },
  {
    title: "Won deals become revenue",
    ceoValue: "Close the deal once. Financials and production follow.",
    body: "Moving a deal to won logs the revenue automatically and offers a production work order from the same deal, so pipeline and financials stay linked.",
    example: "Acme Enterprise closes at $25k. Revenue appears in Financials; Trenston asks if you want a work order started.",
  },
  {
    title: "Deal ownership & follow-ups",
    ceoValue: "Real owners, planned next steps, not free-text ghosts.",
    body: "Deals link to Sales teammates, with next-step and follow-up dates so quiet deals surface before they stall.",
    example: "Riley owns the negotiation. Call-back Thursday is on the card, and Trenston reminds before it slips.",
  },
  {
    title: "Telemetry",
    ceoValue: "Live KPIs: signal over noise.",
    body: "Headcount, open tasks, MRR, and burn in one view. No digging through five dashboards.",
    example: "MRR up 8% MoM. Open tasks down. One team member overloaded.",
  },
  {
    title: "Ask Trenston",
    ceoValue: "Your executive chief-of-staff, on call.",
    body: "Ask anything about your company, grounded in live workspace data, not generic AI.",
    example: "What's our biggest risk this quarter? Trenston answers from your actual financials and pipeline.",
  },
  {
    title: "CEO Pack",
    ceoValue: "Leadership synthesis in one click.",
    body: "A plain-English update covering what happened, what needs attention, and what to do next, ready for your leadership team.",
    example: "Financial snapshot, team updates, and open decisions, formatted to forward, not rebuilt in slides.",
  },
  {
    title: "Daily morning briefing",
    ceoValue: "The company picture in your inbox before the first meeting.",
    body: "One email per day to the CEO or owner covering Sales, Procurement, Production, and Maintenance — separate from the weekly CEO Pack PDF. Metrics with no data yet say so plainly; nothing is invented.",
    example: "Tuesday 7am: order book vs monthly target, late purchase orders, yesterday’s output shortfall, and two spares below threshold — without opening the app first.",
  },
  {
    title: "Gmail thread surfacing + AI draft replies",
    ceoValue: "Inbox signal without living in email.",
    body: "Surfaces important Gmail threads in the cockpit and drafts replies you can send, grounded in company context, not a blank compose box.",
    example: "A customer thread needs a decision. Trenston drafts the reply; you edit and send.",
  },
  {
    title: "Work order tracking",
    ceoValue: "Production status without a separate system.",
    body: "Work orders move through a fixed flow with daily target-vs-actual logging, overtime cost visibility, and optional yield tracking for businesses that convert raw materials into finished goods.",
    example: "Two work orders for the same product, each with its own daily target. Shortfalls show with overtime cost; yield drops flag process problems early.",
  },
  {
    title: "Vendor memory",
    ceoValue: "Re-order without starting from scratch.",
    body: "Procurement remembers past vendors and prices, and surfaces each vendor’s sourcing-time and delivery-delay history so you pick on performance, not just last price.",
    example: "Same bracket as last quarter. Trenston recalls the vendor, last price, and whether they typically deliver late.",
  },
  {
    title: "Sales order book & monthly target",
    ceoValue: "See the real order book without chasing sales reps.",
    body: "Log buyer, country, product, price, and quantity in Trenston instead of a private spreadsheet. Rollups by country and product, a forward view of expected orders for the next 2–3 months, and a company-wide monthly target vs confirmed actual with the gap as a real number.",
    example: "Target $5M this month, confirmed $3M. India and UAE lead the book; $1.2M expected next month is already visible before the review.",
  },
  {
    title: "Procurement spend visibility",
    ceoValue: "Know what purchasing actually costs this month.",
    body: "Total spend with breakdowns by vendor and item, plus a count of requests with no cost recorded so totals are never quietly incomplete. An optional department budget shows actual vs budget only when someone sets it — otherwise you still see actual alone.",
    example: "September spend $184k across three vendors. Twelve requests still have no cost. Budget not set, so the card shows actual without a fake percentage.",
  },
  {
    title: "Equipment reliability alerts",
    ceoValue: "Notice the machine that keeps coming back.",
    body: "Maintenance tickets for equipment issues, plus reliability alerts when the same machine repeats, and ticket-open downtime totals.",
    example: "Press #3 logged three tickets in 90 days. Trenston flags it before the next breakdown.",
  },
  {
    title: "Maintenance operations",
    ceoValue: "Spares, schedules, and repair cost — not just tickets when something breaks.",
    body: "Critical spares with a below-threshold flag, per-machine schedules that update last-serviced when a matching ticket is resolved, annual maintenance contract renewals, and overhead repair cost vs an optional budget.",
    example: "Budget $100k/month for repairs; actual hits $1M. Two bearings below minimum, one AMC due in 12 days, and Press #2’s oil change is overdue.",
  },
  {
    title: "Cross-department blocking",
    ceoValue: "See why production is stuck, in one place.",
    body: "A blocked work order shows the part still in transit or the machine still in repair, and that item jumps to the top of its queue automatically.",
    example: "WO-441 blocked on a bearing order and a mill repair. Both sit at the top of Procurement and Maintenance.",
  },
  {
    title: "Integrations",
    ceoValue: "Your team keeps their tools. You get the picture.",
    body: INTEGRATIONS_PUBLIC_BLURB,
    example: "Finance syncs QuickBooks or SAP Business One. Important Gmail threads surface in Briefing. You see it all in the cockpit.",
    link: { to: "/integrations", label: "See all integrations" },
  },
  {
    title: "Team & Access",
    ceoValue: "Invite your team with the right lane.",
    body: "Role-based packs plus per-department access. Turn on only the departments you need. Each team works in its own lane; you see everything from the top.",
    example: "Your plant lead owns Production. Purchasing runs the request queue. You still see the synthesis in the briefing.",
  },
];

/** Public Help page: plain-language orientation for first-time users. */
export const HOW_TO_USE_INTRO = {
  title: "How to use Trenston",
  subtitle: "A plain guide for owners and teammates who are new here.",
  lead:
    "Trenston brings together what is happening across your company (money, sales, people, and day-to-day work) in one place, so you do not have to bounce between five tools or chase three people for a status update. It shows what needs a decision from you, lets you hand off what does not, and keeps a simple record of what happened.",
};

export const HOW_TO_USE_AUDIENCES = [
  {
    title: "If you own or run this company",
    body:
      "Start with Briefing, then Decisions. Use Financials and Telemetry when you need the numbers, invite people in Team & Access, and turn on only the Departments your company actually uses.",
  },
  {
    title: "If you were invited to a team",
    body:
      "Start with My Day for your own notes and tasks. You will also see the department pages you belong to (for example Procurement or Production). Seeing only your lanes is intentional: access follows the departments and permissions your owner set, not a hidden lockout.",
  },
];

export const HOW_TO_USE_CONCEPTS = [
  {
    term: "Briefing",
    explanation:
      "Briefing is Trenston's homepage for leadership. It pulls together what changed recently, what still needs a call from you, and what you could hand off. Open it when you want the company picture without opening every other tool.",
    example:
      "You open Briefing and see cash was updated, two deals moved stage, and one approval is waiting. You handle the approval and leave the rest for later.",
  },
  {
    term: "My Day",
    explanation:
      "My Day is your personal workspace inside Trenston. It holds private sticky notes, your tasks, and an optional team update you can share. Every teammate gets My Day, not only the owner.",
    example:
      "Before a busy afternoon you jot three priorities on private notes, check your open tasks, and post a short team update so others know what you are focused on.",
  },
  {
    term: "Decisions",
    explanation:
      "In Trenston, a Decision is a specific call that needs approval, rejection, or a clear owner, not just a vague to-do. Decision Center collects those calls, can draft suggestions from live company data, and keeps resolved items visible so you can see what landed.",
    example:
      "A budget request shows up as a Decision. You approve it, or you delegate it to your finance lead. Later it appears under recently resolved so it does not disappear after you act.",
  },
  {
    term: "Departments",
    explanation:
      "Departments are optional work lanes such as Procurement, Production, Legal, HR, or Maintenance. An owner turns on only what the company uses. Each enabled department gets its own queue so that team can move work without cluttering everyone else's screen.",
    example:
      "You enable Procurement and Production. Purchasing lives in Procurement; shop-floor work orders live in Production. People only see the lanes they are on.",
  },
  {
    term: "Ask Trenston",
    explanation:
      "Ask Trenston is a question box grounded in your live workspace data. You type a question in plain language and get an answer from what Trenston already knows about the company, not from a generic internet chatbot.",
    example:
      "You ask \"What is stuck in procurement?\" and Trenston answers from open purchase requests and blockers, instead of giving generic advice.",
  },
  {
    term: "Telemetry",
    explanation:
      "Telemetry is a snapshot of key company numbers and risks in one place: things like headcount, open work, revenue, and cash when you have access. It is for a quick read of the state of the company, not for day-to-day data entry.",
    example:
      "Before a leadership meeting you open Telemetry to confirm headcount, open tasks, and runway without digging through separate spreadsheets.",
  },
  {
    term: "Financials",
    explanation:
      "Financials is where revenue, expenses, and cash are logged so Trenston can show MRR, burn, and runway elsewhere in the cockpit. Your finance team (or anyone granted access) can enter numbers manually, import a CSV, or connect accounting tools. When QuickBooks, Xero, or SAP Business One is connected, synced books are the source of truth and manual entry is for one-offs that sync will not catch.",
    example:
      "Finance logs this month's expenses and updates cash. Briefing and Telemetry then reflect the new runway without a separate spreadsheet chase.",
  },
  {
    term: "Reports",
    explanation:
      "Reports is where you store written context and generate a shareable CEO Pack. The pack is a plain-English update covering financials, team pulse, and open decisions that you can forward to leadership.",
    example:
      "You add a short sales recap, then generate a CEO Pack and send that one document instead of rebuilding slides from five sources.",
  },
  {
    term: "Team & Access",
    explanation:
      "Team & Access is where owners invite people and choose what each person can do. Access packs set a baseline (for example Finance or Member), and owners can also grant specific areas like Financials or Decisions to individuals.",
    example:
      "You invite your CFO on the Finance pack and grant your ops lead access to Decisions, so they can act without seeing every other restricted area.",
  },
  {
    term: "Integrations",
    explanation:
      "Integrations connect outside tools such as Google Calendar, QuickBooks, Xero, SAP Business One, or HubSpot so Trenston can pull events, accounting, and CRM data automatically. Nothing requires an integration: you can enter the same information manually if you prefer.",
    example:
      "You connect Google Calendar so meetings show in Trenston, while expenses keep being entered by hand until QuickBooks or SAP Business One is ready.",
  },
];

export const HOW_TO_USE_STEPS = [
  {
    title: "Open Briefing",
    body:
      "Go to Briefing (shown as /app once you are signed in). This is Trenston's homepage: what changed, what needs a decision, and what you could hand off. Start sessions here when you want the company picture first.",
    audience: "everyone",
  },
  {
    title: "Act on one Decision",
    body:
      "Open Decisions (/app/decisions). Pick one item that needs a call, then approve it, reject it, or assign a clear owner. Trenston keeps the result in recently resolved so the call does not vanish after you act.",
    audience: "everyone",
  },
  {
    title: "Learn My Day and your department lane",
    body:
      "Open My Day (/app/me) for private notes and your tasks. If you belong to a department, open that lane next and move one real item forward. Invited teammates can stop here for a solid first pass.",
    audience: "everyone",
  },
  {
    title: "Connect an integration (owners and admins)",
    body:
      "If you manage the workspace, open Settings and go to Integrations, then connect Google Calendar, QuickBooks, or another available tool when it helps. Skip this if you are an invited teammate without that access, or if your company prefers manual entry for now.",
    audience: "owner",
  },
  {
    title: "Invite a teammate (owners)",
    body:
      "In Team & Access (/app/members), invite someone who should contribute, pick an access pack, and grant only the sections they need. They will land in My Day and their department lanes rather than seeing every owner screen by default.",
    audience: "owner",
  },
  {
    title: "Generate a CEO Pack (owners and report access)",
    body:
      "Open Reports (/app/reports) and generate a CEO Pack when you need a shareable leadership update. This step is for owners and people with report access; department teammates usually will not see it.",
    audience: "owner",
  },
];

/**
 * Public /help FAQ — grounded in backend/plans.py + this file (PLANS, integrations, how-to).
 * prerender-marketing.mjs injects FAQPage JSON-LD from this export for /help.
 */
export const HOW_TO_USE_FAQ = [
  {
    q: "Is there a free plan?",
    a:
      "Yes. Free is $0 and includes up to 3 Trenston users, 5 AI document extracts to try it (then upgrade), Ask Trenston (10 messages/month), AI briefing, Dashboard & decisions, and Google (Gmail & Calendar). Accounting integrations (QuickBooks, Xero, SAP Business One) start on Starter.",
  },
  {
    q: "What are the paid plans and is there a free trial?",
    a:
      "Starter is $15/mo (up to 7 users), Growth is $39/mo (up to 20), and Business is $99/mo (up to 35). Each paid plan includes a 7-day free trial. Cancel before the trial ends and you will not be charged. Billing runs through Paddle.",
  },
  {
    q: "What integrations are included on each plan?",
    a:
      "Google (Gmail & Calendar) is available on every plan, including Free. Starter adds QuickBooks, Xero, and SAP Business One. Growth and Business also add HubSpot and Slack webhook alerts. Connect only what helps — manual entry stays available everywhere else.",
  },
  {
    q: "Can my leadership team use Trenston?",
    a:
      "Yes. Free supports up to 3 Trenston users, Starter up to 7, Growth up to 20, and Business up to 35, with role-based access packs. Trenston users are product logins, separate from your company's total employee headcount. A lean manufacturing company with serious revenue might only need a handful of users.",
  },
  {
    q: "Do I need QuickBooks, SAP Business One, or Google Calendar to get started?",
    a:
      "No. Trenston works with manual entry everywhere an integration is not connected. Connect tools when they help; nothing requires them to get value from Briefing, Decisions, or department queues.",
  },
  {
    q: "Why can I not see Financials or Telemetry?",
    a:
      "Those screens are restricted on purpose. Owners always have them. Finance packs can open Financials, and some packs (such as Executive or Operations) can open Telemetry. Everyone else only sees them if an owner grants that section in Team & Access. If a screen is missing, ask your owner for access rather than assuming Trenston is broken.",
  },
  {
    q: "What is the difference between Ask Trenston and Decisions?",
    a:
      "Ask Trenston answers a question you type right now from your live company data (subject to plan message limits: Free 10/month, Starter 100, Growth 200, Business 500). Decisions is the queue of calls that already need approval or judgment. Use Ask Trenston for a specific question; use Decisions when something is waiting on a yes, no, or owner.",
  },
  {
    q: "Who can see what I write in My Day?",
    a:
      "Private sticky notes on My Day are only visible to you. They are stored per user and are not shown to teammates or the owner. The optional team update on My Day is different: if you post one, it is shared with the team. Tasks you create or are assigned to follow normal task visibility for people who can see that work.",
  },
];

/** Quick-reference paths for people who already know the concepts above. */
export const HOW_TO_USE_MODULES = [
  { nav: "Briefing", path: "/app", tip: "Company homepage: what changed, what to decide, what to hand off." },
  { nav: "My Day", path: "/app/me", tip: "Your private notes, tasks, and optional team update." },
  { nav: "Decisions", path: "/app/decisions", tip: "Approve, reject, or assign ownership; review what already resolved." },
  { nav: "Ask Trenston", path: "/app/ask", tip: "Ask a question about your live company data." },
  { nav: "Telemetry", path: "/app/telemetry", tip: "One-screen snapshot of key numbers and risks (access required)." },
  { nav: "Financials", path: "/app/financials", tip: "Log revenue, expenses, and cash (access required)." },
  { nav: "Pipeline", path: "/app/sales", tip: "Deal stages and open pipeline value." },
  { nav: "Reports", path: "/app/reports", tip: "Written context and shareable CEO Pack." },
  { nav: "Departments", path: "/app/settings", tip: "Turn on Procurement, Production, Legal, HR, and more." },
  { nav: "Team & Access", path: "/app/members", tip: "Invite people and choose what each person can open." },
  { nav: "Integrations", path: "/app/integrations", tip: "Now under Settings → Integrations. Optional connections such as Google Calendar, QuickBooks, Xero, SAP Business One, or HubSpot." },
];
