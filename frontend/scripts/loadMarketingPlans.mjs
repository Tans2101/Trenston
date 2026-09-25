/**
 * Load PLANS (+ light metadata) from marketingCopy.js without bundling React.
 * marketingCopy.js is the canonical pricing source — keep this parser in sync
 * with the export shape there (plain array of plan objects).
 */
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const marketingCopyPath = join(__dirname, "../src/lib/marketingCopy.js");

function extractExport(src, name) {
  const re = new RegExp(`export const ${name} = ([\\s\\S]*?);\\n`);
  const m = src.match(re);
  if (!m) throw new Error(`loadMarketingPlans: export ${name} not found`);
  return Function(`"use strict"; return (${m[1]})`)();
}

export function loadMarketingPlans() {
  const src = readFileSync(marketingCopyPath, "utf8");
  const PLANS = extractExport(src, "PLANS");
  if (!Array.isArray(PLANS) || PLANS.length < 1) {
    throw new Error("loadMarketingPlans: PLANS empty or invalid");
  }
  const TAGLINE = extractExport(src, "TAGLINE");
  const CATEGORY = extractExport(src, "CATEGORY");
  const AUDIENCE = extractExport(src, "AUDIENCE");
  return { PLANS, TAGLINE, CATEGORY, AUDIENCE, marketingCopyPath };
}

/** Founder identity for About Person JSON-LD (name, role, LinkedIn sameAs). */
export function loadFounderIdentity() {
  const src = readFileSync(marketingCopyPath, "utf8");
  const FOUNDER_NAME = extractExport(src, "FOUNDER_NAME");
  const FOUNDER_ROLE = extractExport(src, "FOUNDER_ROLE");
  const FOUNDER_LINKEDIN_URL = extractExport(src, "FOUNDER_LINKEDIN_URL");
  if (!FOUNDER_NAME || !FOUNDER_ROLE || !FOUNDER_LINKEDIN_URL) {
    throw new Error("loadFounderIdentity: missing founder exports");
  }
  return { FOUNDER_NAME, FOUNDER_ROLE, FOUNDER_LINKEDIN_URL };
}

/** Public /help FAQ for FAQPage JSON-LD (HOW_TO_USE_FAQ in marketingCopy.js). */
export function loadHelpFaq() {
  const src = readFileSync(marketingCopyPath, "utf8");
  const faq = extractExport(src, "HOW_TO_USE_FAQ");
  if (!Array.isArray(faq) || faq.length < 1) {
    throw new Error("loadHelpFaq: HOW_TO_USE_FAQ empty or invalid");
  }
  for (const item of faq) {
    if (!item?.q || !item?.a) {
      throw new Error("loadHelpFaq: each FAQ item needs q and a");
    }
  }
  return faq;
}

export function formatPlanPrice(plan) {
  const n = Number(plan.price);
  if (!(n > 0)) return "$0";
  return `$${n}/mo`;
}

export function plansPlainLines(plans) {
  return plans.map((p) => {
    const seats = p.seats != null ? `${p.seats} users` : "";
    const forWhom = p.for ? ` — ${p.for}` : "";
    return `- ${p.label}: ${formatPlanPrice(p)}${seats ? ` (${seats})` : ""}${forWhom}`;
  });
}
