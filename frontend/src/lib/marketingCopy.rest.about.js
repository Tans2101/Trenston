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
