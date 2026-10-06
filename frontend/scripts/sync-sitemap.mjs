#!/usr/bin/env node
/**
 * Writes public/sitemap.xml (and optionally build/sitemap.xml) from seoPages.json
 * so loc list stays in lockstep with marketing SEO routes. lastmod is the build
 * date (UTC) so each deploy refreshes sitemap freshness for Google.
 */
import { copyFileSync, readFileSync, writeFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, "..");
const seoPath = join(frontendRoot, "src/lib/seoPages.json");

/** Defaults when a page omits sitemap fields. */
const DEFAULTS = {
  "/": { changefreq: "weekly", priority: "1.0" },
  "/pricing": { changefreq: "weekly", priority: "0.9" },
  "/features": { changefreq: "monthly", priority: "0.8" },
  "/integrations": { changefreq: "monthly", priority: "0.8" },
  "/about": { changefreq: "monthly", priority: "0.8" },
  "/help": { changefreq: "monthly", priority: "0.7" },
  "/security": { changefreq: "monthly", priority: "0.7" },
  "/changelog": { changefreq: "weekly", priority: "0.7" },
  "/status": { changefreq: "daily", priority: "0.6" },
  "/terms": { changefreq: "yearly", priority: "0.3" },
  "/privacy": { changefreq: "yearly", priority: "0.3" },
  "/refunds": { changefreq: "yearly", priority: "0.3" },
};

function escapeXml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function buildSitemapXml({ origin, pages }, lastmod = new Date().toISOString().slice(0, 10)) {
  const paths = Object.keys(pages).sort((a, b) => {
    if (a === "/") return -1;
    if (b === "/") return 1;
    return a.localeCompare(b);
  });
  const urls = paths.map((path) => {
    const page = pages[path] || {};
    const meta = DEFAULTS[path] || { changefreq: "monthly", priority: "0.5" };
    const loc = path === "/" ? `${origin}/` : `${origin}${path}`;
    const changefreq = page.changefreq || meta.changefreq;
    const priority = page.priority != null ? String(page.priority) : meta.priority;
    const mod = page.lastmod || lastmod;
    return `  <url>
    <loc>${escapeXml(loc)}</loc>
    <lastmod>${escapeXml(mod)}</lastmod>
    <changefreq>${escapeXml(changefreq)}</changefreq>
    <priority>${escapeXml(priority)}</priority>
  </url>`;
  });
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.join("\n")}
</urlset>
`;
}

export function writeSitemap(outPath = join(frontendRoot, "public/sitemap.xml"), lastmod) {
  const { origin, pages } = JSON.parse(readFileSync(seoPath, "utf8"));
  if (!origin || !pages || typeof pages !== "object") {
    throw new Error("sync-sitemap: seoPages.json missing origin/pages");
  }
  const body = buildSitemapXml({ origin, pages }, lastmod);
  writeFileSync(outPath, body, "utf8");
  return outPath;
}

export function syncSitemapToBuild(buildDir = join(frontendRoot, "build")) {
  const publicPath = writeSitemap(join(frontendRoot, "public/sitemap.xml"));
  const buildPath = join(buildDir, "sitemap.xml");
  copyFileSync(publicPath, buildPath);
  return { publicPath, buildPath };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const path = writeSitemap();
  console.log(`sync-sitemap: wrote ${path}`);
}
