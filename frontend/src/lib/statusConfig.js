/**
 * Public status page config — honest about what we measure.
 * Live checks hit /api/health (Render). No fabricated historical uptime %.
 */
export const STATUS_TRACKING_STARTED = "2026-09-19";

export const STATUS_INTRO =
  "This page reports whether Trenston’s public web app, API, and database path are reachable right now. Checks run when you open the page; we do not invent historical uptime charts.";

export const STATUS_COMPONENTS = [
  {
    id: "web",
    name: "Web app",
    detail: "Marketing site and cockpit UI on Vercel (www.trenston.com).",
    check: "page",
  },
  {
    id: "api",
    name: "API",
    detail: "FastAPI backend on Render (health check at /api/health).",
    check: "api",
  },
  {
    id: "database",
    name: "Database",
    detail: "MongoDB Atlas: primary workspace data. Reported via the API health probe.",
    check: "mongo",
  },
];

export const STATUS_HOW_WE_CHECK = [
  "Web app: we load the public site origin and treat a successful response as up.",
  "API: we call /api/health on the Render backend and expect a JSON status of ok.",
  "Database: the same health response reports whether MongoDB Atlas answered the API.",
  "If a check fails, this page shows which component is affected. We do not guess root cause from the browser.",
];

export const STATUS_INCIDENTS = [
  // Add real incidents here when they occur, e.g.:
  // { date: "2026-09-20", title: "…", body: "…", resolved: true },
];

export const STATUS_DISCLAIMER =
  `Public status tracking started ${STATUS_TRACKING_STARTED}. We do not publish historical uptime percentages from before that date because we were not collecting them. This page shows a live check of the services we operate today, plus any incidents we record going forward.`;

export const STATUS_CONTACT =
  "If something looks wrong and your workspace is affected, email contact@trenston.com with the time you noticed it and which screen failed.";
