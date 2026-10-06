/**
 * Plain-text bodies for public pages, read straight from the React sources so
 * non-JS readers (crawlers, AI fetchers, curl) see the same words people do.
 * Nothing here is hand-copied: Privacy, Terms and Refunds are parsed from their
 * JSX; Security is built from its own data arrays; home/about/features/
 * integrations/changelog/status pull from marketingCopy + changelog.json +
 * statusConfig; the rest fall back to the page description from seoPages.json.
 */
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const pagesDir = join(__dirname, "../src/pages");
const marketingCopyPath = join(__dirname, "../src/lib/marketingCopy.js");
const changelogPath = join(__dirname, "../src/lib/changelog.json");
const statusConfigPath = join(__dirname, "../src/lib/statusConfig.js");

const ENTITIES = { "&apos;": "'", "&quot;": '"', "&amp;": "&", "&nbsp;": " ", "&lt;": "<", "&gt;": ">" };

function decode(s) {
  return s.replace(/&(apos|quot|amp|nbsp|lt|gt);/g, (m) => ENTITIES[m]);
}

function copyConstants() {
  const src = readFileSync(marketingCopyPath, "utf8");
  const out = {};
  for (const m of src.matchAll(/export const ([A-Z_]+) = "([^"\n]*)";/g)) out[m[1]] = m[2];
  return out;
}

function extractStringExport(src, name) {
  // Single- or multi-line: export const NAME = "…";  (these copy strings have no escapes)
  const re = new RegExp(`export const ${name} =\\s*"([^"]*)"`);
  const m = src.match(re);
  return m ? m[1] : null;
}

function extractExport(src, name, scope = {}) {
  // Arrays / objects: non-greedy to the first top-level `;\n` after `=`.
  const re = new RegExp(`export const ${name} = ([\\s\\S]*?);\\n`);
  const m = src.match(re);
  if (m) {
    try {
      const keys = Object.keys(scope);
      const vals = keys.map((k) => scope[k]);
      return Function(...keys, `"use strict"; return (${m[1]})`)(...vals);
    } catch {
      /* fall through to string form */
    }
  }
  return extractStringExport(src, name);
}

/** String constants first, then arrays that may reference those identifiers. */
function marketingExport(name) {
  const src = readFileSync(marketingCopyPath, "utf8");
  const scope = copyConstants();
  for (const key of ["INTEGRATIONS_PUBLIC_BLURB", "PUBLIC_INTEGRATIONS_INTRO", "PUBLIC_INTEGRATIONS_ATTRIBUTION"]) {
    if (scope[key] != null) continue;
    const v = extractStringExport(src, key);
    if (typeof v === "string") scope[key] = v;
  }
  // Prefer string extractor for known plain-string exports (regex `= …;\n` is flaky on them).
  if (["TAGLINE", "HERO_OUTCOME", "HERO_SUB", "WHAT_TRENSTON_IS", "ABOUT_PROBLEM", "ABOUT_STORY", "FOUNDER_NOTE", "INTEGRATIONS_PUBLIC_BLURB", "PUBLIC_INTEGRATIONS_INTRO", "PUBLIC_INTEGRATIONS_ATTRIBUTION"].includes(name)) {
    return extractStringExport(src, name) ?? extractExport(src, name, scope);
  }
  return extractExport(src, name, scope);
}

function jsxToText(chunk, consts) {
  return decode(
    chunk
      .replace(/\{\s*"([^"]*)"\s*\}/g, "$1")
      .replace(/\{([A-Z_]+)\}/g, (_, id) => consts[id] ?? "")
      .replace(/\{[^{}]*\}/g, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .replace(/\s+([.,;:)])/g, "$1")
      .trim(),
  );
}

/** Sections of a legal-style page: [{ heading, paragraphs }]. */
function legalSections(file) {
  const src = readFileSync(join(pagesDir, file), "utf8");
  const consts = copyConstants();
  const sections = [];
  for (const m of src.matchAll(/<section[^>]*>([\s\S]*?)<\/section>/g)) {
    const block = m[1];
    const h2 = block.match(/<h2[^>]*>([\s\S]*?)<\/h2>/);
    const heading = h2 ? jsxToText(h2[1], consts) : "";
    const parts = [];
    for (const p of block.matchAll(/<(p|li)[^>]*>([\s\S]*?)<\/\1>/g)) {
      const t = jsxToText(p[2], consts);
      if (t) parts.push(t);
    }
    if (heading || parts.length) sections.push({ heading, parts });
  }
  return sections;
}

