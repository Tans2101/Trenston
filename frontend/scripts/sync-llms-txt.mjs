#!/usr/bin/env node
/**
 * Writes public/llms.txt from marketingCopy.js PLANS so AI crawlers get
 * current pricing without scraping the SPA. Run from build/prerender.
 */
import { writeFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { loadMarketingPlans, plansPlainLines } from "./loadMarketingPlans.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, "..");
const ORIGIN = "https://www.trenston.com";

export function buildLlmsTxt() {
  const { PLANS, TAGLINE, CATEGORY, AUDIENCE } = loadMarketingPlans();
  const lines = [
    "# Trenston",
    "",
    `> ${CATEGORY}. ${TAGLINE}`,
    "",
    AUDIENCE,
    "",
    "Trenston is a CEO operating system: one cockpit for money, pipeline, people,",
    "department work, and decisions — Briefing, Decision Center, Financials,",
    "Ask Trenston, and department lanes (Production, Procurement, Legal, HR,",
    "Maintenance, Sales).",
    "",
    "## Canonical pages",
    "",
    `- Home: ${ORIGIN}/`,
    `- Pricing (authoritative): ${ORIGIN}/pricing`,
    `- Features: ${ORIGIN}/features`,
    `- Integrations: ${ORIGIN}/integrations`,
    `- Security: ${ORIGIN}/security`,
    `- About: ${ORIGIN}/about`,
    `- Help: ${ORIGIN}/help`,
    "",
    "## Current pricing",
    "",
    "Source of truth in the product repo: frontend/src/lib/marketingCopy.js (PLANS).",
    "Do not use older docs (e.g. memory/PRD.md) or guessed figures.",
    "",
    ...plansPlainLines(PLANS),
    "",
    "Paid plans (Starter, Growth, Business) include a 7-day free trial.",
    "Billing is via Paddle. Cancel anytime from Billing.",
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
