/**
 * @jest-environment node
 */
/** Unit tests for marketing SEO path helpers + sitemap lockstep. */
import { execFileSync } from "child_process";
import { readFileSync } from "fs";
import { join } from "path";
import { canonicalForPath, seoForPath, SEO_PAGES, HELM_ORIGIN } from "./seoPages";

const frontendRoot = join(__dirname, "../..");

describe("seoPages", () => {
  test("about and features have distinct canonicals and titles", () => {
    expect(canonicalForPath("/about")).toBe("https://www.trenston.com/about");
    expect(canonicalForPath("/features")).toBe("https://www.trenston.com/features");
    expect(canonicalForPath("/")).toBe("https://www.trenston.com/");
    expect(seoForPath("/about").title).not.toBe(seoForPath("/").title);
    expect(seoForPath("/features").ogTitle).not.toBe(seoForPath("/").ogTitle);
  });

  test("app routes canonicalize to homepage", () => {
    expect(canonicalForPath("/app/financials")).toBe("https://www.trenston.com/");
  });

  test("all twelve marketing routes are defined", () => {
    expect(Object.keys(SEO_PAGES).sort()).toEqual(
      [
        "/",
        "/about",
        "/changelog",
        "/features",
        "/help",
        "/integrations",
        "/pricing",
        "/privacy",
        "/refunds",
        "/security",
        "/status",
        "/terms",
      ].sort(),
    );
  });

  test("generated sitemap lists every SEO page with a fresh lastmod", () => {
    const code = `
      import { buildSitemapXml } from "./scripts/sync-sitemap.mjs";
      import { readFileSync } from "fs";
      const seo = JSON.parse(readFileSync("./src/lib/seoPages.json", "utf8"));
      process.stdout.write(buildSitemapXml(seo, "2026-10-06"));
    `;
    const xml = execFileSync("node", ["-e", code], { cwd: frontendRoot, encoding: "utf8" });
    for (const path of Object.keys(SEO_PAGES)) {
      const loc = path === "/" ? `${HELM_ORIGIN}/` : `${HELM_ORIGIN}${path}`;
      expect(xml).toContain(`<loc>${loc}</loc>`);
    }
    expect(xml).toContain("<lastmod>2026-10-06</lastmod>");
    expect(xml).not.toContain("helmcontrol.online");
  });
});