function evalConst(src, name) {
  const m = src.match(new RegExp(`const ${name} = (\\[[\\s\\S]*?\\n\\]);\\n`));
  if (!m) return [];
  try {
    return Function(`"use strict"; return (${m[1].replace(/^\s*icon: \w+,\n/gm, "")})`)();
  } catch {
    return [];
  }
}

function securitySections() {
  const src = readFileSync(join(pagesDir, "Security.jsx"), "utf8");
  const sections = [];
  const pairs = (rows, a, b) => rows.map((r) => `${r[a]}: ${r[b]}`);
  sections.push({ heading: "Where data lives", parts: pairs(evalConst(src, "WHERE_DATA_LIVES"), "title", "body") });
  sections.push({ heading: "Encryption", parts: pairs(evalConst(src, "ENCRYPTION"), "title", "body") });
  sections.push({ heading: "Third parties", parts: pairs(evalConst(src, "THIRD_PARTIES"), "name", "why") });
  sections.push({ heading: "Retention and deletion", parts: evalConst(src, "RETENTION") });
  sections.push({ heading: "Your data, your exit", parts: pairs(evalConst(src, "DATA_EXIT"), "title", "body") });
  sections.push({ heading: "Staff access", parts: evalConst(src, "STAFF_ACCESS") });
  sections.push({ heading: "Controls", parts: pairs(evalConst(src, "CONTROLS"), "title", "body") });
  sections.push({ heading: "Practices", parts: evalConst(src, "PRACTICES") });
  sections.push({ heading: "Common questions", parts: pairs(evalConst(src, "QUESTIONS"), "q", "a") });
  return sections.filter((s) => s.parts.length);
}

function homeSections() {
  const tagline = marketingExport("TAGLINE") || "";
  const hero = marketingExport("HERO_OUTCOME") || "";
  const sub = marketingExport("HERO_SUB") || "";
  const what = marketingExport("WHAT_TRENSTON_IS") || "";
  const day = marketingExport("CEO_DAY") || [];
  const faq = marketingExport("HOME_FAQ") || [];
  const sections = [];
  if (tagline || hero || sub) {
    sections.push({
      heading: "What Trenston is for",
      parts: [tagline, hero, sub].filter(Boolean),
    });
  }
  if (what) sections.push({ heading: "The product", parts: [what] });
  if (Array.isArray(day) && day.length) {
    sections.push({
      heading: "A day in the cockpit",
      parts: day.map((r) => `${r.title}: ${r.body}`),
    });
  }
  if (Array.isArray(faq) && faq.length) {
    sections.push({
      heading: "Common questions",
      parts: faq.map((r) => `${r.q}: ${r.a}`),
    });
  }
  return sections;
}

function aboutSections() {
  const problem = marketingExport("ABOUT_PROBLEM") || "";
  const story = marketingExport("ABOUT_STORY") || "";
  const note = marketingExport("FOUNDER_NOTE") || "";
  const values = marketingExport("VALUES") || [];
  const who = marketingExport("WHO_HELM_IS_FOR") || [];
  const sections = [];
  if (problem) sections.push({ heading: "The problem", parts: [problem] });
  if (story) sections.push({ heading: "Why Trenston exists", parts: [story] });
  if (Array.isArray(values) && values.length) {
    sections.push({
      heading: "How we build",
      parts: values.map((v) => `${v.title}: ${v.body}`),
    });
  }
  if (Array.isArray(who) && who.length) {
    sections.push({
      heading: "Who it is for",
      parts: who.map((v) => `${v.title}: ${v.body}`),
    });
  }
  if (note) sections.push({ heading: "From the founder", parts: [note] });
  return sections;
}

function featuresSections() {
  const categories = marketingExport("FEATURE_CATEGORIES") || [];
  const modules = marketingExport("FEATURE_MODULES") || [];
  const sections = [];
  if (Array.isArray(categories) && categories.length) {
    sections.push({
      heading: "Capability areas",
      parts: categories.map((c) => {
        const mods = Array.isArray(c.modules) ? c.modules.join(", ") : "";
        return `${c.label}: ${c.intro}${mods ? ` Includes: ${mods}.` : ""}`;
      }),
    });
  }
  if (Array.isArray(modules) && modules.length) {
    sections.push({
      heading: "Modules",
      parts: modules.map((m) => {
        const plan = m.plan ? ` (${m.plan})` : "";
        return `${m.title}${plan}: ${m.ceoValue} ${m.body}`;
      }),
    });
  }
  return sections;
}

