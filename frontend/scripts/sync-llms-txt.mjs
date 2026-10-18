#!/usr/bin/env node
/**
 * Writes public/llms.txt from marketingCopy.js PLANS so AI crawlers get
 * current pricing without scraping the SPA. Run from build/prerender.
 */
import { writeFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { loadMarketingPlans, plansPlainLines } from "./loadMarketingPlans.mjs";
import { marketingExport } from "./staticPageText.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, "..");
const ORIGIN = "https://www.trenston.com";

export function buildLlmsTxt() {
  const { PLANS, TAGLINE, CATEGORY, AUDIENCE } = loadMarketingPlans();
  const what = marketingExport("WHAT_TRENSTON_IS") || "";
  const who = marketingExport("WHO_HELM_IS_FOR") || [];
  const day = marketingExport("CEO_DAY") || [];
  const faq = marketingExport("HOME_FAQ") || [];
  const list = (rows, a, b) => (Array.isArray(rows) ? rows.map((r) => `- ${r[a]}: ${r[b]}`) : []);
  const lines = [
    "# Trenston",
    "",
    `> ${CATEGORY}. ${TAGLINE}`,
    "",
    "Trenston is web software that puts a company's money, sales, team, tasks, and decisions in one place,",
    "so the person running the company can see what changed, what needs a decision, and what can be handed off.",
    AUDIENCE,
    "",
    what,
    "",
    "## Who it is for",
    "",
    ...list(who, "title", "body"),
    "",
    "## Main features",
    "",
    ...list(day, "title", "body"),
    "- Departments (optional): Sales, Accounting & Finance, Production, Procurement, Legal, HR, and Engineering & Maintenance pages, turned on only when a company uses them.",
    "",
    "## Integrations",
    "",
    "- Google Calendar and Drive, on every plan (Trenston does not request any Gmail access)",
    "- QuickBooks, Xero, and Slack, from Starter",
    "- SAP Business One and HubSpot, from Growth",
    `- Details: ${ORIGIN}/integrations`,
    "",
    "## Pricing",
    "",
    ...plansPlainLines(PLANS),
    "",
    "Paid plans (Starter, Growth, Business) include a 7-day free trial.",
    "Billing is via Paddle. Cancel anytime from Billing.",
    `Authoritative pricing: ${ORIGIN}/pricing`,
    "",
    "## Common questions",
    "",
    ...list(faq, "q", "a"),
    "",
    "## Pages",
    "",
    `- Home: ${ORIGIN}/`,
    `- Features: ${ORIGIN}/features`,
    `- Pricing: ${ORIGIN}/pricing`,
    `- How Trenston compares: ${ORIGIN}/compare`,
    `- Trenston vs Excel and Google Sheets: ${ORIGIN}/compare/excel-google-sheets`,
    `- Trenston vs Power BI: ${ORIGIN}/compare/power-bi`,
    `- Trenston vs Notion: ${ORIGIN}/compare/notion`,
    `- Guides for founders and CEOs: ${ORIGIN}/guides`,
    `- How to track runway as a founder: ${ORIGIN}/guides/how-to-track-runway-as-a-founder`,
    `- What a CEO should check every morning: ${ORIGIN}/guides/what-a-ceo-should-check-every-morning`,
    `- Integrations: ${ORIGIN}/integrations`,
    `- Security: ${ORIGIN}/security`,
    `- About: ${ORIGIN}/about`,
    `- Help: ${ORIGIN}/help`,
    `- Changelog: ${ORIGIN}/changelog`,
    "",
    "## Company",
    "",
    "- Founded: September 2026, BGC, Taguig, Philippines",
    "- Contact: contact@trenston.com",
    "",
  ];
  return `${lines.join("\n")}\n`;
}

export function writeLlmsTxt(outPath = join(frontendRoot, "public/llms.txt")) {
  const body = buildLlmsTxt();
  writeFileSync(outPath, body, "utf8");
  return outPath;
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const path = writeLlmsTxt();
  console.log(`sync-llms-txt: wrote ${path}`);
}
