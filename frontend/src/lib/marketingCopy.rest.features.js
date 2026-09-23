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