function integrationsSections() {
  const intro = marketingExport("PUBLIC_INTEGRATIONS_INTRO") || "";
  const items = marketingExport("PUBLIC_INTEGRATIONS") || [];
  const coming = marketingExport("PUBLIC_INTEGRATIONS_COMING_SOON") || [];
  const attribution = marketingExport("PUBLIC_INTEGRATIONS_ATTRIBUTION") || "";
  const sections = [];
  if (intro) sections.push({ heading: "Overview", parts: [intro] });
  if (Array.isArray(items) && items.length) {
    sections.push({
      heading: "Shipped integrations",
      parts: items.map((i) => {
        const scope = i.scope ? ` ${i.scope}` : "";
        return `${i.name} (${i.category}): ${i.description} ${i.feeds || ""}${scope}`;
      }),
    });
  }
  if (Array.isArray(coming) && coming.length) {
    sections.push({
      heading: "Coming soon",
      parts: coming.map((i) => `${i.name}: ${i.description}`),
    });
  }
  if (attribution) sections.push({ heading: "Trademarks", parts: [attribution] });
  return sections;
}

function changelogSections() {
  const data = JSON.parse(readFileSync(changelogPath, "utf8"));
  const intro = data.intro || "";
  const entries = Array.isArray(data.entries) ? [...data.entries] : [];
  entries.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  const sections = [];
  if (intro) sections.push({ heading: "About this changelog", parts: [intro] });
  // Cap prerender length — newest entries are enough for crawlers.
  const recent = entries.slice(0, 8);
  if (recent.length) {
    sections.push({
      heading: "Recent ships",
      parts: recent.map((e) => `${e.date} — ${e.title}: ${e.description}`),
    });
  }
  return sections;
}

function statusSections() {
  const src = readFileSync(statusConfigPath, "utf8");
  const started = extractExport(src, "STATUS_TRACKING_STARTED") || "2026-09-19";
  const components = extractExport(src, "STATUS_COMPONENTS") || [];
  const disclaimer = extractExport(src, "STATUS_DISCLAIMER") || "";
  const sections = [];
  sections.push({
    heading: "What we measure",
    parts: [
      `Public status tracking started ${started}.`,
      ...(Array.isArray(components)
        ? components.map((c) => `${c.name}: ${c.detail}`)
        : []),
    ],
  });
  if (disclaimer) sections.push({ heading: "Honesty note", parts: [disclaimer] });
  return sections;
}

const LEGAL = {
  "/privacy": { file: "Privacy.jsx", h1: "Privacy Policy" },
  "/terms": { file: "Terms.jsx", h1: "Terms of Service" },
  "/refunds": { file: "Refunds.jsx", h1: "Refund and Billing Policy" },
};

const NAV = [
  ["/features", "Features"],
  ["/pricing", "Pricing"],
  ["/integrations", "Integrations"],
  ["/security", "Security"],
  ["/privacy", "Privacy"],
  ["/terms", "Terms"],
  ["/about", "About"],
];

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** Returns the static <main> markup for a path, or null if the page has its own prerender. */
export function staticBodyFor(path, page) {
  let h1;
  let sections;
  if (LEGAL[path]) {
    h1 = LEGAL[path].h1;
    sections = legalSections(LEGAL[path].file);
  } else if (path === "/security") {
    h1 = "Security at Trenston";
    sections = securitySections();
  } else if (path === "/") {
    h1 = "Trenston";
    sections = homeSections();
  } else if (path === "/about") {
    h1 = "About Trenston";
    sections = aboutSections();
  } else if (path === "/features") {
    h1 = "Trenston Features";
    sections = featuresSections();
  } else if (path === "/integrations") {
    h1 = "Trenston Integrations";
    sections = integrationsSections();
  } else if (path === "/changelog") {
    h1 = "Trenston Changelog";
    sections = changelogSections();
  } else if (path === "/status") {
    h1 = "Trenston Status";
    sections = statusSections();
  } else {
    h1 = (page.ogTitle || page.title || "Trenston").replace(/\s*[·|].*$/, "");
    sections = [];
  }
  const body = sections
    .map((s) => {
      const items = s.parts.map((t) => `<p>${esc(t)}</p>`).join("\n  ");
      return `<section>${s.heading ? `\n  <h2>${esc(s.heading)}</h2>` : ""}\n  ${items}\n</section>`;
    })
    .join("\n");
  const nav = NAV.map(([href, label]) => `<a href="${href}">${label}</a>`).join(" · ");
  return `<main id="helm-prerender-page">
  <h1>${esc(h1)}</h1>
  <p>${esc(page.description || "")}</p>
${body}
  <nav>${nav}</nav>
</main>`;
}

export function textLength(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().length;
}
