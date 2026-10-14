/**
 * In-app guides: what each page is for, a few how-tos, and a short tour that
 * lights up the real buttons. Plain words, no jargon, no AI.
 *
 * A step's `targets` are CSS selectors tried in order; the first one that is
 * visible on screen gets highlighted. If none is there (say the person can't
 * use that button, or the list is empty), the step still shows, centred.
 */

const tid = (...ids) => ids.map((id) => `[data-testid="${id}"]`);

const SEARCH = tid("action-search-bar-inline", "mobile-search-btn");
const HELP = tid("page-help-btn", "page-help-btn-mobile");

export const GUIDES = [
  {
    id: "briefing",
    path: /^\/app\/?$/,
    name: "Briefing",
    purpose: "Your company at a glance: what changed, what needs a decision, and how the money looks, on one screen.",
    tips: [
      "Read it top to bottom whenever you open Trenston. It takes about two minutes.",
      "Anything that says \"Add data\" isn't known yet. Trenston never fills in a made-up number.",
      "Click any line under What changed to jump straight to it.",
    ],
    steps: [
      {
        targets: tid("briefing-hero-metrics", "briefing-cockpit-hero"),
        title: "Your numbers at a glance",
        body: "Cash, runway and this month's money. If a box says Add data, Trenston doesn't know that number yet, and it will never guess one.",
      },
      {
        targets: tid("briefing-ai-summary"),
        title: "Today's summary",
        body: "A short write-up of what matters today, built from your own records. Press Generate when you want a fresh one.",
      },
      {
        targets: tid("briefing-what-changed"),
        title: "What changed",
        body: "Everything new since you last looked: updates, deals, money, tasks. Click a line to open it.",
      },
      {
        targets: tid("briefing-what-to-decide"),
        title: "What to decide",
        body: "Open calls that are waiting on you. Open one to approve it, push back, or hand it to someone.",
      },
      {
        targets: SEARCH,
        title: "Find or add anything",
        body: "Press Ctrl+K (Cmd+K on a Mac) to jump to any page. Type task, decision or note first to add one in seconds.",
      },
      {
        targets: HELP,
        title: "Stuck on any page? Press ?",
        body: "Every page has this button. It explains the page in plain words and can replay its tour.",
      },
    ],
  },
  {
    id: "myday",
    path: /^\/app\/me\/?$/,
    name: "My Day",
    purpose: "Only your work: what's waiting on you, your tasks, your private notes and your daily update.",
    tips: [
      "Start here, then work down the list.",
      "Post a two-line update at the end of the day so nobody needs to ask how it's going.",
      "Notes here are private. Only you can see them.",
    ],
    steps: [
      {
        targets: tid("needs-your-call", "needs-your-call-loading"),
        title: "Waiting on you",
        body: "Decisions and requests that need your answer. Clear these first, because other people are stuck until you do.",
      },
      {
        targets: tid("my-work-feed"),
        title: "Your work",
        body: "Everything assigned to you, soonest first. Late items are marked so they don't slip by.",
      },
      {
        targets: tid("myday-add-task-btn"),
        title: "Add something for yourself",
        body: "Quick tasks for you only. Give it a date and it shows up in your list on that day.",
      },
      {
        targets: tid("team-update-form", "my-team-update", "team-updates-card"),
        title: "Post your update",
        body: "Two lines: what you did and what's next. It goes into your manager's Briefing, so you can skip the status meeting.",
      },
      {
        targets: tid("new-note-btn", "sticky-notes-grid"),
        title: "Private notes",
        body: "Sticky notes only you can see. Handy for things you don't want to forget but don't belong on the task board.",
      },
    ],
  },
  {
    id: "decisions",
    path: /^\/app\/decisions\/?$/,
    name: "Decisions",
    purpose: "Every call you need to make, in one list, so nothing important waits in a chat thread.",
    tips: [
      "Log anything you need to decide: a hire, a price change, which supplier to use.",
      "Write what you're leaning towards. Future you will want to know why.",
      "After deciding, come back later and note how it turned out. That's how you learn which calls work.",
    ],
    steps: [
      {
        targets: tid("new-decision-btn", "empty-new-decision-btn"),
        title: "Log a decision",
        body: "Give it a title, what you're leaning towards and a due date. It shows on your Briefing until it's done.",
      },
      {
        targets: tid("suggested-decisions", "refresh-suggestions-btn"),
        title: "Suggestions from your records",
        body: "Trenston spots things that need a call, like a late supplier or a deal that went quiet, and suggests them here. Add the ones that matter and dismiss the rest.",
      },
      {
        targets: [],
        title: "Close the loop",
        body: "When you decide, mark it approved or rejected. Later, record how it went. Over time that tells you which kinds of calls you get right.",
      },
    ],
  },
  {
    id: "financials",
    path: /^\/app\/financials\/?$/,
    name: "Financials",
    purpose: "Your cash, what comes in, what goes out, and how many months the money lasts.",
    tips: [
      "Start with two things: what's in the bank today, and one month of income and expenses.",
      "Mark repeating costs (rent, salaries, software) as recurring so you don't type them every month.",
      "You can drop a bill or invoice on the page to read it in, or connect QuickBooks or Xero.",
    ],
    steps: [
      {
        targets: tid("runway-meter", "fin-Runway"),
        title: "Runway",
        body: "How many months your cash lasts if spending stays the same. It needs your cash balance and at least one month of numbers.",
      },
      {
        targets: tid("runway-update-cash-btn", "edit-settings-btn", "empty-settings-btn"),
        title: "Set your cash balance",
        body: "Enter what's in the bank today. Update it whenever it changes a lot.",
      },
      {
        targets: tid("add-entry-btn", "empty-add-entry-btn"),
        title: "Add income and expenses",
        body: "One line per item: a client payment, salaries, rent. Pick the month it belongs to.",
      },
      {
        targets: tid("upload-bill-btn", "empty-upload-bill-btn", "import-menu-btn"),
        title: "Or bring them in",
        body: "Drop in a bill or invoice and Trenston reads it for you to check. You can also import a spreadsheet (CSV).",
      },
      {
        targets: tid("ledger"),
        title: "Your ledger",
        body: "Every entry, month by month. Click one to fix or delete it.",
      },
    ],
  },
  {
    id: "tasks",
    path: /^\/app\/tasks\/?$/,
    name: "Tasks",
    purpose: "Everyone's work on one board: what's waiting, what's moving and what's done.",
    tips: [
      "Give every task one owner and a date. Tasks without a date never feel late.",
      "Move cards along as work happens, so the board is always true.",
      "Late tasks turn red and show up on the Briefing.",
    ],
    steps: [
      {
        targets: tid("new-task-btn", "empty-new-task-btn"),
        title: "Add a task",
        body: "Write it as an action (\"Send Acme the quote\"), pick who owns it and when it's due.",
      },
      {
        targets: tid("task-board"),
        title: "Move work across",
        body: "Drag a card from To-Do to In Progress, Review and Done as the work moves. Everyone who cares sees it without asking.",
      },
      {
        targets: SEARCH,
        title: "Faster: add from anywhere",
        body: "Press Ctrl+K on any page and type: task send the quote friday for Ann. Check the preview, press Enter, done.",
      },
    ],
  },
  {
    id: "sales",
    path: /^\/app\/sales\/?$/,
    name: "Sales",
    purpose: "The deals you're chasing, what stage each one is at, and what happens next.",
    tips: [
      "Every open deal should have a next step and a date.",
      "Deals that sit still too long get flagged on your Briefing.",
      "Mark deals won or lost so your pipeline total stays honest.",
    ],
    steps: [
      {
        targets: tid("add-deal-btn", "empty-add-deal-btn"),
        title: "Add a deal",
        body: "Who it's with, roughly what it's worth, the stage, and the next step with a date.",
      },
      {
        targets: tid("metric-open"),
        title: "Your open pipeline",
        body: "The total of deals you haven't won or lost yet. It's what could come in, not what will.",
      },
      {
        targets: tid("sales-tabs"),
        title: "Different views",
        body: "Switch between the deal board and the other sales views here.",
      },
    ],
  },
  {
    id: "automations",
    path: /^\/app\/automations\/?$/,
    name: "Automations",
    purpose: "Rules that watch the company for you and create a task or an alert when something happens.",
    tips: [
      "Start with a ready-made rule. One click and it's on.",
      "Each problem fires a rule once, so turning one on never floods the board.",
      "Money rules only assign tasks to you, so the figures stay private.",
    ],
    steps: [
      {
        targets: tid("automations-templates"),
        title: "Start with a ready-made rule",
        body: "Pick one that matches a problem you keep catching too late, like an overdue supplier order or short runway.",
      },
      {
        targets: tid("automations-rules"),
        title: "Your rules",
        body: "Turn rules on or off with the switch. Each one says in plain words what it watches and what it does.",
      },
      {
        targets: tid("automations-new-rule"),
        title: "Build your own",
        body: "Choose what to watch, then whether to make a task (for whom, how urgent) or just show an alert.",
      },
      {
        targets: tid("automations-activity"),
        title: "What the rules did",
        body: "A log of every task a rule created, so you can see they're working.",
      },
    ],
  },
  {
    id: "map",
    path: /^\/app\/map\/?$/,
    name: "Company map",
    purpose: "Your whole company as one picture: money in and out, what you've promised, and what's going wrong.",
    tips: [
      "Red means something needs attention. Each red item comes with a next step.",
      "The map only shows what your records say. Add data and it fills in.",
      "Tap anything to see the detail and jump to it.",
    ],
    steps: [
      {
        targets: tid("company-map-svg"),
        title: "One picture",
        body: "Cash in the middle. Where money comes from on the left, where it goes on the right. Promises and deadlines below.",
      },
      {
        targets: tid("map-problems"),
        title: "What needs you",
        body: "Problems, worst first, each with a plain next step. Work through these and the red disappears.",
      },
    ],
  },
  {
    id: "reports",
    path: /^\/app\/reports\/?$/,
    name: "Reports",
    purpose: "Ready-made summaries to send to investors, partners or your team, plus exports of your numbers.",
    tips: [
      "The CEO Pack is a one-page summary of the week. Generate, check, copy or download.",
      "Export your financials as PDF or Excel for your accountant.",
    ],
    steps: [
      {
        targets: tid("generate-pack-btn"),
        title: "CEO Pack",
        body: "One click makes a summary of the week from your real records. Read it, then copy it or download it as a PDF.",
      },
      {
        targets: tid("financial-export-card"),
        title: "Export your numbers",
        body: "Pick a period and download your financials as PDF or Excel.",
      },
      {
        targets: tid("add-report-btn"),
        title: "Department reports",
        body: "Write or collect reports from each part of the business in one place.",
      },
    ],
  },
  {
    id: "ask",
    path: /^\/app\/ask\/?$/,
    name: "Ask Trenston",
    purpose: "Ask questions about your company in plain words and get answers from your own records.",
    tips: [
      "Ask like you'd ask a colleague: \"What's our biggest risk this month?\"",
      "If something isn't in your records, it says so instead of making it up.",
      "Your plan includes a set number of messages a month.",
    ],
    steps: [
      {
        targets: tid("ask-input"),
        title: "Ask in plain words",
        body: "For example: \"Which costs went up the most?\" or \"What's late this week?\"",
      },
      {
        targets: tid("ask-suggestion"),
        title: "Not sure what to ask?",
        body: "Tap a suggestion to start.",
      },
      {
        targets: tid("ask-quota"),
        title: "Your monthly messages",
        body: "Shows how many questions you have left this month.",
      },
    ],
  },
  {
    id: "people",
    path: /^\/app\/people\/?$/,
    name: "People",
    purpose: "Who works with you, their role and their department.",
    tips: [
      "Adding someone here doesn't give them a login. Invite them under Team & Access for that.",
      "Put people in departments so work and updates land in the right place.",
    ],
    steps: [
      {
        targets: tid("add-person-btn", "empty-add-person-btn"),
        title: "Add a person",
        body: "Name, role and department. You can invite them to log in from the same form.",
      },
      {
        targets: tid("people-unassigned-callout"),
        title: "People without a department",
        body: "Give them one so their work shows up in the right place.",
      },
    ],
  },
  {
    id: "calendar",
    path: /^\/app\/calendar\/?$/,
    name: "Calendar",
    purpose: "Your meetings and every dated item in Trenston (tasks, deadlines, deals) in one week view.",
    tips: [
      "Connect Google Calendar so your meetings show here too.",
      "Due dates from tasks, legal deadlines and deals appear automatically.",
    ],
    steps: [
      {
        targets: tid("connect-google-calendar-btn", "connect-calendar-btn"),
        title: "Connect your calendar",
        body: "Bring in your Google Calendar so meetings and deadlines sit side by side.",
      },
      {
        targets: tid("add-event-btn"),
        title: "Add an event",
        body: "Add something to the calendar, and choose whether it also goes to Google.",
      },
    ],
  },
  {
    id: "members",
    path: /^\/app\/members\/?$/,
    name: "Team & Access",
    purpose: "Who can log in, and what each person can see.",
    tips: [
      "Invite by email and pick a role. Each role only sees what it needs.",
      "Members see their own work. Financials stay with people you give access to.",
    ],
    steps: [
      {
        targets: tid("invite-email-input"),
        title: "Invite someone",
        body: "Type their email and pick their role. They get an email with a link to join.",
      },
      {
        targets: tid("invite-pack-select"),
        title: "Pick what they can see",
        body: "Roles decide access. A sales person sees sales, finance sees financials, and so on.",
      },
    ],
  },
  {
    id: "modeling",
    path: /^\/app\/modeling\/?$/,
    name: "Financial Modeling",
    purpose: "Try \"what if\" plans, like hiring two people or losing a client, and see what happens to your cash.",
    tips: [
      "It starts from your real numbers, so add cash and a few months of entries first.",
      "Save a plan to compare it with others later. Nothing here changes your real books.",
    ],
    steps: [
      {
        targets: tid("modeling-controls", "open-controls"),
        title: "Change the plan",
        body: "Move the controls: new hires, price changes, cost cuts.",
      },
      {
        targets: tid("modeling-chart"),
        title: "See the effect",
        body: "The chart shows your cash month by month under this plan, next to how things go now.",
      },
      {
        targets: tid("scenario-save", "scenario-bar"),
        title: "Save and compare",
        body: "Save plans you like and switch between them.",
      },
    ],
  },
  {
    id: "integrations",
    path: /^\/app\/integrations\/?$/,
    name: "Integrations",
    purpose: "Connect the tools you already use so their data shows up here without typing.",
    tips: [
      "Google brings in your email and calendar.",
      "QuickBooks or Xero bring in your books, so Financials stays up to date by itself.",
    ],
    steps: [],
  },
  {
    id: "production",
    path: /^\/app\/departments\/production\/?$/,
    name: "Production",
    purpose: "Work orders: what's being made, for whom, and whether it's on time.",
    tips: ["Add each job as a work order with a due date.", "Late work orders show up on the Briefing."],
    steps: [{ targets: tid("add-work-order-btn", "add-work-order-empty"), title: "Add a work order", body: "What's being made, how many, for which customer, and when it's due." }],
  },
  {
    id: "procurement",
    path: /^\/app\/departments\/procurement\/?$/,
    name: "Procurement",
    purpose: "What you've ordered from suppliers and when it should arrive.",
    tips: ["Add each order with an expected delivery date.", "Late deliveries that hold up production get flagged first."],
    steps: [{ targets: tid("add-procurement-request-btn"), title: "Add an order", body: "Item, quantity, cost and when it should arrive." }],
  },
  {
    id: "legal",
    path: /^\/app\/departments\/legal\/?$/,
    name: "Legal",
    purpose: "Contracts, filings and renewals, with their deadlines, so none of them catch you out.",
    tips: ["Add every deadline you can't miss: tax filings, permit renewals, contract end dates.", "Repeating ones (yearly, quarterly) roll forward by themselves."],
    steps: [{ targets: tid("add-legal-matter-btn"), title: "Add a deadline or contract", body: "What it is, who it's with, and the due date. Set it to repeat if it comes back every year." }],
  },
  {
    id: "maintenance",
    path: /^\/app\/departments\/engineering_maintenance\/?$/,
    name: "Maintenance",
    purpose: "Repair tickets for equipment, and which machines keep breaking.",
    tips: ["Log every breakdown, even small ones.", "Machines that fail again and again get flagged so you can decide: fix properly or replace."],
    steps: [{ targets: tid("add-maintenance-ticket-btn"), title: "Log a ticket", body: "Which machine, what's wrong, how urgent, and who's on it." }],
  },
  {
    id: "hr",
    path: /^\/app\/departments\/hr\/?$/,
    name: "HR",
    purpose: "Leave requests and onboarding for new hires.",
    tips: ["Leave requests waiting on you show on your Briefing.", "Onboarding checklists make sure each new hire gets the same good start."],
    steps: [
      { targets: tid("hr-add-leave-btn"), title: "Leave requests", body: "Log a leave request, then approve or decline it." },
      { targets: tid("hr-add-onboarding-btn"), title: "Onboarding", body: "Start a checklist for a new hire." },
    ],
  },
];

/** The quick-add walkthrough: can start on any page. */
export const QUICK_ADD_GUIDE = {
  id: "quickadd",
  name: "Quick add",
  purpose: "Add a task, decision or note from any page in a few seconds.",
  tips: [],
  steps: [
    {
      targets: SEARCH,
      title: "Open the search bar",
      body: "Press Ctrl+K (Cmd+K on a Mac), or click here. It works on every page.",
    },
    {
      targets: SEARCH,
      title: "Type what you mean",
      body: "Start with task, decision or note. For example: task call the bank friday · task send invoice oct 20 for Ann !high · note ask Sam about the lease",
    },
    {
      targets: [],
      title: "Check it, then press Enter",
      body: "A preview shows the title, date, person and priority it understood. Nothing saves until you press Enter.",
      tryIt: "task ",
    },
  ],
};

export const ALL_GUIDES = [...GUIDES, QUICK_ADD_GUIDE];

export function guideForPath(pathname) {
  const clean = (pathname || "").replace(/\/+$/, "") || "/";
  return GUIDES.find((g) => g.path.test(clean) || g.path.test(`${clean}/`)) || null;
}

export function guideById(id) {
  return ALL_GUIDES.find((g) => g.id === id) || null;
}
