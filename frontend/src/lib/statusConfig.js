/**
 * Public status page config — honest about what we measure.
 * Live checks hit /api/health (Render). No fabricated historical uptime %.
 */
export const STATUS_TRACKING_STARTED = "2026-09-19";

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

export const STATUS_INCIDENTS = [
  // Add real incidents here when they occur, e.g.:
  // { date: "2026-09-20", title: "…", body: "…", resolved: true },
];

export const STATUS_DISCLAIMER =
  `Public status tracking started ${STATUS_TRACKING_STARTED}. We do not publish historical uptime percentages from before that date because we were not collecting them. This page shows a live check of the services we operate today, plus any incidents we record going forward.`;
