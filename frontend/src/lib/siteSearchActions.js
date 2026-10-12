/** Public marketing pages available from the ⌘K quick-nav search.

Omit /integrations — the in-app Settings → Integrations page already covers
connecting tools; the public marketing page stays in nav/footer only.
*/
export const SITE_SEARCH_ACTIONS = [
  {
    id: "about",
    label: "About",
    to: "/about",
    description: "Site",
    keywords: ["about trenston", "about helm", "company", "mission", "founder", "story"],
  },
  {
    id: "features",
    label: "Features",
    to: "/features",
    description: "Site",
    keywords: ["product", "modules", "cockpit", "what trenston includes", "what helm includes"],
  },
  {
    id: "pricing",
    label: "Pricing",
    to: "/pricing",
    description: "Site",
    keywords: ["plans", "price", "cost", "starter", "growth", "business", "free", "billing"],
  },
  {
    id: "compare",
    label: "How we compare",
    to: "/compare",
    description: "Site",
    keywords: ["compare", "comparison", "alternatives", "versus", "vs", "spreadsheets", "dashboards"],
  },
  {
    id: "help",
    label: "Help",
    to: "/help",
    description: "Site",
    keywords: ["docs", "how to", "guide", "faq"],
  },
  {
    id: "contact",
    label: "Contact",
    to: "mailto:contact@trenston.com",
    description: "Site",
    keywords: ["contact us", "email", "support", "reach", "talk"],
  },
  {
    id: "security-page",
    label: "Security",
    to: "/security",
    description: "Site",
    keywords: ["trust", "encryption", "privacy"],
  },
  {
    id: "changelog",
    label: "Changelog",
    to: "/changelog",
    description: "Site",
    keywords: ["whats new", "updates", "release notes", "shipped"],
  },
  {
    id: "status",
    label: "Status",
    to: "/status",
    description: "Site",
    keywords: ["uptime", "outage", "health", "operational"],
  },
  {
    id: "terms",
    label: "Terms of Service",
    to: "/terms",
    description: "Site",
    keywords: ["tos", "legal", "terms"],
  },
  {
    id: "privacy",
    label: "Privacy Policy",
    to: "/privacy",
    description: "Site",
    keywords: ["legal", "data", "gdpr"],
  },
  {
    id: "refunds",
    label: "Refunds",
    to: "/refunds",
    description: "Site",
    keywords: ["billing", "cancel", "trial", "money back"],
  },
];
