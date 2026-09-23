#!/usr/bin/env node
/**
 * Postbuild marketing prerender (CRA-compatible).
 *
 * Copies build/index.html into per-route static files with route-specific
 * <title>, description, canonical, and Open Graph / Twitter tags rewritten
 * in the head. For /pricing, also injects visible plan HTML + JSON-LD into
 * #root so non-JS fetchers (AI crawlers, curl) see real dollar figures from
 * marketingCopy.js — not just meta tags. For /about, injects Person JSON-LD
 * (founder name, role, LinkedIn sameAs) from the same marketingCopy constants.
 *
 * Output:
 *   build/index.html
 *   build/about/index.html
 *   build/pricing/index.html
 *   …
 *   build/llms.txt (+ refreshes public/llms.txt)
 *
 * Vercel serves these static files before the SPA rewrite catch-all.
 */
import { mkdirSync, readFileSync, writeFileSync, existsSync, copyFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { loadMarketingPlans, formatPlanPrice, loadFounderIdentity } from "./loadMarketingPlans.mjs";
import { writeLlmsTxt } from "./sync-llms-txt.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, "..");
const buildDir = join(frontendRoot, "build");
const indexPath = join(buildDir, "index.html");
const seoPath = join(frontendRoot, "src/lib/seoPages.json");

function upsertMeta(html, attr, key, content) {
  const re = new RegExp(`<meta\\s+[^>]*${attr}=["']${key}["'][^>]*>`, "i");
  const tag = `<meta ${attr}="${key}" content="${escapeAttr(content)}" />`;
  if (re.test(html)) return html.replace(re, tag);
  return html.replace(/<\/head>/i, `    ${tag}\n    </head>`);
}

function upsertLink(html, rel, href) {
  const re = new RegExp(`<link\\s+[^>]*rel=["']${rel}["'][^>]*>`, "i");
  const tag = `<link rel="${rel}" href="${escapeAttr(href)}" />`;
  if (re.test(html)) return html.replace(re, tag);
  return html.replace(/<\/head>/i, `    ${tag}\n    </head>`);
}

function upsertTitle(html, title) {
  if (/<title>[\s\S]*?<\/title>/i.test(html)) {
    return html.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeHtml(title)}</title>`);
  }
  return html.replace(/<\/head>/i, `    <title>${escapeHtml(title)}</title>\n    </head>`);
}

function escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function applySeo(html, { path, page, origin, ogImage }) {
  const canonical = path === "/" ? `${origin}/` : `${origin}${path}`;
  let out = html;
  out = upsertTitle(out, page.title);
  out = upsertMeta(out, "name", "description", page.description);
  out = upsertLink(out, "canonical", canonical);
  out = upsertMeta(out, "property", "og:url", canonical);
  out = upsertMeta(out, "property", "og:title", page.ogTitle || page.title);
  out = upsertMeta(out, "property", "og:description", page.ogDescription || page.description);
  out = upsertMeta(out, "property", "og:image", ogImage);
  out = upsertMeta(out, "name", "twitter:title", page.ogTitle || page.title);
  out = upsertMeta(out, "name", "twitter:description", page.ogDescription || page.description);
  out = upsertMeta(out, "name", "twitter:image", ogImage);
  return out;
}

function pricingJsonLd(plans, origin) {
  const offers = plans.map((p) => ({
    "@type": "Offer",
    name: p.label,
    description: p.for || undefined,
    price: String(Number(p.price) || 0),
    priceCurrency: "USD",
    availability: "https://schema.org/InStock",
    url: `${origin}/pricing`,
    priceSpecification: {
      "@type": "UnitPriceSpecification",
      price: String(Number(p.price) || 0),
      priceCurrency: "USD",
      billingDuration: "P1M",
      unitText: "month",
    },
  }));
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: "Trenston",
    description: "CEO Operating System — Briefing, decisions, financials, and department lanes.",
    brand: { "@type": "Brand", name: "Trenston" },
    url: `${origin}/pricing`,
    offers: {
      "@type": "AggregateOffer",
      priceCurrency: "USD",
      lowPrice: String(Math.min(...plans.map((p) => Number(p.price) || 0))),
      highPrice: String(Math.max(...plans.map((p) => Number(p.price) || 0))),
      offerCount: String(plans.length),
      offers,
    },
  };
}

/** Person JSON-LD for /about — name, role, LinkedIn sameAs only (no fabricated fields). */
function founderPersonJsonLd({ FOUNDER_NAME, FOUNDER_ROLE, FOUNDER_LINKEDIN_URL }, origin) {
  return {
    "@context": "https://schema.org",
    "@type": "Person",
    name: FOUNDER_NAME,
    jobTitle: FOUNDER_ROLE,
    sameAs: [FOUNDER_LINKEDIN_URL],
    url: `${origin}/about`,
  };
}

function pricingStaticHtml(plans) {
  const cards = plans
    .map((p) => {
      const price = formatPlanPrice(p);
      const features = (p.includes || [])
        .map((f) => `<li>${escapeHtml(f)}</li>`)
        .join("");
      const trial =
        Number(p.trialDays) > 0
          ? `<p>${escapeHtml(String(p.trialDays))}-day free trial</p>`
          : "";
      return `<article>
  <h2>${escapeHtml(p.label)}</h2>
  <p><strong>${escapeHtml(price)}</strong>${Number(p.price) > 0 ? "" : " (free)"}</p>
  <p>${escapeHtml(p.for || "")}</p>
  <p>Up to ${escapeHtml(String(p.seats))} seats</p>
  ${trial}
  <ul>${features}</ul>
</article>`;
    })
    .join("\n");

  return `<main id="helm-prerender-pricing">
  <h1>Trenston pricing</h1>
  <p>Start free. Paid plans include a 7-day free trial. Cancel anytime.</p>
  <p>Canonical plan list (source: frontend/src/lib/marketingCopy.js PLANS):</p>
  ${cards}
  <p><a href="/features">Features</a> · <a href="/about">About</a> · <a href="/security">Security</a></p>
</main>`;
}

function injectPricingBody(html, plans, origin) {
  const body = pricingStaticHtml(plans);
  const jsonLd = `<script type="application/ld+json" id="helm-pricing-jsonld">${JSON.stringify(pricingJsonLd(plans, origin))}</script>`;
  let out = html;
  // Visible content for non-JS fetchers; React replace #root on boot.
  if (/<div id="root"><\/div>/i.test(out)) {
    out = out.replace(/<div id="root"><\/div>/i, `<div id="root">${body}</div>`);
  } else if (/<div id="root">[\s\S]*?<\/div>/i.test(out)) {
    out = out.replace(/<div id="root">[\s\S]*?<\/div>/i, `<div id="root">${body}</div>`);
  } else {
    out = out.replace(/<body([^>]*)>/i, `<body$1>\n${body}\n`);
  }
  // Always attach Product/Offer JSON-LD (site may already have Organization graph).
  if (/id="helm-pricing-jsonld"/i.test(out)) {
    out = out.replace(/<script type="application\/ld\+json" id="helm-pricing-jsonld">[\s\S]*?<\/script>/i, jsonLd);
  } else {
    out = out.replace(/<\/head>/i, `    ${jsonLd}\n    </head>`);
  }
  return out;
}

function injectAboutPersonJsonLd(html, founder, origin) {
  const jsonLd = `<script type="application/ld+json" id="helm-founder-jsonld">${JSON.stringify(founderPersonJsonLd(founder, origin))}</script>`;
  if (/id="helm-founder-jsonld"/i.test(html)) {
    return html.replace(/<script type="application\/ld\+json" id="helm-founder-jsonld">[\s\S]*?<\/script>/i, jsonLd);
  }
  return html.replace(/<\/head>/i, `    ${jsonLd}\n    </head>`);
}

function main() {
  if (!existsSync(indexPath)) {
    console.error("prerender-marketing: build/index.html missing — run build first");
    process.exit(1);
  }
  const { origin, ogImage, pages } = JSON.parse(readFileSync(seoPath, "utf8"));
  const shell = readFileSync(indexPath, "utf8");
  const { PLANS } = loadMarketingPlans();
  const founder = loadFounderIdentity();

  for (const [path, page] of Object.entries(pages)) {
    let html = applySeo(shell, { path, page, origin, ogImage });
    if (path === "/pricing") {
      html = injectPricingBody(html, PLANS, origin);
    }
    if (path === "/about") {
      html = injectAboutPersonJsonLd(html, founder, origin);
    }
    const outFile =
      path === "/"
        ? indexPath
        : join(buildDir, path.replace(/^\//, ""), "index.html");
    mkdirSync(dirname(outFile), { recursive: true });
    writeFileSync(outFile, html, "utf8");
    console.log(`prerender-marketing: wrote ${outFile.slice(frontendRoot.length + 1)}`);
  }

  const publicLlms = writeLlmsTxt(join(frontendRoot, "public/llms.txt"));
  const buildLlms = join(buildDir, "llms.txt");
  copyFileSync(publicLlms, buildLlms);
  console.log(`prerender-marketing: wrote ${buildLlms.slice(frontendRoot.length + 1)}`);
  console.log("prerender-marketing: ok");
}

main();
