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

export const HOW_TO_USE_FAQ = [
  {
    q: "Why can I not see Financials or Telemetry?",
    a:
      "Those screens are restricted on purpose. Owners always have them. Finance packs can open Financials, and some packs (such as Executive or Operations) can open Telemetry. Everyone else only sees them if an owner grants that section in Team & Access. If a screen is missing, ask your owner for access rather than assuming Trenston is broken.",
  },
  {
    q: "What if my company does not use QuickBooks, SAP Business One, or Google Calendar?",
    a:
      "That is fine. Trenston works with manual entry everywhere an integration is not connected. Connect tools when they help; nothing in the product requires them to get value from Briefing, Decisions, or department queues.",
  },
  {
    q: "What happens after I approve or delegate a decision in Decision Center?",
    a:
      "The decision moves out of the open queue. Approved, rejected, and delegated items stay visible under recently resolved so you can confirm the outcome and who owns the follow-through. Delegating to yourself keeps the item open so you can still approve or reject it.",
  },
  {
    q: "What is the difference between asking Ask Trenston and checking Decisions?",
    a:
      "Ask Trenston answers a question you type right now, using your live company data. Decisions is the queue of calls that already need approval or judgment, including suggestions Trenston drafts for you to confirm. Use Ask Trenston when you have a specific question; use Decisions when something is waiting on a yes, no, or owner.",
  },
  {
    q: "Who can see what I write in My Day?",
    a:
      "Private sticky notes on My Day are only visible to you. They are stored per user and are not shown to teammates or the owner. The optional team update on My Day is different: if you post one, it is shared with the team. Tasks you create or are assigned to follow normal task visibility for people who can see that work.",
  },
  {
    q: "I am in one department. Why do I not see the rest of the company?",
    a:
      "Access follows department membership and the permissions your owner set. You see My Day plus the department lanes you belong to. Company-wide screens such as Financials, Telemetry, or Team & Access appear only when your pack or an explicit grant includes them. That keeps each team in its own lane while leadership keeps the full picture.",
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
