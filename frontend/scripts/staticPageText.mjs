/**
 * Plain-text bodies for public pages, read straight from the React sources so
 * non-JS readers (crawlers, AI fetchers, curl) see the same words people do.
 * Nothing here is hand-copied: Privacy, Terms and Refunds are parsed from their
 * JSX; Security is built from its own data arrays; the rest fall back to the
 * page description from seoPages.json plus links.
 */
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const pagesDir = join(__dirname, "../src/pages");
const marketingCopyPath = join(__dirname, "../src/lib/marketingCopy.js");

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
